import os
import sys
from pathlib import Path

from llama_index.core import VectorStoreIndex, QueryBundle, Settings
from llama_index.vector_stores.pinecone import PineconeVectorStore
from llama_index.postprocessor.cohere_rerank import CohereRerank
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
# from llama_index.llms.ollama import Ollama
from llama_index.llms.groq import Groq
from pinecone import Pinecone

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for candidate in (str(PROJECT_ROOT), str(PROJECT_ROOT.parent)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from app.config import EMBED_MODEL
from dotenv import load_dotenv

load_dotenv()

# ── Singleton cache ────────────────────────────────────────────────────────────
# Built once on first call, reused for all subsequent requests.
_query_engine = None


def get_query_engine():
    """
    Load the VectorStoreIndex from Pinecone and set up a query engine with Cohere Re-rank.
    Cached as a module-level singleton — built only once per server process.
    """
    global _query_engine
    if _query_engine is not None:
        return _query_engine

    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        print("Warning: PINECONE_API_KEY not found. Cannot connect to Pinecone.")
        return None
        
    index_name = os.getenv("PINECONE_INDEX_NAME", "lyraa-support")
    index_name = index_name.lower().replace("_", "-")
    
    pc = Pinecone(api_key=api_key)
    
    try:
        pinecone_index = pc.Index(index_name)
    except Exception as e:
        print(f"Error accessing Pinecone index '{index_name}': {e}")
        return None

    vector_store = PineconeVectorStore(pinecone_index=pinecone_index)
    
    groq_api_key = os.getenv("GROQ_API_KEY")
    groq_model = os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")  # fast Groq model
    Settings.llm = Groq(model=groq_model, api_key=groq_api_key)

    # Set embed model in Settings for query embeddings
    google_api_key = os.getenv("GOOGLE_API_KEY")
    embedding_model = GoogleGenAIEmbedding(model_name=EMBED_MODEL, api_key=google_api_key)
    Settings.embed_model = embedding_model
    
    index = VectorStoreIndex.from_vector_store(vector_store)
    
    # Set up Cohere re-ranker
    cohere_api_key = os.environ.get("COHERE_API_KEY")
    if cohere_api_key:
        # top_k=5 (down from 10) → fewer candidates sent to Cohere = faster re-rank
        cohere_rerank = CohereRerank(api_key=cohere_api_key, top_n=3)
        node_postprocessors = [cohere_rerank]
    else:
        print("Warning: COHERE_API_KEY not found. Skipping re-ranking step.")
        node_postprocessors = []

    query_engine = index.as_query_engine(
        similarity_top_k=5,          # reduced from 10 — less context sent to Cohere
        node_postprocessors=node_postprocessors,
        streaming=True,              # enables response_gen for token-by-token streaming
    )

    _query_engine = query_engine  # cache for all future requests
    print("[RAG] Query engine initialized and cached.")
    return _query_engine

def query_rag(question: str):
    engine = get_query_engine()
    if not engine:
        return "The knowledge base is empty or not configured."
    
    response = engine.query(question)
    return str(response)
