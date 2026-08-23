"""
auth.py
~~~~~~~
Supabase JWT verification and FastAPI authentication dependencies for the
Lyraa multi-tenant backend.

Two authentication paths:
  1. Supabase JWT   — for dashboard / direct API calls
     Header: Authorization: Bearer <supabase_access_token>

  2. API Key        — for embeddable widget / third-party integrations
     Header: X-API-Key: lyr_<random>

Dependency resolution order (get_tenant_from_request):
  JWT → API Key → 401
"""
from __future__ import annotations

import os
import secrets
import string
import uuid
from typing import Annotated

import bcrypt
from dotenv import load_dotenv
from fastapi import Depends, Header, HTTPException, Request, status
from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db import get_db
from app.models import AgentConfig, ApiKey, Tenant

load_dotenv()

SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET", "")
SUPABASE_JWKS_URL = os.getenv("SUPABASE_JWKS_URL", "")
ALGORITHM = "HS256"

import urllib.request
import json
_jwks = None

def _get_jwks():
    global _jwks
    if not _jwks and SUPABASE_JWKS_URL:
        try:
            with urllib.request.urlopen(SUPABASE_JWKS_URL) as response:
                _jwks = json.loads(response.read())
        except Exception as e:
            print(f"[AUTH] Failed to fetch JWKS: {e}")
    return _jwks

# ── JWT verification ───────────────────────────────────────────────────────────


def verify_supabase_token(token: str) -> dict:
    """
    Decode and verify a Supabase-issued JWT.

    Returns the decoded payload dict on success.
    Raises HTTPException 401 on failure.
    """
    if not SUPABASE_JWT_SECRET:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="SUPABASE_JWT_SECRET is not configured on the server.",
        )
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg", "HS256")
        
        # Use JWKS for ES256/RS256, otherwise use the symmetric secret
        key = _get_jwks() if alg != "HS256" else SUPABASE_JWT_SECRET
        if alg != "HS256" and not key:
            key = SUPABASE_JWT_SECRET # fallback if JWKS fetch failed
            
        payload = jwt.decode(
            token,
            key,
            algorithms=["HS256", "RS256", "ES256"],
            options={"verify_aud": False},  # Supabase uses custom audience claims
        )
        return payload
    except JWTError as exc:
        print(f"[AUTH DEBUG] JWT decode error: {exc}")
        print(f"[AUTH DEBUG] Secret used: {SUPABASE_JWT_SECRET[:10]}...")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid or expired token: {exc}",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ── FastAPI dependencies ───────────────────────────────────────────────────────


async def _get_tenant_by_supabase_uid(
    supabase_uid: str, db: AsyncSession
) -> Tenant | None:
    """Fetch a tenant (with agent_config eagerly loaded) by their Supabase UID."""
    result = await db.execute(
        select(Tenant)
        .where(Tenant.supabase_uid == supabase_uid, Tenant.is_active == True)
        .options(selectinload(Tenant.agent_config), selectinload(Tenant.subscription))
    )
    return result.scalar_one_or_none()


async def get_current_tenant(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """
    FastAPI dependency: validates the Supabase JWT from the Authorization header
    and returns the corresponding Tenant ORM object.

    Raises 401 if the token is missing/invalid.
    Raises 404 if no tenant has been registered for this Supabase UID yet.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header missing or malformed. Expected: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.removeprefix("Bearer ").strip()
    payload = verify_supabase_token(token)
    supabase_uid: str | None = payload.get("sub")

    if not supabase_uid:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token payload missing 'sub' claim.",
        )

    tenant = await _get_tenant_by_supabase_uid(supabase_uid, db)
    if tenant is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No tenant registered for this account. POST /api/admin/tenants to register.",
        )

    return tenant


async def _get_tenant_by_api_key(raw_key: str, db: AsyncSession) -> Tenant | None:
    """
    Validate a raw API key and return the owning Tenant.

    Strategy: fetch all active api_key rows that share the same prefix (first 12 chars),
    then bcrypt.checkpw against each hash. This avoids a full table scan.
    """
    if not raw_key or len(raw_key) < 12:
        return None

    prefix = raw_key[:12]  # "lyr_" + 8 chars

    result = await db.execute(
        select(ApiKey)
        .where(
            ApiKey.key_prefix == prefix,
            ApiKey.is_active == True,
        )
        .options(
            selectinload(ApiKey.tenant).options(
                selectinload(Tenant.agent_config),
                selectinload(Tenant.subscription),
            )
        )
    )
    candidates: list[ApiKey] = list(result.scalars().all())

    for key_row in candidates:
        try:
            match = bcrypt.checkpw(
                raw_key.encode("utf-8"),
                key_row.key_hash.encode("utf-8"),
            )
        except Exception:
            continue
        if match and key_row.tenant and key_row.tenant.is_active:
            # Update last_used_at asynchronously (fire and forget is fine here)
            from datetime import datetime, timezone

            key_row.last_used_at = datetime.now(timezone.utc)
            return key_row.tenant

    return None


async def get_tenant_from_request(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> Tenant:
    """
    Multi-path FastAPI dependency used on public endpoints (chat, upload, etc.).

    Tries:
      1. Authorization: Bearer <jwt>
      2. X-API-Key: <raw_key>
    Raises 401 if neither succeeds.
    """
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.removeprefix("Bearer ").strip()
        try:
            payload = verify_supabase_token(token)
            supabase_uid = payload.get("sub")
            if supabase_uid:
                tenant = await _get_tenant_by_supabase_uid(supabase_uid, db)
                if tenant:
                    return tenant
        except HTTPException:
            pass  # Fall through to API key check

    api_key = request.headers.get("X-API-Key", "").strip()
    if api_key:
        tenant = await _get_tenant_by_api_key(api_key, db)
        if tenant:
            return tenant

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required. Provide a valid Bearer token or X-API-Key header.",
        headers={"WWW-Authenticate": "Bearer"},
    )


# ── API key generation helper ──────────────────────────────────────────────────

_KEY_ALPHABET = string.ascii_letters + string.digits


def generate_api_key() -> tuple[str, str, str]:
    """
    Generate a new API key.

    Returns:
        (raw_key, key_prefix, key_hash)

    raw_key    — shown to the user ONCE, never stored
    key_prefix — first 12 chars, stored in DB for lookup (e.g. "lyr_abc12345")
    key_hash   — bcrypt hash of raw_key, stored in DB for verification
    """
    body = "".join(secrets.choice(_KEY_ALPHABET) for _ in range(40))
    raw_key = f"lyr_{body}"
    key_prefix = raw_key[:12]
    key_hash = bcrypt.hashpw(raw_key.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    return raw_key, key_prefix, key_hash
