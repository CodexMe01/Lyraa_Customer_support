"""
endpoints.py
~~~~~~~~~~~~
FastAPI routes for the Lyraa multi-tenant customer support agent backend.

All routes resolve the caller's Tenant via get_tenant_from_request, which
accepts either a Supabase JWT (Authorization: Bearer) or an API key
(X-API-Key header).  Data is fully isolated per tenant:
  - Pinecone namespace  : tenant_<tenant.id>
  - Cloudinary prefix   : tenant_<tenant.slug>/
  - Agent / RAG cache   : keyed by tenant.id
"""

import os
import sys
import time
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from tavily import TavilyClient

PROJECT_ROOT = Path(__file__).resolve().parents[2]
for candidate in (str(PROJECT_ROOT), str(PROJECT_ROOT.parent)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)

from agent.bot import chat_with_agent, stream_chat_with_agent
from agent.rag import invalidate_engine
from ingestion.pipeline import run_ingestion_pipeline
from storage.supabase_storage import SupabaseStorage

from app.auth import get_tenant_from_request
from app.db import get_db
from app.models import Tenant, UsageLog
from app.schemas import ChatRequest, ChatResponse, IngestRequest, LinkRequest

from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

# Local staging dir for the /ingest endpoint
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Singleton Supabase storage client
_storage = SupabaseStorage()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _log_usage(
    db: AsyncSession,
    tenant: Tenant,
    intent: str,
    session_id: str | None,
    response_ms: int,
) -> None:
    """Append a row to usage_logs (best-effort — never raises)."""
    try:
        log = UsageLog(
            tenant_id=tenant.id,
            session_id=session_id,
            intent=intent,
            response_ms=response_ms,
        )
        db.add(log)
        await db.commit()
    except Exception as exc:
        print(f"[Usage] Failed to log usage: {exc}")


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------

@router.post("/chat", response_model=ChatResponse)
async def api_chat(
    request: ChatRequest,
    tenant: Tenant = Depends(get_tenant_from_request),
    db: AsyncSession = Depends(get_db),
):
    """Non-streaming chat endpoint. Returns the full response at once."""
    t0 = time.monotonic()
    try:
        result = chat_with_agent(
            message=request.message,
            tenant_id=str(tenant.id),
            agent_config=tenant.agent_config,
        )
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        await _log_usage(db, tenant, result.get("intent", "unknown"), request.session_id, elapsed_ms)
        return ChatResponse(response=result["response"], intent=result["intent"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/chat/stream")
async def api_chat_stream(
    request: ChatRequest,
    tenant: Tenant = Depends(get_tenant_from_request),
    db: AsyncSession = Depends(get_db),
):
    """
    Streaming chat endpoint using Server-Sent Events (SSE).
    Each event: data: {"token": str, "intent": str, "done": bool}
    """
    t0 = time.monotonic()

    async def _generator():
        last_intent = "unknown"
        async for chunk in stream_chat_with_agent(
            message=request.message,
            tenant_id=str(tenant.id),
            agent_config=tenant.agent_config,
        ):
            # Peek at the last SSE line to extract intent for logging
            if '"done": true' in chunk or '"done":true' in chunk:
                import json as _json
                try:
                    data_str = chunk.removeprefix("data: ").strip()
                    last_intent = _json.loads(data_str).get("intent", "unknown")
                except Exception:
                    pass
            yield chunk
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        await _log_usage(db, tenant, last_intent, request.session_id, elapsed_ms)

    return StreamingResponse(
        _generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ---------------------------------------------------------------------------
# Upload → Supabase (tenant-scoped prefix)
# ---------------------------------------------------------------------------

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    tenant: Tenant = Depends(get_tenant_from_request),
):
    """
    Upload a file to Supabase under the tenant's own folder:
        customer_support/tenant_<slug>/<type>/<filename>

    Call POST /api/ingest afterwards to index the file for RAG search.
    """
    try:
        file_bytes = await file.read()
        if not file_bytes:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        result = _storage.upload_file(
            file_bytes=file_bytes,
            filename=file.filename,
            user_id=f"tenant_{tenant.slug}",
        )
        return {
            "message": f"Successfully uploaded '{file.filename}' to cloud storage.",
            "public_id": result["public_id"],
            "secure_url": result["secure_url"],
            "folder": result["folder"],
            "tenant_slug": tenant.slug,
            "uploaded_at": result["uploaded_at"],
            "size_bytes": result["size"],
            "expires_in": "24 hours",
            "note": "Call POST /api/ingest to index this file for RAG search.",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# List documents
# ---------------------------------------------------------------------------

@router.get("/documents")
def list_documents(
    tenant: Tenant = Depends(get_tenant_from_request),
):
    """List all cloud-stored files for the authenticated tenant."""
    try:
        files = _storage.list_files(user_id=f"tenant_{tenant.slug}")
        return {
            "tenant_slug": tenant.slug,
            "total": len(files),
            "documents": files,
        }
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Download a file (proxied)
# ---------------------------------------------------------------------------

@router.get("/documents/download")
def download_document(
    public_id: str = Query(..., description="Cloudinary public_id of the file"),
    resource_type: str = Query(default="raw", description='"raw" or "image"'),
    tenant: Tenant = Depends(get_tenant_from_request),
):
    """Download a file from Cloudinary by its public_id."""
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
# Delete a document
# ---------------------------------------------------------------------------

@router.delete("/documents")
def delete_document(
    public_id: str = Query(..., description="Cloudinary public_id of the file"),
    resource_type: str = Query(default="raw", description='"raw" or "image"'),
    tenant: Tenant = Depends(get_tenant_from_request),
):
    """
    Delete a file from Cloudinary.
    Guards against cross-tenant deletion by checking the public_id prefix.
    """
    # Ensure the document belongs to this tenant
    expected_prefix = f"customer_support/tenant_{tenant.slug}/"
    if not public_id.startswith(expected_prefix):
        raise HTTPException(
            status_code=403,
            detail="You do not have permission to delete this document.",
        )
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
# Add link (web scrape via Tavily)
# ---------------------------------------------------------------------------

@router.post("/add-link")
def add_link(
    request: LinkRequest,
    tenant: Tenant = Depends(get_tenant_from_request),
):
    """
    Scrape a web URL via Tavily, save the extracted text to Cloudinary
    (under the tenant's folder) and a local staging copy for ingestion.
    """
    try:
        tavily_api_key = os.getenv("TAVILY_API_KEY")
        if not tavily_api_key:
            raise HTTPException(status_code=500, detail="TAVILY_API_KEY is not set.")

        client = TavilyClient(api_key=tavily_api_key)
        print(f"[Link] Scraping URL: {request.url} for tenant '{tenant.slug}'...")
        response = client.extract(urls=[request.url], extract_depth="advanced")
        results = response.get("results", [])
        if not results:
            raise HTTPException(status_code=400, detail="Failed to extract content from the URL.")

        content = results[0].get("raw_content", "")
        if not content:
            raise HTTPException(status_code=400, detail="No content extracted from the URL.")

        parsed_url = urlparse(request.url)
        clean_netloc = parsed_url.netloc.replace(".", "_")
        filename = f"web_{clean_netloc}_{abs(hash(request.url)) % 10000}.txt"
        file_bytes = content.encode("utf-8")

        cloud_result = _storage.upload_file(
            file_bytes=file_bytes,
            filename=filename,
            user_id=f"tenant_{tenant.slug}",
        )

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
# Ingest (tenant-scoped Pinecone namespace)
# ---------------------------------------------------------------------------

@router.post("/ingest")
async def trigger_ingest(
    request: IngestRequest = None,
    tenant: Tenant = Depends(get_tenant_from_request),
):
    """
    Trigger the RAG ingestion pipeline.

    Documents from Cloudinary (under the tenant's folder) are indexed into
    the tenant's isolated Pinecone namespace: tenant_<tenant.id>

    Workflow:
      1. POST /api/upload  → file stored in Cloudinary
      2. POST /api/ingest  → Cloudinary docs indexed into Pinecone
    """
    mode = (request.mode if request and request.mode in ("all", "recent") else "all")
    try:
        print(f"[Ingest] Starting for tenant '{tenant.slug}' (mode={mode})...")
        index = run_ingestion_pipeline(
            data_dir=DATA_DIR,
            mode=mode,
            tenant_id=str(tenant.id),
            tenant_slug=tenant.slug,
        )
        # Bust the cached query engine so next request uses fresh vectors
        invalidate_engine(str(tenant.id))

        if index is None:
            return {"message": f"Ingestion ({mode}) completed but no documents found."}
        return {
            "message": f"Ingestion ({mode}) successfully completed! Vector index updated in Pinecone.",
            "namespace": f"tenant_{tenant.id}",
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------------------------------------------
# Manual cleanup (admin)
# ---------------------------------------------------------------------------

@router.post("/cleanup")
def manual_cleanup(
    tenant: Tenant = Depends(get_tenant_from_request),
):
    """Manually trigger 24-hour file expiry cleanup for this tenant's Cloudinary assets."""
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
