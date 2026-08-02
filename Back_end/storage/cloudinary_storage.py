"""
cloudinary_storage.py
~~~~~~~~~~~~~~~~~~~~~
Cloudinary cloud storage backend for the customer support agent.

Folder layout per user (auto-partitioned by file type):
    customer_support/{user_id}/pdfs/
    customer_support/{user_id}/images/
    customer_support/{user_id}/docs/
    customer_support/{user_id}/spreadsheets/
    customer_support/{user_id}/text/
    customer_support/{user_id}/others/

Files are tagged with their upload timestamp so the 24-hour
auto-cleanup job can identify and delete expired assets.
"""

from __future__ import annotations

import io
import os
import logging
from datetime import datetime, timezone
from typing import Optional

import cloudinary
import cloudinary.uploader
import cloudinary.api
import requests
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Extension → subfolder mapping
# ---------------------------------------------------------------------------
_FOLDER_MAP: dict[str, str] = {
    # PDFs
    ".pdf": "pdfs",
    # Images
    ".png": "images",
    ".jpg": "images",
    ".jpeg": "images",
    ".gif": "images",
    ".webp": "images",
    ".bmp": "images",
    ".tiff": "images",
    ".svg": "images",
    # Word / LibreOffice documents
    ".doc": "docs",
    ".docx": "docs",
    ".odt": "docs",
    ".rtf": "docs",
    # Spreadsheets
    ".xls": "spreadsheets",
    ".xlsx": "spreadsheets",
    ".csv": "spreadsheets",
    # Plain text / Markdown
    ".txt": "text",
    ".md": "text",
}

ROOT_FOLDER = "customer_support"


def _configure() -> None:
    """Configure Cloudinary SDK from environment variables (idempotent)."""
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True,
    )


def get_folder_for_file(filename: str, user_id: str = "anonymous") -> str:
    """
    Return the Cloudinary folder path for *filename* scoped to *user_id*.

    Example:
        get_folder_for_file("report.pdf", "user_42")
        → "customer_support/user_42/pdfs"
    """
    ext = os.path.splitext(filename)[-1].lower()
    sub = _FOLDER_MAP.get(ext, "others")
    return f"{ROOT_FOLDER}/{user_id}/{sub}"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

class CloudinaryStorage:
    """
    Thin wrapper around the Cloudinary Python SDK.

    All methods are synchronous (FastAPI will call them in a thread pool via
    `run_in_executor` if needed for async routes).
    """

    def __init__(self) -> None:
        _configure()

    # ------------------------------------------------------------------
    # Upload
    # ------------------------------------------------------------------

    def upload_file(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: str = "anonymous",
    ) -> dict:
        """
        Upload *file_bytes* to Cloudinary under the correct type-folder for
        *user_id*.

        Returns a dict with:
            public_id   – Cloudinary asset identifier (used for deletion)
            secure_url  – HTTPS download URL
            folder      – folder path inside Cloudinary
            user_id     – owner
            uploaded_at – ISO-8601 UTC timestamp (used for 24-hr cleanup)
            filename    – original filename
            size        – bytes uploaded
            resource_type – "image" | "raw" (Cloudinary concept)
        """
        folder = get_folder_for_file(filename, user_id)
        # Strip extension from display name; Cloudinary appends it automatically.
        display_name = os.path.splitext(filename)[0]
        ext = os.path.splitext(filename)[-1].lower()

        # Cloudinary requires "raw" resource_type for non-image/non-video files.
        resource_type = "image" if ext in {".png", ".jpg", ".jpeg", ".gif",
                                            ".webp", ".bmp", ".tiff"} else "raw"

        now_iso = datetime.now(timezone.utc).isoformat()

        result = cloudinary.uploader.upload(
            io.BytesIO(file_bytes),
            folder=folder,
            public_id=display_name,
            resource_type=resource_type,
            overwrite=False,
            use_filename=True,
            unique_filename=True,
            # Store metadata so the cleanup job can filter by upload time.
            context=f"user_id={user_id}|uploaded_at={now_iso}|original_filename={filename}",
            tags=[f"user_{user_id}", "customer_support", "auto_delete_24h"],
        )

        return {
            "public_id": result["public_id"],
            "secure_url": result["secure_url"],
            "folder": folder,
            "user_id": user_id,
            "uploaded_at": now_iso,
            "filename": filename,
            "size": result.get("bytes", len(file_bytes)),
            "resource_type": resource_type,
        }

    # ------------------------------------------------------------------
    # List
    # ------------------------------------------------------------------

    def list_files(self, user_id: Optional[str] = None) -> list[dict]:
        """
        List all files for *user_id* (or every file if None).

        Returns a list of dicts:
            public_id, secure_url, folder, filename, size,
            uploaded_at, resource_type, expires_in_seconds
        """
        prefix = (
            f"{ROOT_FOLDER}/{user_id}/" if user_id else f"{ROOT_FOLDER}/"
        )

        assets: list[dict] = []

        # Query both "image" and "raw" resource types
        for rtype in ("image", "raw"):
            next_cursor = None
            while True:
                kwargs: dict = {
                    "type": "upload",
                    "prefix": prefix,
                    "max_results": 100,
                    "context": True,
                    "tags": True,
                }
                if next_cursor:
                    kwargs["next_cursor"] = next_cursor

                try:
                    resp = cloudinary.api.resources(resource_type=rtype, **kwargs)
                except cloudinary.exceptions.AuthorizationRequired:
                    logger.error("Cloudinary credentials not configured.")
                    raise RuntimeError(
                        "Cloudinary is not configured. Set CLOUDINARY_CLOUD_NAME, "
                        "CLOUDINARY_API_KEY, CLOUDINARY_API_SECRET in .env"
                    )

                for r in resp.get("resources", []):
                    ctx = r.get("context", {}).get("custom", {})
                    uploaded_at_str = ctx.get("uploaded_at", r.get("created_at", ""))
                    original_filename = ctx.get("original_filename", r["public_id"].split("/")[-1])

                    # Calculate seconds until expiry (24 h after upload)
                    expires_in: Optional[int] = None
                    try:
                        uploaded_dt = datetime.fromisoformat(uploaded_at_str)
                        age_secs = (datetime.now(timezone.utc) - uploaded_dt).total_seconds()
                        expires_in = max(0, int(86400 - age_secs))
                    except Exception:
                        pass

                    assets.append({
                        "public_id": r["public_id"],
                        "secure_url": r.get("secure_url", ""),
                        "folder": "/".join(r["public_id"].split("/")[:-1]),
                        "filename": original_filename,
                        "size": r.get("bytes", 0),
                        "uploaded_at": uploaded_at_str,
                        "resource_type": rtype,
                        "expires_in_seconds": expires_in,
                    })

                next_cursor = resp.get("next_cursor")
                if not next_cursor:
                    break

        return assets

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_file(self, public_id: str, resource_type: str = "raw") -> dict:
        """
        Delete a single file by its Cloudinary *public_id*.

        *resource_type* must match the type used during upload ("image" or "raw").
        """
        result = cloudinary.uploader.destroy(
            public_id, resource_type=resource_type, invalidate=True
        )
        return {"public_id": public_id, "result": result.get("result", "unknown")}

    # ------------------------------------------------------------------
    # Download (for ingestion pipeline)
    # ------------------------------------------------------------------

    def download_file(self, public_id: str, resource_type: str = "raw") -> bytes:
        """
        Download a file from Cloudinary and return its raw bytes.
        Useful for feeding files into the Pinecone ingestion pipeline
        without needing a local copy.
        """
        # Build the URL using the Cloudinary API
        resources = cloudinary.api.resource(public_id, resource_type=resource_type)
        url = resources.get("secure_url")
        if not url:
            raise FileNotFoundError(f"No secure_url found for public_id={public_id}")

        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        return resp.content

    # ------------------------------------------------------------------
    # 24-hour cleanup (called by the APScheduler job)
    # ------------------------------------------------------------------

    def delete_expired_files(self) -> dict:
        """
        Scan all assets tagged 'auto_delete_24h' and delete those uploaded
        more than 24 hours ago.

        Returns a summary: {"deleted": [...], "errors": [...]}
        """
        deleted: list[str] = []
        errors: list[str] = []
        now = datetime.now(timezone.utc)

        for rtype in ("image", "raw"):
            next_cursor = None
            while True:
                kwargs: dict = {
                    "type": "upload",
                    "prefix": f"{ROOT_FOLDER}/",
                    "max_results": 100,
                    "context": True,
                    "tags": True,
                }
                if next_cursor:
                    kwargs["next_cursor"] = next_cursor

                try:
                    resp = cloudinary.api.resources(resource_type=rtype, **kwargs)
                except Exception as exc:
                    logger.error("Cloudinary cleanup error: %s", exc)
                    break

                for r in resp.get("resources", []):
                    ctx = r.get("context", {}).get("custom", {})
                    uploaded_at_str = ctx.get("uploaded_at", "")
                    tags = r.get("tags", [])

                    if "auto_delete_24h" not in tags:
                        continue

                    try:
                        uploaded_dt = datetime.fromisoformat(uploaded_at_str)
                        age_secs = (now - uploaded_dt).total_seconds()
                        if age_secs >= 86400:  # 24 hours
                            pub_id = r["public_id"]
                            cloudinary.uploader.destroy(
                                pub_id, resource_type=rtype, invalidate=True
                            )
                            deleted.append(pub_id)
                            logger.info("Auto-deleted expired asset: %s", pub_id)
                    except Exception as exc:
                        errors.append(str(exc))
                        logger.warning("Error during cleanup: %s", exc)

                next_cursor = resp.get("next_cursor")
                if not next_cursor:
                    break

        return {"deleted": deleted, "errors": errors}
