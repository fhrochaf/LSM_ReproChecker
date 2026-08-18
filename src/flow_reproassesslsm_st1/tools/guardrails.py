"""Guardrails that verify LLM-reported ``verbatim`` excerpts actually occur
in the source PDF, using fuzzy substring matching to tolerate the line
breaks/hyphenation artifacts introduced by PDF text extraction.
"""

import re
from functools import lru_cache
from typing import Any, Callable, TypeVar

import pdfplumber
from crewai.tasks.task_output import TaskOutput
from pydantic import BaseModel, ValidationError
from rapidfuzz import fuzz

FUZZY_MATCH_THRESHOLD = 80.0  # rapidfuzz partial_ratio score, 0-100
LINK_FUZZY_MATCH_THRESHOLD = 85.0  # stricter: links are short, exact strings

# Mirrors crewai.utilities.converter._JSON_PATTERN: grabs the outermost
# {...} span so a JSON object wrapped in prose/code fences still parses.
_JSON_PATTERN = re.compile(r"({.*})", re.DOTALL)

ModelT = TypeVar("ModelT", bound=BaseModel)


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
    return " ".join(text.split())


def _fuzzy_contains(needle: str, haystack: str) -> float:
    """Best fuzzy-match score (0-100) of `needle` as a substring of `haystack`."""
    needle = " ".join(needle.split())
    if not needle:
        return 0.0
    return fuzz.partial_ratio(needle.lower(), haystack.lower())


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
        print(output) #####################
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

            score = _fuzzy_contains(verbatim, text)
            if score < FUZZY_MATCH_THRESHOLD:
                failures.append(
                    f'- "{entry.name}": verbatim excerpt not found in the PDF text '
                    f'(best match {score:.0f}%, need >={FUZZY_MATCH_THRESHOLD:.0f}%): '
                    f'"{verbatim[:160]}"'
                )
                continue

            if link:
                link_score = _fuzzy_contains(link, verbatim)
                if link_score < LINK_FUZZY_MATCH_THRESHOLD:
                    failures.append(
                        f'- "{entry.name}": link "{link}" does not appear in its own '
                        f"verbatim excerpt (best match {link_score:.0f}%, need >="
                        f"{LINK_FUZZY_MATCH_THRESHOLD:.0f}%). Only set link when the URL "
                        "itself is quoted verbatim in the paper text; otherwise leave "
                        "link null (source alone is fine)."
                    )

        if failures:
            return False, (
                "The following verbatim excerpts could not be verified against the "
                "PDF's extracted text. Re-check each one and either quote the exact "
                "wording from the paper (copy it, do not paraphrase) or, if you "
                "cannot actually locate it in the text, change status to "
                "NOT_MENTIONED and set verbatim to null:\n" + "\n".join(failures)
            )

        return True, output

    return guardrail
