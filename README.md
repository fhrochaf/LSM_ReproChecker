# LSM ReproChecker

A [CrewAI](https://crewai.com) flow that automatically screens publications on landslide mapping (LSM) to check their detection methods and assess their reproducibility.

## What it does

`ReproCheckFlow` (`src/flow_reproassesslsm_st1/main.py`) processes one publication at a time from a Scopus export CSV:

1. **Filter** — an `abstract_screener` agent reads the abstract and decides whether the paper is actually about a landslide mapping *method* (`INCLUDE`/`EXCLUDE`), as opposed to an inventory, susceptibility mapping, or review paper. The decision is written back to the CSV so it's never re-run for that row.
2. **Availability check** — skipped if the CSV row already has prefilled `Webpage_*` availability columns (see [Prefilled availability](#prefilled-availability)); otherwise an `availability_web_scraper` agent visits the publication's DOI page to check for data/code availability statements and links.
3. **Reproducibility checks** — a `paper_analyzer` agent reads the paper's PDF (via RAG search or full-text, see [PDF reading modes](#pdf-reading-modes)) to extract every dataset and every method used, each run **three times independently** and reconciled by fuzzy consensus (see [Multi-run consensus](#multi-run-consensus)). Every extracted excerpt is also checked by a guardrail against the actual PDF text before it's accepted (see [Guardrails](#guardrails-verbatim-fuzzy-matching)).
4. **Report compilation** — a `report_elaborator` agent combines the consolidated dataset/method findings and the availability summary into a final `reproducibility_status` (`REPRODUCIBLE` / `PARTIALLY_REPRODUCIBLE` / `NOT_REPRODUCIBLE`) plus a short assessment.

Results are written back into the input CSV and saved as a JSON report per publication in the configured output directory.

## Agents

Defined in `src/flow_reproassesslsm_st1/crews/reprochecker_crew/config/agents.yaml`, wired up in `reprochecker_crew.py`:

| Agent | Role | LLM | Tools |
|---|---|---|---|
| `abstract_screener` | Fast triage from the abstract alone: INCLUDE/EXCLUDE with a reason | `llm_local` (local Ollama model) | — |
| `paper_analyzer` | Extracts dataset and method reproducibility info from the full paper | `llm_large` (remote/larger model) | `PDFSearchTool` (RAG) or `PDFFullTextTool`, plus the `lsm_domain_instructions` skill |
| `availability_web_scraper` | Visits the DOI page to confirm real-world data/code availability | `llm_large` | `PublicationAvailabilityTool` |
| `report_elaborator` | Synthesizes everything into one final structured report; never introduces new claims | `llm_large` | — |

`llm_local`/`llm_large` are configured in `src/flow_reproassesslsm_st1/config.py`. Splitting cheap triage (local model) from the heavier extraction/synthesis work (larger model) keeps cost and rate limits down — all agents are additionally capped at `MAX_RPM = 5` requests/minute.

### PDF reading modes

`paper_analyzer` reads the PDF one of two ways, toggled by `--use-full-text-tool`:

- **Default (RAG)**: `PDFSearchTool` embeds and chunks the PDF (OpenAI `text-embedding-3-small`) into a per-paper Chroma collection, and the agent retrieves the top-matching chunks per query.
- **Full text** (`--use-full-text-tool`): `PDFFullTextTool` dumps the entire extracted PDF text into the agent's context in one call — no chunking/retrieval, so nothing is missed due to an imperfect search query, at the cost of a much larger prompt.

## Multi-run consensus

Extraction is inherently noisy — the same paper read twice can turn up slightly different dataset/method lists. To reduce this, `check_data_reproducibility` and `check_method_reproducibility` are each run `MULTI_RUN_COUNT = 3` times independently by default (`reprochecker_crew.py::_repeat_task`), producing 3 separate `DataReproOutput`/`MethodReproOutput` results — configurable per invocation via `--multi-run-count`.

`utils.merge_entries` (`src/flow_reproassesslsm_st1/utils.py`) then reconciles the runs per check into one list:

1. **Cluster by fuzzy name match** — every entry from every run is folded into a cluster with any existing entry whose *normalized* name scores `>=75` on RapidFuzz `token_set_ratio` (`NAME_CLUSTER_THRESHOLD`). Normalization strips parenthetical citations and turns `-`/`_`/`/` into spaces, so e.g. `"Faster-RCNN"` and `"Faster R-CNN (Ren et al. 2016)"` cluster together even though they don't match verbatim.
2. **Majority vote** — a cluster only survives into the final result if it has entries from at least `min_votes` of the runs. `min_votes` defaults to `min(2, number of runs)`: still 2 whenever there are 2+ runs (a dataset/method only one run found is dropped as likely a hallucination or a one-off misread), but relaxes to 1 when `--multi-run-count 1` is used, since a single run can never produce 2 agreeing votes.
3. **Pick a representative** — within a surviving cluster, the entry with a non-null `link` wins (preferring the run that actually found the retrieval link); ties are broken by whichever entry has the most non-null fields (`source`, `link`, `verbatim`).

This consensus step runs entirely in Python between crew kickoffs — the Flow (`main.py::run_repro_check`) pulls the 3 raw task outputs from `self._crew._data_runs`/`_method_runs` and merges them before handing the result to `report_elaborator`.

## Guardrails: verbatim fuzzy-matching

Every `check_data_reproducibility`/`check_method_reproducibility` task run (`src/flow_reproassesslsm_st1/tools/guardrails.py`) is attached a CrewAI task **guardrail** via `make_verbatim_guardrail`, which runs after each individual run and can force a retry before the output is accepted:

- Any entry with `status: MENTIONED` must include a `verbatim` excerpt; a `MENTIONED` entry with no excerpt fails the guardrail outright.
- The excerpt is fuzzy-matched against the paper's actual extracted PDF text (`pdfplumber`, cached per PDF) using RapidFuzz `partial_ratio`. It must score `>=80` (`FUZZY_MATCH_THRESHOLD`) — a lower score means the agent likely paraphrased or fabricated the quote, and the guardrail fails with a message telling the agent to quote verbatim or mark the entry `NOT_MENTIONED`.
- If an entry also has a `link`, the link itself must fuzzy-match (`>=80`, `LINK_FUZZY_MATCH_THRESHOLD`) *inside* that entry's own verbatim excerpt — catching a URL the agent guessed/inferred rather than one actually printed next to the quote.
- Matching first normalizes typographic characters (smart quotes, en/em dashes) that PDFs use but LLM transcriptions usually don't reproduce exactly, and retries a "despaced" comparison (all whitespace stripped) to tolerate spacing artifacts from `pdfplumber`'s text extraction on multi-column layouts.

This guardrail is what actually enforces grounding: it runs independently on each multi-run pass (not just once on the consolidated result), so a hallucinated dataset/method has to survive fuzzy verification on every pass before it can even reach the consensus step above.

## Prefilled availability

If a CSV row already has `Webpage_Access_Status == "ACCESSIBLE"` plus at least one of `Webpage_Data_Status`/`Webpage_Code_Status` filled in (`utils._row_has_prefilled_availability`), the Flow skips `availability_web_scraper` entirely and reuses those columns (`utils._availability_from_row`) — including translating older/manual prefill vocabularies (e.g. `AVAILABLE`/`NOT_AVAILABLE`, `FOUND`/`NOT_FOUND`) into the current `MENTIONED`/`NOT_MENTIONED` schema. This lets a batch of availability checks be done once (e.g. by hand, or in an earlier pass) and reused across reruns of the reproducibility checks without re-scraping.

## Project layout

- `src/flow_reproassesslsm_st1/` — the CrewAI flow, crew, agents, tasks, and Pydantic models
  - `main.py` — `ReproCheckFlow` (the flow graph) and the `kickoff`/`plot`/`run_with_trigger` CLI entry points
  - `crews/reprochecker_crew/config/` — `agents.yaml` and `tasks.yaml` defining agent roles and task prompts
  - `crews/reprochecker_crew/skills/lsm_domain_instructions/` — domain-knowledge skill given to `paper_analyzer`
  - `tools/custom_tool.py` — `PublicationAvailabilityTool` (DOI-page scraper) and `PDFFullTextTool`
  - `tools/guardrails.py` — the verbatim fuzzy-match guardrail
  - `utils.py` — multi-run consensus (`merge_entries`), CSV row helpers, prefilled-availability coercion
  - `models.py` — Pydantic schemas for every task output and the Flow's state
  - `config.py` — paths, LLM configs, embedding config
- `publications/` — source PDFs (named `<EID>.pdf`) and the Scopus CSV export used as input
- `output*/` — generated per-publication reproducibility reports (JSON); the active output directory is set by `OUTPUT_DIR` in `config.py`
- `scripts/` — batch/utility scripts (abstract filtering, DOI/link checks, PDF sampling, etc.)
- `tests/` — pytest suite covering the crew config, filter step, and flow

## Prerequisites

Before running the flow, you need:

1. **A Scopus export CSV** — the input CSV listing the publications to process. It must contain at least:
   - `EID` — a unique identification ID for each publication.
   - `Abstract` — the publication's abstract text.
   - `DOI` — the publication's DOI.

   This project uses a CSV exported directly from the results of a query on [Scopus.com](https://www.scopus.com) (`;`-separated, with the standard Scopus export columns such as `Authors`, `Title`, `Year`, `DOI`, `Abstract`, `EID`, etc.). The path to this CSV is set in `INPUTS_PATH` in [src/flow_reproassesslsm_st1/config.py](src/flow_reproassesslsm_st1/config.py).

2. **A PDF of each publication you want analyzed** (only required for papers that pass the abstract filter and go through the reproducibility checks). Place the PDF in `publications/` and **rename it to match the publication's `EID`**, e.g. `2-s2.0-85130393221.pdf` for the row where `EID` is `2-s2.0-85130393221`.

## Setup

Requires Python >=3.10,<3.14 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Add required API keys (e.g. `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`, `GEMINI_API_KEY`) to a `.env` file. A local [Ollama](https://ollama.com) instance is used for `abstract_screener` (`llm_local`), so make sure it's running if you use the default config.

## Serving local LLMs with Ollama

```bash
# Pull the desired model (only required once)
ollama pull qwen3

# Verify that the model is available locally
ollama list

# (Optional) Test the model interactively
ollama run qwen3

# Start the Ollama server only if it is not already running
# (On Windows, Ollama is typically started automatically.)
ollama serve
```

## Running

Three CLI commands are exposed via `pyproject.toml`'s `[project.scripts]`:

```bash
uv run kickoff [OPTIONS]                   # batch-process rows from the input CSV
uv run plot                                # generate a flow diagram (flow.html)
uv run run_with_trigger '<json_payload>'   # run the flow once, from an explicit JSON payload
```

### `uv run kickoff` options

`kickoff()` (`main.py`) iterates every row of the input CSV in order and runs `ReproCheckFlow` on each, skipping:
- rows that already have a saved output report,
- rows where `Filter_Decision`, `Human_Filter_Decision` is `EXCLUDE`, or `Webpage_Access_Status` is `NOT_ACCESSIBLE`.

| Flag | Default | Meaning |
|---|---|---|
| `--max-papers N` | unlimited | Stop after successfully processing `N` papers in this invocation |
| `--check-paper-only EID` | none | Restrict the run to a single row, matched by `EID` |
| `--wait-seconds N` | `60` | Seconds to wait before retrying a row that raised an exception |
| `--max-retries N` | `2` | Max retry attempts per row before giving up and moving to the next one |
| `--use-full-text-tool` | off | Give `paper_analyzer` the full extracted PDF text (`PDFFullTextTool`) instead of the default `PDFSearchTool` RAG retrieval |
| `--with-human-intervention` | off | Pause after **every** task for human review, via CrewAI's native `Task(human_input=True)`: the agent's answer is shown in the terminal and you can type feedback to send it back for another pass, or press Enter to accept and move on |
| `--guardrail-max-retries N` | `3` | Max retries per task when the verbatim guardrail (see [Guardrails](#guardrails-verbatim-fuzzy-matching)) rejects an output, before giving up and accepting the last attempt |
| `--multi-run-count N` | `3` | Independent runs per dataset/method check, reconciled by majority vote (see [Multi-run consensus](#multi-run-consensus)) |

Examples:

```bash
# Process the whole CSV, retrying failures up to 3 times with a 2-minute backoff
uv run kickoff --max-retries 3 --wait-seconds 120

# Re-run a single paper, forcing full-text mode instead of RAG search
uv run kickoff --check-paper-only 2-s2.0-85130393221 --use-full-text-tool

# Process only the next 5 not-yet-processed papers (e.g. for a spot check)
uv run kickoff --max-papers 5

# Review every task's output by hand before it's accepted, and give the
# guardrail a couple more tries before giving up on a verbatim match
uv run kickoff --with-human-intervention --guardrail-max-retries 5

# Cheaper/faster spot check: 2 runs per dataset/method check instead of 3
uv run kickoff --check-paper-only 2-s2.0-85130393221 --multi-run-count 2
```

### `uv run run_with_trigger`

Runs the flow once from an explicit JSON payload instead of iterating the CSV — useful for testing a single publication or wiring the flow into an external trigger:

```bash
uv run run_with_trigger '{"publication_id": "2-s2.0-85130393221", "pdf_file": "2-s2.0-85130393221.pdf", "doi": "10.xxxx/xxxx", "abstract": "...", "use_full_text_tool": false}'
```
