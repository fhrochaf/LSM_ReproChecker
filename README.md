# LSM ReproChecker

A [CrewAI](https://crewai.com) flow that automatically screens publications on landslide mapping (LSM) to check their detection methods and assess their reproducibility.

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
- `scripts/` — utility scripts

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

Add required API keys (e.g. `ANTHROPIC_API_KEY`, `OPENAI_API_KEY`) to a `.env` file. A local [Ollama](https://ollama.com) instance is used for some agents (`llama3.2`), so make sure it's running if you use those.

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

```bash
uv run kickoff          # run the flow against the configured publication(s)
uv run plot              # generate a flow diagram
uv run run_with_trigger '<json_payload>'   # run the flow with a single trigger payload
```

Currently `kickoff()` is hardcoded to process a single EID for testing (it must exist as a row in the input CSV, with a matching `<EID>.pdf` in `publications/`); see the commented-out loop in `main.py` for batch processing over the whole CSV.