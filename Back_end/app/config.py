import os

# Embedding configurations
EMBED_MODEL = os.getenv("EMBED_MODEL", "models/gemini-embedding-2-preview")

# Semantic splitting configurations
SEMANTIC_BUFFER_SIZE = int(os.getenv("SEMANTIC_BUFFER_SIZE", "1"))
SEMANTIC_BREAKPOINT_PERCENTILE = int(os.getenv("SEMANTIC_BREAKPOINT_PERCENTILE", "95"))
SEMANTIC_FALLBACK_CHUNK_SIZE = int(os.getenv("SEMANTIC_FALLBACK_CHUNK_SIZE", "512"))
SEMANTIC_FALLBACK_CHUNK_OVERLAP = int(os.getenv("SEMANTIC_FALLBACK_CHUNK_OVERLAP", "50"))

