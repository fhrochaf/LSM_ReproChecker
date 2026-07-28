from pathlib import Path
from crewai import LLM

# ----- PATH CONFIGS
LSM_DOMAIN_INSTRUCTIONS = Path(__file__).resolve().parent / "crews" / "reprochecker_crew" / "skills" / "lsm_domain_instructions"
LSM_DOMAIN_INSTRUCTIONS.mkdir(exist_ok=True)


PDF_DIR = Path(__file__).resolve().parent.parent.parent / "publications"
PDF_DIR.mkdir(exist_ok=True)

INPUTS_PATH = PDF_DIR / "scopus_export_Jul_22_2026_query1.csv"

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output2"
OUTPUT_DIR.mkdir(exist_ok=True)

llm_local = LLM(
    model="ollama/llama3.2",
    base_url="http://localhost:11434"
)

llm_2 = LLM(
    model="anthropic/claude-sonnet-5")

EMBEDDING_CONFIG_OPENAI = {
    "embedding_model": {
        "provider": "openai",
        "config": {
            "model": "text-embedding-3-small",
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