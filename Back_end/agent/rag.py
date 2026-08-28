import os
import sys
from pathlib import Path
from typing import Optional

from llama_index.core import VectorStoreIndex, QueryBundle, Settings
from llama_index.vector_stores.pinecone import PineconeVectorStore
from llama_index.postprocessor.cohere_rerank import CohereRerank
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from llama_index.llms.groq import Groq
from pinecone import Pinecone

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for candidate in (str(PROJECT_ROOT), str(PROJECT_ROOT.parent)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from app.config import EMBED_MODEL
from dotenv import load_dotenv

load_dotenv()

from app.tracing import get_tracer
tracer = get_tracer("agent.rag")

# ── Per-tenant query engine cache ──────────────────────────────────────────────
# Dict keyed by tenant_id (str UUID). Built on first request, reused thereafter.
_query_engines: dict[str, object] = {}

# ── Shared singletons (Pinecone index + embedding model) ──────────────────────
_pinecone_index = None
_embedding_model = None


def _get_pinecone_index():
    """Return a cached Pinecone Index object (shared across tenants)."""
    global _pinecone_index
    if _pinecone_index is not None:
        return _pinecone_index

    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        print("Warning: PINECONE_API_KEY not found. Cannot connect to Pinecone.")
        return None

    index_name = os.getenv("PINECONE_INDEX_NAME", "lyraa-support")
    index_name = index_name.lower().replace("_", "-")

    pc = Pinecone(api_key=api_key)
    try:
        _pinecone_index = pc.Index(index_name)
        print(f"[RAG] Connected to Pinecone index '{index_name}'.")
    except Exception as e:
        print(f"[RAG] Error accessing Pinecone index '{index_name}': {e}")
        return None

    return _pinecone_index


def _get_embedding_model():
    """Return a cached Google GenAI embedding model (shared across tenants)."""
    global _embedding_model
    if _embedding_model is not None:
        return _embedding_model

    google_api_key = os.getenv("GOOGLE_API_KEY")
    _embedding_model = GoogleGenAIEmbedding(model_name=EMBED_MODEL, api_key=google_api_key)
    return _embedding_model


def get_query_engine(tenant_id: str):
    """
    Return a query engine scoped to *tenant_id*.

    Each tenant gets their own Pinecone namespace (``tenant_<tenant_id>``) so
    their vectors are fully isolated from all other tenants.

    The engine is cached in ``_query_engines`` after the first build.
    """
    tenant_id = str(tenant_id)

    if tenant_id in _query_engines:
        return _query_engines[tenant_id]

    pinecone_index = _get_pinecone_index()
    if pinecone_index is None:
        return None

    embedding_model = _get_embedding_model()

    # Configure global LlamaIndex Settings (safe to set repeatedly; they're process-level)
    groq_api_key = os.getenv("GROQ_API_KEY")
    groq_model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    Settings.llm = Groq(model=groq_model, api_key=groq_api_key)
    Settings.embed_model = embedding_model

    # ── Tenant-scoped vector store ─────────────────────────────────────────────
    namespace = f"tenant_{tenant_id}"
    vector_store = PineconeVectorStore(
        pinecone_index=pinecone_index,
        namespace=namespace,
    )

    index = VectorStoreIndex.from_vector_store(vector_store)

    # ── Cohere re-ranker ───────────────────────────────────────────────────────
    cohere_api_key = os.environ.get("COHERE_API_KEY")
    if cohere_api_key:
        cohere_rerank = CohereRerank(api_key=cohere_api_key, top_n=3)
        node_postprocessors = [cohere_rerank]
    else:
        print("[RAG] Warning: COHERE_API_KEY not found. Skipping re-ranking.")
        node_postprocessors = []

    query_engine = index.as_query_engine(
        similarity_top_k=5,
        node_postprocessors=node_postprocessors,
        streaming=True,
    )

    _query_engines[tenant_id] = query_engine
    print(f"[RAG] Query engine for tenant '{tenant_id}' (namespace: {namespace}) built and cached.")
    return query_engine


def invalidate_engine(tenant_id: str) -> None:
    """
    Remove a tenant's cached query engine.

    Call this after a successful document ingestion so the next request
    picks up the freshly indexed vectors.
    """
    _query_engines.pop(str(tenant_id), None)
    print(f"[RAG] Invalidated cached engine for tenant '{tenant_id}'.")


def query_rag(question: str, tenant_id: str) -> str:
    """Query the tenant-scoped RAG knowledge base and return a string answer."""
    with tracer.start_as_current_span("rag_query") as span:
        span.set_attribute("tenant_id", tenant_id)
        span.set_attribute("query.text", question)
        
        engine = get_query_engine(tenant_id)
        if not engine:
            return "The knowledge base is empty or not configured for your account."

        response = engine.query(question)
        return str(response)
