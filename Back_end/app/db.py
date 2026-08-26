"""
db.py
~~~~~
Database layer for the Lyraa multi-tenant backend.

Provides:
  - get_supabase_client()      → Supabase Python client (service role)
  - AsyncSessionLocal          → SQLAlchemy async session factory
  - get_db()                   → FastAPI dependency yielding an async DB session
"""
from __future__ import annotations

import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from supabase import Client, create_client

load_dotenv()

# ── Supabase client (service-role — bypasses RLS, backend use ONLY) ───────────

_supabase_client: Client | None = None


def get_supabase_client() -> Client:
    """Return a cached Supabase service-role client."""
    global _supabase_client
    if _supabase_client is not None:
        return _supabase_client

    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set in .env"
        )

    _supabase_client = create_client(url, key)
    return _supabase_client


# ── SQLAlchemy async engine (for ORM / complex queries) ───────────────────────
# Supabase exposes a direct Postgres connection string — use asyncpg driver.
# Format: postgresql+asyncpg://postgres:<password>@db.<ref>.supabase.co:5432/postgres

def _build_async_db_url() -> str:
    url = os.getenv("SUPABASE_DB_URL")  # optional override
    if url:
        # Make sure we use the asyncpg driver
        return url.replace("postgresql://", "postgresql+asyncpg://").replace(
            "postgres://", "postgresql+asyncpg://"
        )
    # Construct from individual vars as fallback
    host = os.getenv("SUPABASE_DB_HOST", "")
    password = os.getenv("SUPABASE_DB_PASSWORD", "")
    if not host or not password:
        raise RuntimeError(
            "Set either SUPABASE_DB_URL or both SUPABASE_DB_HOST + SUPABASE_DB_PASSWORD in .env"
        )
    return f"postgresql+asyncpg://postgres:{password}@{host}:5432/postgres"


_async_engine = None
_AsyncSessionLocal = None


def _get_engine():
    global _async_engine
    if _async_engine is None:
        _async_engine = create_async_engine(
            _build_async_db_url(),
            pool_size=5,
            max_overflow=10,
            echo=False,  # set True to log SQL during development
            connect_args={
                "prepared_statement_cache_size": 0,
                "statement_cache_size": 0,
            },
        )
    return _async_engine


def _get_session_factory():
    global _AsyncSessionLocal
    if _AsyncSessionLocal is None:
        _AsyncSessionLocal = async_sessionmaker(
            bind=_get_engine(),
            class_=AsyncSession,
            expire_on_commit=False,
        )
    return _AsyncSessionLocal


# ── FastAPI dependency ─────────────────────────────────────────────────────────

async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields an async SQLAlchemy session."""
    factory = _get_session_factory()
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
