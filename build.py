"""Build the static ReproChecker results viewer (index.html).

Reads the per-paper assessment reports produced by the reproducibility crew
and the human-reviewed Scopus export metadata (including each paper's
method approach and hybrid flag), keeps papers assessed as REPRODUCIBLE,
PARTIALLY_REPRODUCIBLE, or NOT_REPRODUCIBLE, and renders them into a single
static HTML page.

Usage:
    uv sync --group viewer   # one-time, installs jinja2 for building only
    uv run python build.py

This is a development-time tool. Its output (index.html) is a plain static
file with no build step required to view it — open it directly in a browser.
"""

from __future__ import annotations

import json
from pathlib import Path

import ftfy
import pandas as pd
from jinja2 import Environment, FileSystemLoader

REPO_ROOT = Path(__file__).resolve().parent
REPORTS_DIR = REPO_ROOT / "outputs_LSM_ReproChecker"
METADATA_CSV = REPORTS_DIR / "analysis" / "scopus_query1_postPipeline_postHumanReview.csv"
VIEWER_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = VIEWER_DIR / "templates"
OUTPUT_HTML = VIEWER_DIR / "index.html"

TARGET_STATUSES = ("REPRODUCIBLE", "PARTIALLY_REPRODUCIBLE", "NOT_REPRODUCIBLE")
STATUS_SORT_RANK = {status: i for i, status in enumerate(TARGET_STATUSES)}


def fix_mojibake(value: object) -> object:
    """Repair mis-decoded UTF-8 text (mojibake) in the Scopus export.

    Rows mix more than one mangled encoding -- plain accented letters like
    "GanerÃ¸d" (cp1252-style) alongside curly punctuation mangled through
    plain Latin-1 in other rows -- so a single hardcoded encode/decode
    roundtrip doesn't cover every row. ftfy detects and reverses mojibake
    per-string regardless of which single-byte encoding produced it, and
    leaves already-clean text untouched.
    """
    if not isinstance(value, str):
        return value
    return ftfy.fix_text(value)


def load_metadata() -> pd.DataFrame:
    df = pd.read_csv(METADATA_CSV, sep=";", engine="python", on_bad_lines="warn")
    df = df.map(fix_mojibake)
    return df.set_index("EID")


def clean_links(entries: list[dict] | None) -> list[dict]:
    """Drop the verbatim quote field; keep name/source/link/summary only."""
    out = []
    for entry in entries or []:
        out.append(
            {
                "name": entry.get("name"),
                "source": entry.get("source"),
                "link": entry.get("link"),
                "summary": entry.get("summary"),
                "method_type": entry.get("method_type"),
            }
        )
    return out


def clean_flag(value: object) -> str | None:
    """Normalise a categorical CSV cell to an upper-case string, or None."""
    if not isinstance(value, str) or not value.strip():
        return None
    return value.strip().upper()


def build_paper_record(report_path: Path, meta_row: pd.Series) -> dict:
    with report_path.open(encoding="utf-8") as f:
        report = json.load(f)

    eid = report_path.stem
    doi = meta_row.get("DOI")
    availability = report.get("availability") or {}
    # Per-paper method classification from the human-reviewed Scopus export.
    # Method_temporal (single date / multi-temporal) is intentionally ignored.
    approach = clean_flag(meta_row.get("Method_approach"))
    hybrid = clean_flag(meta_row.get("Method_hybrid")) == "YES"

    return {
        "id": eid,
        "title": meta_row.get("Title"),
        "authors": meta_row.get("Authors"),
        "year": int(meta_row["Year"]) if pd.notna(meta_row.get("Year")) else None,
        "doi": doi,
        "doi_url": f"https://doi.org/{doi}" if isinstance(doi, str) and doi else None,
        "abstract": meta_row.get("Abstract"),
        "status": report.get("reproducibility_status"),
        "approach": approach,
        "hybrid": hybrid,
        "reproducibility_assessment": report.get("reproducibility_assessment"),
        "datasets": clean_links(report.get("datasets")),
        "methods": clean_links(report.get("methods")),
        "availability": {
            "access_status": availability.get("access_status"),
            "data_status": availability.get("data_status"),
            "code_status": availability.get("code_status"),
            "author_statement": availability.get("author_statement"),
            "data_links": clean_links(availability.get("data_links")),
            "code_links": clean_links(availability.get("code_links")),
        },
    }


def collect_assessed_papers() -> list[dict]:
    meta = load_metadata()
    papers = []
    for report_path in sorted(REPORTS_DIR.glob("*.json")):
        with report_path.open(encoding="utf-8") as f:
            report = json.load(f)
        status = report.get("reproducibility_status")
        if status not in TARGET_STATUSES:
            continue
        eid = report_path.stem
        if eid not in meta.index:
            continue
        papers.append(build_paper_record(report_path, meta.loc[eid]))

    papers.sort(
        key=lambda p: (
            STATUS_SORT_RANK.get(p["status"], len(STATUS_SORT_RANK)),
            p["year"] is None,
            -(p["year"] or 0),
            p["title"] or "",
        )
    )
    return papers


def total_assessed_count() -> int:
    return sum(1 for _ in REPORTS_DIR.glob("*.json"))


def render(papers: list[dict]) -> str:
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES_DIR)),
        autoescape=True,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    template = env.get_template("index.html.jinja")
    # Escape "</script" so an abstract/quote containing it can't break out of
    # the embedded JSON <script> block below.
    papers_json = json.dumps(papers, ensure_ascii=False).replace("</script", "<\\/script")
    reproducible_count = sum(1 for p in papers if p["status"] == "REPRODUCIBLE")
    partial_count = sum(1 for p in papers if p["status"] == "PARTIALLY_REPRODUCIBLE")
    return template.render(
        papers=papers,
        papers_json=papers_json,
        reproducible_count=reproducible_count,
        partial_count=partial_count,
        total_count=total_assessed_count(),
    )


def main() -> None:
    papers = collect_assessed_papers()
    html = render(papers)
    OUTPUT_HTML.write_text(html, encoding="utf-8")
    reproducible_count = sum(1 for p in papers if p["status"] == "REPRODUCIBLE")
    partial_count = sum(1 for p in papers if p["status"] == "PARTIALLY_REPRODUCIBLE")
    not_reproducible_count = sum(1 for p in papers if p["status"] == "NOT_REPRODUCIBLE")
    print(
        f"Wrote {OUTPUT_HTML} ({reproducible_count} reproducible, "
        f"{partial_count} partially reproducible, "
        f"{not_reproducible_count} not reproducible)"
    )


if __name__ == "__main__":
    main()
