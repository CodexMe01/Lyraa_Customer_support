"""
supabase_storage.py
~~~~~~~~~~~~~~~~~~~
Supabase file storage backend for the customer support agent.

Folder layout per user (auto-partitioned by file type):
    customer_support/{user_id}/pdfs/
    customer_support/{user_id}/images/
    customer_support/{user_id}/docs/
    customer_support/{user_id}/spreadsheets/
    customer_support/{user_id}/text/
    customer_support/{user_id}/others/

Files older than 24 hours are identified via their created_at
timestamp during the auto-cleanup job.
"""

from __future__ import annotations

import os
import logging
from datetime import datetime, timezone
from typing import Optional

from app.db import get_supabase_client

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
BUCKET_NAME = "Lyraa_CustomerSupportAgent"


def get_folder_for_file(filename: str, user_id: str = "anonymous") -> str:
    """
    Return the Supabase folder path for *filename* scoped to *user_id*.

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

class SupabaseStorage:
    """
    Thin wrapper around the Supabase Python SDK's Storage API.

    All methods are synchronous (FastAPI will call them in a thread pool via
    `run_in_executor` if needed for async routes).
    """

    def __init__(self) -> None:
        self.client = get_supabase_client()
        self.bucket = self.client.storage.from_(BUCKET_NAME)

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
        Upload *file_bytes* to Supabase under the correct type-folder for
        *user_id*.

        Returns a dict with:
            public_id   – Supabase path (used for deletion/download)
            secure_url  – HTTPS download URL
            folder      – folder path inside Supabase
            user_id     – owner
            uploaded_at – ISO-8601 UTC timestamp
            filename    – original filename
            size        – bytes uploaded
            resource_type – "raw" (for compatibility)
        """
        folder = get_folder_for_file(filename, user_id)
        now = datetime.now(timezone.utc)
        timestamp = int(now.timestamp())
        
        name, ext = os.path.splitext(filename)
        # Ensure filename is unique by appending timestamp
        unique_filename = f"{name}_{timestamp}{ext}"
        path = f"{folder}/{unique_filename}"

        # Determine content type based on extension
        content_type = "application/octet-stream"
        if ext in [".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"]:
            content_type = f"image/{ext.replace('.', '')}"
        elif ext == ".pdf":
            content_type = "application/pdf"
        elif ext in [".txt", ".md"]:
            content_type = "text/plain"

        try:
            self.bucket.upload(
                path,
                file_bytes,
                file_options={"content-type": content_type}
            )
        except Exception as e:
            logger.error(f"Failed to upload to Supabase: {e}")
            raise RuntimeError(f"Storage upload failed: {e}")

        secure_url = self.bucket.get_public_url(path)

        return {
            "public_id": path,
            "secure_url": secure_url,
            "folder": folder,
            "user_id": user_id,
            "uploaded_at": now.isoformat(),
            "filename": filename,
            "size": len(file_bytes),
            "resource_type": "raw",
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
        assets: list[dict] = []
        
        # Determine users to list
        users_to_list = []
        if user_id:
            users_to_list = [{"name": user_id}]
        else:
            try:
                users = self.bucket.list(ROOT_FOLDER)
                users_to_list = [u for u in users if u.get("id") is None]
            except Exception as e:
                logger.error(f"Failed to list ROOT_FOLDER: {e}")
                return assets

        for u in users_to_list:
            u_name = u["name"]
            user_prefix = f"{ROOT_FOLDER}/{u_name}"
            try:
                folders = self.bucket.list(user_prefix)
            except Exception:
                continue
                
            for f in folders:
                # If it's a folder (no id)
                if f.get("id") is None:
                    f_name = f["name"]
                    sub_prefix = f"{user_prefix}/{f_name}"
                    try:
                        files = self.bucket.list(sub_prefix)
                    except Exception:
                        continue
                        
                    for file_obj in files:
                        if file_obj.get("id") is not None:
                            # It is a file
                            path = f"{sub_prefix}/{file_obj['name']}"
                            
                            uploaded_at_str = file_obj.get("created_at")
                            expires_in: Optional[int] = None
                            try:
                                uploaded_dt = datetime.fromisoformat(uploaded_at_str.replace("Z", "+00:00"))
                                age_secs = (datetime.now(timezone.utc) - uploaded_dt).total_seconds()
                                expires_in = max(0, int(86400 - age_secs))
                            except Exception:
                                pass
                            
                            # Clean filename
                            original_filename = file_obj["name"]
                            if "_" in original_filename:
                                name_part = original_filename.rsplit("_", 1)[0]
                                ext_part = os.path.splitext(original_filename)[-1]
                                original_filename = f"{name_part}{ext_part}"

                            assets.append({
                                "public_id": path,
                                "secure_url": self.bucket.get_public_url(path),
                                "folder": sub_prefix,
                                "filename": original_filename,
                                "size": file_obj.get("metadata", {}).get("size", 0),
                                "uploaded_at": uploaded_at_str,
                                "resource_type": "raw",
                                "expires_in_seconds": expires_in,
                            })

        return assets

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    def delete_file(self, public_id: str, resource_type: str = "raw") -> dict:
        """
        Delete a single file by its Supabase *public_id* (which is its path).
        """
        try:
            res = self.bucket.remove([public_id])
            if res and len(res) > 0:
                return {"public_id": public_id, "result": "ok"}
            return {"public_id": public_id, "result": "not found"}
        except Exception as e:
            logger.error(f"Failed to delete {public_id}: {e}")
            return {"public_id": public_id, "result": "error"}

    # ------------------------------------------------------------------
    # Download (for ingestion pipeline)
    # ------------------------------------------------------------------

    def download_file(self, public_id: str, resource_type: str = "raw") -> bytes:
        """
        Download a file from Supabase and return its raw bytes.
        """
        try:
            return self.bucket.download(public_id)
        except Exception as e:
            logger.error(f"Failed to download {public_id}: {e}")
            raise FileNotFoundError(f"Failed to download public_id={public_id}")

    # ------------------------------------------------------------------
    # 24-hour cleanup
    # ------------------------------------------------------------------

    def delete_expired_files(self) -> dict:
        """
        Scan all assets and delete those uploaded more than 24 hours ago.
        Returns a summary: {"deleted": [...], "errors": [...]}
        """
        deleted: list[str] = []
        errors: list[str] = []
        now = datetime.now(timezone.utc)

        try:
            users = self.bucket.list(ROOT_FOLDER)
        except Exception as e:
            errors.append(f"Failed to list ROOT_FOLDER: {e}")
            return {"deleted": deleted, "errors": errors}

        for u in users:
            if u.get("id") is None:
                u_name = u["name"]
                user_prefix = f"{ROOT_FOLDER}/{u_name}"
                try:
                    folders = self.bucket.list(user_prefix)
                except Exception as e:
                    errors.append(f"Failed to list {user_prefix}: {e}")
                    continue
                    
                for f in folders:
                    if f.get("id") is None:
                        f_name = f["name"]
                        sub_prefix = f"{user_prefix}/{f_name}"
                        try:
                            files = self.bucket.list(sub_prefix)
                        except Exception as e:
                            errors.append(f"Failed to list {sub_prefix}: {e}")
                            continue
                            
                        for file_obj in files:
                            if file_obj.get("id") is not None:
                                uploaded_at_str = file_obj.get("created_at")
                                try:
                                    uploaded_dt = datetime.fromisoformat(uploaded_at_str.replace("Z", "+00:00"))
                                    age_secs = (now - uploaded_dt).total_seconds()
                                    if age_secs >= 86400:  # 24 hours
                                        path = f"{sub_prefix}/{file_obj['name']}"
                                        self.bucket.remove([path])
                                        deleted.append(path)
                                        logger.info(f"Auto-deleted expired asset: {path}")
                                except Exception as exc:
                                    errors.append(str(exc))
                                    logger.warning(f"Error during cleanup of {file_obj['name']}: {exc}")

        return {"deleted": deleted, "errors": errors}
