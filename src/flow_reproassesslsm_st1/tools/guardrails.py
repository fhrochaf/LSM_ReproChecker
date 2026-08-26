"""Guardrails that verify LLM-reported ``verbatim`` excerpts actually occur
in the source PDF, using fuzzy substring matching to tolerate the line
breaks/hyphenation artifacts introduced by PDF text extraction.
"""

import re
import unicodedata
from functools import lru_cache
from typing import Any, Callable, TypeVar

import pdfplumber
from crewai.tasks.task_output import TaskOutput
from pydantic import BaseModel, ValidationError
from rapidfuzz import fuzz

FUZZY_MATCH_THRESHOLD = 80.0  # rapidfuzz partial_ratio score, 0-100
LINK_FUZZY_MATCH_THRESHOLD = 80.0  # stricter: links are short, exact strings

# Mirrors crewai.utilities.converter._JSON_PATTERN: grabs the outermost
# {...} span so a JSON object wrapped in prose/code fences still parses.
_JSON_PATTERN = re.compile(r"({.*})", re.DOTALL)

# Typographic characters PDFs commonly use (smart quotes, en/em dashes,
# non-breaking spaces) that an LLM transcribing a "verbatim" quote almost
# always normalizes to their plain-ASCII equivalents. Folding both sides to
# the same form avoids penalizing otherwise-exact quotes for this.
_TYPOGRAPHIC_FOLD = str.maketrans(
    {
        "‘": "'",
        "’": "'",
        "“": '"',
        "”": '"',
        "–": "-",
        "—": "-",
        " ": " ",
    }
)

ModelT = TypeVar("ModelT", bound=BaseModel)


def _normalize_text(s: str) -> str:
    """Fold typographic punctuation/ligatures so PDF text and LLM-transcribed
    quotes compare on equal footing regardless of which "smart" characters
    each side happens to use."""
    s = unicodedata.normalize("NFKC", s)
    return s.translate(_TYPOGRAPHIC_FOLD)


@lru_cache(maxsize=8)
def _pdf_text(pdf_path: str) -> str:
    """Extract and whitespace-normalize the full text of a PDF, cached per path
    so repeated guardrail retries on the same paper don't re-parse it."""
    with pdfplumber.open(pdf_path) as pdf:
        # use_text_flow=True follows the PDF content stream's original
        # text-drawing order instead of resorting by y/x position, which
        # otherwise interleaves left/right columns line-by-line on
        # two-column academic layouts and fragments genuine quotes.
        pages = [page.extract_text(use_text_flow=True) or "" for page in pdf.pages]
    text = " ".join(pages)
    return _normalize_text(" ".join(text.split()))


def _fuzzy_contains(needle: str, haystack: str) -> tuple[float, str]:
    """Best fuzzy-match score (0-100) of `needle` as a substring of `haystack`."""
    needle = _normalize_text(" ".join(needle.split())).lower()
    haystack = haystack.lower()
    if not needle:
        return 0.0, ""

    alignment = fuzz.partial_ratio_alignment(needle, haystack)
    score = alignment.score
    best_match = haystack[alignment.dest_start : alignment.dest_end]

    if score < FUZZY_MATCH_THRESHOLD:
        # use_text_flow extraction sometimes drops spaces between words
        # (e.g. headers/citation blocks render as "Thisarticleisan..."),
        # which can drag down an otherwise-correct quote's score. Retry
        # with all whitespace stripped from both sides so missing/extra
        # spaces alone can't fail a genuine excerpt.
        despaced_needle = re.sub(r"\s+", "", needle)
        despaced_haystack = re.sub(r"\s+", "", haystack)
        despaced_alignment = fuzz.partial_ratio_alignment(despaced_needle, despaced_haystack)
        if despaced_alignment.score > score:
            score = despaced_alignment.score
            best_match = despaced_haystack[despaced_alignment.dest_start : despaced_alignment.dest_end]

    return score, best_match


def _parse_output(output: TaskOutput, model: type[ModelT]) -> ModelT | None:
    """Parse a TaskOutput's raw text into `model`.

    crewAI leaves `TaskOutput.pydantic` unset while a task guardrail is
    attached — that conversion normally only runs *after* guardrails pass
    (see crewai.task.Task._invoke_guardrail_function) — so a guardrail must
    do its own parsing rather than trusting `output.pydantic`.
    """
    if isinstance(output.pydantic, model):
        return output.pydantic

    raw = output.raw or ""
    try:
        return model.model_validate_json(raw)
    except (ValidationError, ValueError):
        pass

    match = _JSON_PATTERN.search(raw)
    if not match:
        return None
    try:
        return model.model_validate_json(match.group())
    except (ValidationError, ValueError):
        return None


def make_verbatim_guardrail(
    pdf_path: str, model: type[ModelT]
) -> Callable[[TaskOutput], tuple[bool, Any]]:
    """Build a Task guardrail that checks every non-null `verbatim` field on a
    DataReproOutput or MethodReproOutput against the PDF's actual text.

    Both DatasetEntry.verbatim and MethodEntry.verbatim are gated by
    `status`: entries whose status is NOT_MENTIONED are skipped entirely
    (verbatim is expected to be null there), and a MENTIONED entry with a
    missing verbatim is a failure.

    Any excerpt that is present gets fuzzy-matched against the PDF; a bad
    match fails the guardrail, feeding a correction message back to the
    agent for a retry. When a non-null `link` is also set, it must itself be
    fuzzy-matched inside that entry's verbatim excerpt, catching links the
    agent inferred/guessed rather than actually found quoted in the text.
    """

    def guardrail(output: TaskOutput) -> tuple[bool, Any]:
        parsed = _parse_output(output, model)
        if parsed is None:
            return False, (
                "Output could not be parsed as structured JSON. "
                "Return valid JSON matching the expected schema exactly."
            )
        output.pydantic = parsed

        entries = getattr(parsed, "datasets", None)
        if entries is None:
            entries = getattr(parsed, "methods", None)
        if not entries:
            return True, output

        text = _pdf_text(pdf_path)
        failures: list[str] = []

        for entry in entries:
            verbatim = getattr(entry, "verbatim", None)
            link = getattr(entry, "link", None)

            if entry.status == "NOT_MENTIONED":
                continue
            if not verbatim:
                failures.append(
                    f'- "{entry.name}": status is MENTIONED but verbatim is missing. '
                    "Quote the exact sentence/clause from the paper where this was found."
                )
                continue

            # An excerpt reported as "text text ... text text" splices two
            # non-adjacent spans of the source together
            segments = [seg.strip() for seg in verbatim.split("...") if seg.strip()] or [verbatim]
            results = [_fuzzy_contains(seg, text) for seg in segments]
            score = min(s for s, _ in results)
            best_match = " ... ".join(m for _, m in results)
            if score < FUZZY_MATCH_THRESHOLD:
                failures.append(
                    f'- "{entry.name}": verbatim excerpt not found in the PDF text '
                    f'(best match {score:.0f}%, need >={FUZZY_MATCH_THRESHOLD:.0f}%). '
                    f'Quoted: "{verbatim[:160]}" | Closest text in PDF: "{best_match[:160]}"'
                )
                continue

            if link:
                link_score, link_best_match = _fuzzy_contains(link, verbatim)
                if link_score < LINK_FUZZY_MATCH_THRESHOLD:
                    failures.append(
                        f'- "{entry.name}": link "{link}" does not appear in its own '
                        f"verbatim excerpt (best match {link_score:.0f}%, need >="
                        f'{LINK_FUZZY_MATCH_THRESHOLD:.0f}%). Closest text in excerpt: '
                        f'"{link_best_match[:160]}". Only set link when the URL itself is '
                        "quoted verbatim in the paper text; otherwise leave link null "
                        "(source alone is fine)."
                    )

        if failures:
            return False, (
                "The following verbatim excerpts could not be verified against the "
                "PDF's extracted text. Use only a fraction of the verbatim if the match is close. "
                "If a link was mentioned, use the text where the link is instead. "
                "Only change status to NOT_MENTIONED and set verbatim to null if the dataset/method source or link "
                "is not mentioned in the paper at all:\n" + "\n".join(failures)
            )

        return True, output

    return guardrail
