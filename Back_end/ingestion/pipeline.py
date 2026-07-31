import os
from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.core import StorageContext
from llama_index.vector_stores.pinecone import PineconeVectorStore
from ingestion.loaders import load_local_documents
from llama_index.core.node_parser import SemanticSplitterNodeParser, SentenceSplitter
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv

load_dotenv()

from app.config import (
    EMBED_MODEL,
    SEMANTIC_BUFFER_SIZE,
    SEMANTIC_BREAKPOINT_PERCENTILE,
    SEMANTIC_FALLBACK_CHUNK_SIZE,
    SEMANTIC_FALLBACK_CHUNK_OVERLAP,
)

def build_splitter(embed_model) -> SemanticSplitterNodeParser:
    fallback = SentenceSplitter(
        chunk_size=SEMANTIC_FALLBACK_CHUNK_SIZE,
        chunk_overlap=SEMANTIC_FALLBACK_CHUNK_OVERLAP,
    )
    return SemanticSplitterNodeParser(
        buffer_size=SEMANTIC_BUFFER_SIZE,
        breakpoint_percentile_threshold=SEMANTIC_BREAKPOINT_PERCENTILE,
        embed_model=embed_model,
        # sub_node_parsers splits oversized semantic chunks as a safety net
        sub_node_parsers=[fallback],
    )

def create_or_update_index(documents: list[Document], collection_name: str = "lyraa-support"):
    """
    Ingest documents into Pinecone and create/update a VectorStoreIndex.
    """
    if not documents:
        print("No documents to ingest.")
        return None
    
    google_api_key = os.getenv("GOOGLE_API_KEY")
    embedding_model = GoogleGenAIEmbedding(model_name=EMBED_MODEL, api_key=google_api_key)
    Settings.embed_model = embedding_model

    # Initialize Pinecone client
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("PINECONE_API_KEY environment variable is not set. Please set it in .env.")
        
    index_name = os.getenv("PINECONE_INDEX_NAME", collection_name)
    # Pinecone indexes must be lowercase, numbers, and hyphens only
    index_name = index_name.lower().replace("_", "-")
    
    pc = Pinecone(api_key=api_key)
    
    # Check if index exists, create if not
    existing_indexes = [idx.name for idx in pc.list_indexes()]
    if index_name not in existing_indexes:
        # Determine embedding dimension
        dimension = len(embedding_model.get_text_embedding("test"))
        print(f"Creating Pinecone index '{index_name}' with dimension {dimension}...")
        pc.create_index(
            name=index_name,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1")
        )
    else:
        print(f"Index '{index_name}' already exists. Connecting...")
        
    pinecone_index = pc.Index(index_name)
    
    # Assign pinecone as the vector store
    vector_store = PineconeVectorStore(pinecone_index=pinecone_index)
    storage_context = StorageContext.from_defaults(vector_store=vector_store)
    
    # Build the index
    index = VectorStoreIndex.from_documents(
        documents, storage_context=storage_context
    )
    
    return index

def run_ingestion_pipeline(data_dir: str = "./data", mode: str = "all"):
    """Run the complete pipeline to load documents and build the index.
    
    Args:
        data_dir: Path to the directory containing documents.
        mode: 'all' to process every file, 'recent' to process only files
              modified in the last 24 hours.
    """
    print(f"Loading documents (mode={mode})...")
    docs = load_local_documents(data_dir, mode=mode)
    
    if docs:
        print(f"Loaded {len(docs)} documents. Building index...")
        index = create_or_update_index(docs)
        print("Ingestion complete.")
        return index
    else:
        print("Ingestion skipped - no data.")
        return None

if __name__ == "__main__":
    run_ingestion_pipeline()
