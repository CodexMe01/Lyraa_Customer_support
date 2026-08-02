import os
from typing import Optional

from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.core import StorageContext
from llama_index.vector_stores.pinecone import PineconeVectorStore
from Back_end.ingestion.loaders import load_local_documents
from Back_end.ingestion.loaders import load_pdf_with_ocr, load_image_with_ocr
from llama_index.core.node_parser import SemanticSplitterNodeParser, SentenceSplitter
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv

from Back_end.storage.cloudinary_storage import CloudinaryStorage

load_dotenv()

try:
    from Back_end.app.config import (
        EMBED_MODEL,
        SEMANTIC_BUFFER_SIZE,
        SEMANTIC_BREAKPOINT_PERCENTILE,
        SEMANTIC_FALLBACK_CHUNK_SIZE,
        SEMANTIC_FALLBACK_CHUNK_OVERLAP,
    )
except ImportError:
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

def run_ingestion_pipeline(
    data_dir: str = "./data",
    mode: str = "all",
    storage: Optional[CloudinaryStorage] = None,
    user_id: str = "anonymous",
):
    """Run the ingestion pipeline for both local files and Cloudinary-backed uploads.

    Args:
        data_dir: Local staging directory used as a fallback.
        mode: 'all' to process every file, 'recent' to process only files
              modified in the last 24 hours.
        storage: Cloudinary storage client used to fetch uploaded assets.
        user_id: User scope for Cloudinary-backed documents.
    """
    print(f"Loading documents (mode={mode})...")

    storage_client = storage or CloudinaryStorage()
    docs = []

    try:
        cloud_documents = storage_client.list_files(user_id=user_id)
        if cloud_documents:
            print(f"Found {len(cloud_documents)} Cloudinary document(s) for user '{user_id}'.")
            for asset in cloud_documents:
                public_id = asset.get("public_id")
                resource_type = asset.get("resource_type", "raw")
                if not public_id:
                    continue
                try:
                    file_bytes = storage_client.download_file(public_id, resource_type=resource_type)
                except Exception as exc:  # pragma: no cover - defensive logging
                    print(f"Skipping Cloudinary asset {public_id}: {exc}")
                    continue

                filename = asset.get("filename") or public_id.split("/")[-1]
                if not file_bytes:
                    continue
                docs.extend(load_documents_from_bytes(file_bytes, filename, mode=mode))
    except Exception as exc:
        print(f"Cloudinary ingestion unavailable: {exc}")

    if not docs:
        docs = load_local_documents(data_dir, mode=mode)

    if docs:
        print(f"Loaded {len(docs)} documents. Building index...")
        index = create_or_update_index(docs)
        print("Ingestion complete.")
        return index

    print("Ingestion skipped - no data.")
    return None


def load_documents_from_bytes(file_bytes: bytes, filename: str, mode: str = "all"):
    """Load documents from in-memory bytes by delegating to the existing loaders."""
    import tempfile
    from pathlib import Path

    suffix = os.path.splitext(filename)[1].lower()
    temp_dir = tempfile.mkdtemp(prefix="cloudinary_ingest_", dir=os.getcwd())
    temp_path = os.path.join(temp_dir, filename)

    try:
        with open(temp_path, "wb") as handle:
            handle.write(file_bytes)

        if suffix == ".pdf":
            return load_pdf_with_ocr(temp_path, "document", filename)
        if suffix in {".png", ".jpg", ".jpeg", ".bmp", ".tiff"}:
            return load_image_with_ocr(temp_path, filename)

        try:
            text = file_bytes.decode("utf-8")
            if text.strip():
                from llama_index.core import Document as LlamaDocument
                return [LlamaDocument(text=text, metadata={"source_file": filename, "doc_category": "cloudinary_document"})]
        except Exception:
            pass

        return load_local_documents(temp_dir, mode=mode)
    finally:
        for item in Path(temp_dir).glob("*"):
            try:
                item.unlink()
            except IsADirectoryError:
                continue
        try:
            os.rmdir(temp_dir)
        except OSError:
            pass

if __name__ == "__main__":
    run_ingestion_pipeline()
