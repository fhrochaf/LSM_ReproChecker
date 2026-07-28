# LSM ReproChecker

A [CrewAI](https://crewai.com) flow that automatically screens landslide susceptibility mapping (LSM) publications and assesses their reproducibility, as part of an MSc thesis at the University of Twente (Thesis_LAReprod).

## What it does

`ReproCheckFlow` (`src/flow_reproassesslsm_st1/main.py`) processes one publication at a time from a Scopus export CSV:

1. **Filter** — an `abstract_screener` agent reads the abstract and decides whether the paper is actually about landslide mapping (`INCLUDE`/`EXCLUDE`).
2. **Reproducibility checks** (only if included) — a `paper_analyzer` agent reads the full PDF to extract dataset and method information, while an `availability_web_scraper` agent checks the publication's webpage for data/code availability statements and links.
3. **Report compilation** — a `report_elaborator` agent combines the above into a final `ReproducibilityAssessment`.

Results are written back into the input CSV and saved as a JSON report per publication in `output/`.

## Project layout

- `src/flow_reproassesslsm_st1/` — the CrewAI flow, crew, agents, tasks, and Pydantic models
  - `crews/reprochecker_crew/config/` — `agents.yaml` and `tasks.yaml` defining agent roles and task prompts
  - `tools/` — custom tools (e.g. webpage availability scraper)
- `publications/` — source PDFs and the Scopus CSV export used as input
- `output/` — generated per-publication reproducibility reports (JSON)
- `tests/` — pytest suite covering the flow, crew config, and filtering logic
- `scripts/` — maintenance/utility scripts
- `prototyping.ipynb`, `debug_flow.ipynb` — exploratory notebooks

## Setup

Requires Python >=3.10,<3.14 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

Add required API keys (e.g. `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) to a `.env` file. A local [Ollama](https://ollama.com) instance is used for some agents (`llama3.2`), so make sure it's running if you use those.

## Running

```bash
uv run kickoff          # run the flow against the configured publication(s)
uv run plot              # generate a flow diagram
uv run run_with_trigger '<json_payload>'   # run the flow with a single trigger payload
```

Currently `kickoff()` is hardcoded to process a single EID for testing; see the commented-out loop in `main.py` for batch processing over the whole CSV.

## Testing

```bash
uv run pytest
```