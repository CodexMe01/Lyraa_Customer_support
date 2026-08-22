import os
import sys
from pathlib import Path
from typing import Optional

from llama_index.core import VectorStoreIndex, Document, Settings
from llama_index.core import StorageContext
from llama_index.vector_stores.pinecone import PineconeVectorStore
from ingestion.loaders import load_local_documents
from ingestion.loaders import load_pdf_with_ocr, load_image_with_ocr
from llama_index.core.node_parser import SemanticSplitterNodeParser, SentenceSplitter
from llama_index.embeddings.google_genai import GoogleGenAIEmbedding
from pinecone import Pinecone, ServerlessSpec
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for candidate in (str(PROJECT_ROOT), str(PROJECT_ROOT.parent)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from storage.cloudinary_storage import CloudinaryStorage

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

def create_or_update_index(documents: list[Document], tenant_id: str) -> VectorStoreIndex | None:
    """
    Ingest *documents* into Pinecone under the namespace ``tenant_<tenant_id>``.

    Each tenant's vectors are fully isolated from one another via Pinecone
    namespaces.  The shared index name is taken from PINECONE_INDEX_NAME.
    """
    if not documents:
        print("No documents to ingest.")
        return None

    google_api_key = os.getenv("GOOGLE_API_KEY")
    embedding_model = GoogleGenAIEmbedding(model_name=EMBED_MODEL, api_key=google_api_key)
    Settings.embed_model = embedding_model

    # ── Pinecone setup ─────────────────────────────────────────────────────────
    api_key = os.getenv("PINECONE_API_KEY")
    if not api_key:
        raise ValueError("PINECONE_API_KEY environment variable is not set. Please set it in .env.")

    index_name = os.getenv("PINECONE_INDEX_NAME", "lyraa-support")
    index_name = index_name.lower().replace("_", "-")

    pc = Pinecone(api_key=api_key)

    existing_indexes = [idx.name for idx in pc.list_indexes()]
    if index_name not in existing_indexes:
        dimension = len(embedding_model.get_text_embedding("test"))
        print(f"Creating Pinecone index '{index_name}' with dimension {dimension}...")
        pc.create_index(
            name=index_name,
            dimension=dimension,
            metric="cosine",
            spec=ServerlessSpec(cloud="aws", region="us-east-1"),
        )
    else:
        print(f"Index '{index_name}' already exists. Connecting...")

    pinecone_index = pc.Index(index_name)

    # ── Tenant-scoped namespace ────────────────────────────────────────────────
    namespace = f"tenant_{tenant_id}"
    print(f"[Ingest] Using Pinecone namespace '{namespace}' for tenant '{tenant_id}'.")

    vector_store = PineconeVectorStore(
        pinecone_index=pinecone_index,
        namespace=namespace,
    )
    storage_context = StorageContext.from_defaults(vector_store=vector_store)

    index = VectorStoreIndex.from_documents(documents, storage_context=storage_context)
    return index

def run_ingestion_pipeline(
    data_dir: str = "./data",
    mode: str = "all",
    storage: Optional[CloudinaryStorage] = None,
    tenant_id: str = "anonymous",
    tenant_slug: str = "anonymous",
):
    """
    Run the ingestion pipeline for both local files and Cloudinary-backed uploads.

    Args:
        data_dir:    Local staging directory used as a fallback.
        mode:        'all' to process every file, 'recent' for last-24h only.
        storage:     Cloudinary storage client (optional override for testing).
        tenant_id:   Tenant UUID — used as the Pinecone namespace key.
        tenant_slug: Tenant slug — used as the Cloudinary folder prefix.
    """
    print(f"[Ingest] Loading documents (mode={mode}, tenant={tenant_id})...")

    storage_client = storage or CloudinaryStorage()
    docs = []

    # ── Fetch from Cloudinary (tenant-prefixed folder) ─────────────────────────
    try:
        cloud_documents = storage_client.list_files(user_id=tenant_slug)
        if cloud_documents:
            print(f"[Ingest] Found {len(cloud_documents)} Cloudinary document(s) for tenant '{tenant_slug}'.")
            for asset in cloud_documents:
                public_id = asset.get("public_id")
                resource_type = asset.get("resource_type", "raw")
                if not public_id:
                    continue
                try:
                    file_bytes = storage_client.download_file(public_id, resource_type=resource_type)
                except Exception as exc:
                    print(f"[Ingest] Skipping Cloudinary asset {public_id}: {exc}")
                    continue

                filename = asset.get("filename") or public_id.split("/")[-1]
                if not file_bytes:
                    continue
                docs.extend(load_documents_from_bytes(file_bytes, filename, mode=mode))
    except Exception as exc:
        print(f"[Ingest] Cloudinary ingestion unavailable: {exc}")

    # ── Fallback: local staging dir ────────────────────────────────────────────
    if not docs:
        docs = load_local_documents(data_dir, mode=mode)

    if docs:
        print(f"[Ingest] Loaded {len(docs)} documents. Building index for tenant '{tenant_id}'...")
        index = create_or_update_index(docs, tenant_id=tenant_id)
        print("[Ingest] Ingestion complete.")
        return index

    print("[Ingest] Skipped — no data found.")
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
