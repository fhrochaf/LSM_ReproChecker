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

PDF_DIR = Path(__file__).resolve().parent.parent.parent / "publications"
PDF_DIR.mkdir(exist_ok=True)

INPUTS_PATH = PDF_DIR / "scopus_export_Jul_22_2026_query1.csv"

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output_fullPDF_with_review"
OUTPUT_DIR.mkdir(exist_ok=True)

#------------ LLM CONFIGS ------------

#-------- Local/Smaller LLM's --------

# llm_local = LLM(
#     model="ollama/llama3.2",
#     base_url="http://localhost:11434",
#     temperature=0
# )
llm_local = LLM(
    model="ollama/qwen3",
    base_url="http://localhost:11434",
    temperature=0
)

#-------- Remote/Larger LLM's --------


# llm_large = LLM(
#     model="ollama/llama4:scout",
#     base_url="http://localhost:11434",
#     temperature=0
# )

## Anthropic Large LLM
# llm_large = LLM(
#     model="anthropic/claude-sonnet-5"
# )

## DeepSeek Large LLM
# llm_large = LLM(
#     model="deepseek/deepseek-v4-flash",  # This specific model ID
#     base_url="https://api.deepseek.com",
#     temperature=0
# )

## Gemini Large LLM
llm_large = LLM(
    model="gemini/gemini-3.1-flash-lite",
    temperature=0
)

# llm_large = LLM(
#     model="ollama/qwen3",
#     base_url="http://localhost:11434",
#     temperature=0
# )

EMBEDDING_CONFIG_OPENAI = {
    "embedding_model": {
        "provider": "openai",
        "config": {
            "model_name": "text-embedding-3-small",
        },
    },
}

# EMBEDDING_CONFIG_OLLAMA_NOMIC = {
#                 "embedding_model": {
#                     "provider": "ollama",
#                     "config": {
#                         "model": "nomic-embed-text",
#                     },
#                 },
#                 "vectordb": {
#                     "provider": "chromadb",
#                     "config": {
#                         "dir": Path(__file__).resolve().parent.parent / "knowledge_ollama_nomic",
#                     },
#                 }
# }
