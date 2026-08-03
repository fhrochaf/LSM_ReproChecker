from pathlib import Path
from crewai import LLM

# ----- PATH CONFIGS
LSM_DOMAIN_INSTRUCTIONS = Path(__file__).resolve().parent / "crews" / "reprochecker_crew" / "skills" / "lsm_domain_instructions"
LSM_DOMAIN_INSTRUCTIONS.mkdir(exist_ok=True)

PDF_DIR = Path(__file__).resolve().parent.parent.parent / "publications"
PDF_DIR.mkdir(exist_ok=True)

INPUTS_PATH = PDF_DIR / "scopus_export_Jul_22_2026_query1.csv"

OUTPUT_DIR = Path(__file__).resolve().parent.parent.parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

#-------- LLM CONFIGS --------

### Local/Smaller LLM's

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

### Remote/Larger LLM's

## Anthropic Large LLM
# llm_large = LLM(
#     model="anthropic/claude-sonnet-5",
#     temperature=0
# )

### DeepSeek Large LLM
# llm_large = LLM(
#     model="deepseek/deepseek-v4-pro",  # This specific model ID
#     base_url="https://api.deepseek.com/v1",
#     temperature=0
# )

llm_large = LLM(
    model="ollama/qwen3",
    base_url="http://localhost:11434",
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