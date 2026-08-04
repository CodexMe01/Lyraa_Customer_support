"""
endpoints.py
~~~~~~~~~~~~
FastAPI routes for the customer support agent backend.

Cloud storage changes (Cloudinary):
  - /upload         → stores file in Cloudinary under {user_id}/{type}/ folder
  - /documents      → lists files from Cloudinary for a given user_id
  - /documents/{id} → deletes by Cloudinary public_id
  - /documents/download/{public_id} → proxies the file back to the caller

Upload and ingestion remain independent steps.
"""

import os
import base64
import shutil
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlparse, quote

from fastapi import APIRouter, HTTPException, UploadFile, File, Query, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from tavily import TavilyClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for candidate in (str(PROJECT_ROOT), str(PROJECT_ROOT.parent)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from agent.bot import chat_with_agent, stream_chat_with_agent
from ingestion.pipeline import run_ingestion_pipeline
from storage.cloudinary_storage import CloudinaryStorage

from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

# Local data dir is still used as a staging area for the /ingest endpoint.
DATA_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "data"
)
os.makedirs(DATA_DIR, exist_ok=True)

# Singleton storage client
_storage = CloudinaryStorage()

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class ChatRequest(BaseModel):
    message: str
    user_id: str = "anonymous"

class ChatResponse(BaseModel):
    response: str
    intent: str = "unknown"

class LinkRequest(BaseModel):
    url: str
    user_id: str = "anonymous"

class IngestRequest(BaseModel):
    mode: str = "all"          # "all" | "recent"
    user_id: str = "anonymous"

# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
def api_chat(request: ChatRequest):
    try:
        result = chat_with_agent(request.message)
        return ChatResponse(response=result["response"], intent=result["intent"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def api_chat_stream(request: ChatRequest):
    """
    Streaming chat endpoint using Server-Sent Events (SSE).
    Each SSE event payload: {"token": str, "intent": str, "done": bool}
    """
    return StreamingResponse(
        stream_chat_with_agent(request.message),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )

# ---------------------------------------------------------------------------
# Upload  →  Cloudinary (per-user, per-type folder, 24-hr TTL tagged)
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    user_id: str = Query(default="anonymous", description="User identifier"),
):
    """
    Upload a file to Cloudinary.

    The file is stored at:
        customer_support/{user_id}/{type}/{filename}

    File types → folders:
        PDFs          → pdfs/
        Images        → images/
        Word/ODT      → docs/
        Excel/CSV     → spreadsheets/
        TXT/MD        → text/
        Everything else → others/

    Files are automatically deleted after **24 hours**.
    Upload and ingestion are intentionally separate steps — call /ingest
    afterwards to index the document for RAG.
    """
    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        result = _storage.upload_file(
            file_bytes=file_bytes,
            filename=file.filename,
            user_id=user_id,
        )
        return {
            "message": f"Successfully uploaded '{file.filename}' to cloud storage.",
            "public_id": result["public_id"],
            "secure_url": result["secure_url"],
            "folder": result["folder"],
            "user_id": result["user_id"],
            "uploaded_at": result["uploaded_at"],
            "size_bytes": result["size"],
            "expires_in": "24 hours",
            "note": "Call POST /api/ingest to index this file for RAG search.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# List documents from Cloudinary
# ---------------------------------------------------------------------------

@router.get("/documents")
def list_documents(
    user_id: str = Query(default="anonymous", description="Filter by user ID"),
):
    """
    List all cloud-stored files for *user_id*.

    Returns each file with:
      - public_id, secure_url, folder, filename, size
      - uploaded_at (ISO-8601 UTC)
      - expires_in_seconds  (countdown to 24-hr auto-delete)
    """
    try:
        files = _storage.list_files(user_id=user_id)
        return {
            "user_id": user_id,
            "total": len(files),
            "documents": files,
        }
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Download a file from Cloudinary (proxied)
# ---------------------------------------------------------------------------

@router.get("/documents/download")
def download_document(
    public_id: str = Query(..., description="Cloudinary public_id of the file"),
    resource_type: str = Query(default="raw", description='"raw" or "image"'),
):
    """
    Download a file from Cloudinary by its public_id.
    The file content is streamed back to the caller.
    """
    try:
        file_bytes = _storage.download_file(public_id, resource_type=resource_type)
        filename = public_id.split("/")[-1]
        return Response(
            content=file_bytes,
            media_type="application/octet-stream",
            headers={
                "Content-Disposition": f'attachment; filename="{filename}"',
                "Content-Length": str(len(file_bytes)),
            },
        )
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Delete a document from Cloudinary
# ---------------------------------------------------------------------------

@router.delete("/documents")
def delete_document(
    public_id: str = Query(..., description="Cloudinary public_id of the file"),
    resource_type: str = Query(default="raw", description='"raw" or "image"'),
):
    """
    Delete a file from Cloudinary by its public_id.
    """
    try:
        result = _storage.delete_file(public_id, resource_type=resource_type)
        if result.get("result") == "not found":
            raise HTTPException(status_code=404, detail="Document not found in cloud storage.")
        return {
            "message": f"Successfully deleted '{public_id}' from cloud storage.",
            "public_id": public_id,
            "result": result.get("result"),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Add link (web scrape via Tavily) → local staging + Cloudinary
# ---------------------------------------------------------------------------

@router.post("/add-link")
def add_link(request: LinkRequest):
    """
    Scrape a web URL via Tavily, save the extracted text to Cloudinary
    (text/ folder) and a local staging copy for immediate ingestion if needed.
    """
    try:
        tavily_api_key = os.getenv("TAVILY_API_KEY")
        if not tavily_api_key:
            raise HTTPException(
                status_code=500,
                detail="TAVILY_API_KEY environment variable is not set.",
            )

        client = TavilyClient(api_key=tavily_api_key)
        print(f"Scraping URL: {request.url} via Tavily...")
        response = client.extract(urls=[request.url], extract_depth="advanced")
        results = response.get("results", [])
        if not results:
            raise HTTPException(
                status_code=400,
                detail="Failed to extract content from the URL.",
            )

        content = results[0].get("raw_content", "")
        if not content:
            raise HTTPException(
                status_code=400,
                detail="No content extracted from the URL.",
            )

        parsed_url = urlparse(request.url)
        clean_netloc = parsed_url.netloc.replace(".", "_")
        filename = f"web_{clean_netloc}_{abs(hash(request.url)) % 10000}.txt"
        file_bytes = content.encode("utf-8")

        # Upload text file to Cloudinary
        cloud_result = _storage.upload_file(
            file_bytes=file_bytes,
            filename=filename,
            user_id=request.user_id,
        )

        # Also write to local staging dir so /ingest can pick it up
        local_path = os.path.join(DATA_DIR, filename)
        with open(local_path, "w", encoding="utf-8") as f:
            f.write(content)

        return {
            "message": f"Extracted content from {request.url}",
            "filename": filename,
            "public_id": cloud_result["public_id"],
            "secure_url": cloud_result["secure_url"],
            "note": "Call POST /api/ingest to index this content for RAG search.",
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Ingest  (unchanged — reads from local staging dir)
# ---------------------------------------------------------------------------

@router.post("/ingest")
def trigger_ingest(request: IngestRequest = None):
    """
    Trigger the RAG ingestion pipeline to index documents from the local
    staging directory into Pinecone.

    This is intentionally separate from /upload.  Workflow:
      1. POST /upload  →  file stored in Cloudinary
      2. POST /ingest  →  local staging dir indexed into Pinecone
    """
    mode = (
        request.mode
        if request and request.mode in ("all", "recent")
        else "all"
    )
    try:
        user_id = request.user_id if request else "anonymous"
        print(f"Starting document ingestion for user '{user_id}' (mode={mode})...")
        index = run_ingestion_pipeline(data_dir=DATA_DIR, mode=mode, user_id=user_id)
        if index is None:
            return {"message": f"Ingestion ({mode}) completed but no documents found."}
        return {
            "message": f"Ingestion ({mode}) successfully completed! Vector index updated in Pinecone."
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ---------------------------------------------------------------------------
# Manual cleanup trigger (admin use)
# ---------------------------------------------------------------------------

@router.post("/cleanup")
def manual_cleanup():
    """
    Manually trigger the 24-hour file expiry cleanup.
    Normally this runs automatically every hour via the background scheduler.
    """
    try:
        result = _storage.delete_expired_files()
        return {
            "message": "Cleanup completed.",
            "deleted_count": len(result["deleted"]),
            "deleted": result["deleted"],
            "errors": result["errors"],
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
