import os
from pathlib import Path

# Must be set before `crewai` is imported: it reads these at import time to
# decide whether to spin up its OTLP telemetry exporter. On this network that
# exporter hangs for minutes instead of failing fast, which stalls every run.
os.environ.setdefault("CREWAI_DISABLE_TELEMETRY", "true")
os.environ.setdefault("OTEL_SDK_DISABLED", "true")

from crewai import LLM

# ----- PATH CONFIGS
LSM_DOMAIN_INSTRUCTIONS = Path(__file__).resolve().parent / "crews" / "reprochecker_crew" / "skills" / "lsm_domain_instructions"
LSM_DOMAIN_INSTRUCTIONS.mkdir(exist_ok=True)

# Plain JSON reference (not a crewai Agent Skill: its content is mutated
# mid-run by the dataset research crew, then re-read and interpolated
# directly into compile_final_report_from_consolidated's task inputs, so it
# needs no on-disk SKILL.md/frontmatter structure).
DATASET_AVAILABILITY_REFERENCE = (
    Path(__file__).resolve().parent
    / "crews" / "reprochecker_crew" / "skills" / "dataset_availability_reference" / "dataset_availability_reference.json"
)

REPORT_TAIL_NAME = ""

PDF_DIR = Path(__file__).resolve().parent.parent.parent / "publications"
PDF_DIR.mkdir(exist_ok=True)

INPUTS_PATH = PDF_DIR / "scopus_export_Jul_22_2026_query1.csv"

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output_fullPDF_with_guardrails_singlePDFread"
OUTPUT_DIR.mkdir(exist_ok=True)

#------------ LLM CONFIGS ------------

#-------- Local/Smaller LLM's --------

llm_local = LLM(
    model="ollama/qwen3",
    base_url="http://localhost:11434",
    temperature=0
)

#-------- Remote/Larger LLM's --------

# Gemini Large LLM - lite
llm_large = LLM(
    model="gemini/gemini-3.1-flash-lite",
    temperature=0
)

EMBEDDING_CONFIG_OPENAI = {
    "embedding_model": {
        "provider": "openai",
        "config": {
            "model_name": "text-embedding-3-small",
        },
    },
}
