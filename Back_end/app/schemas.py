"""
schemas.py
~~~~~~~~~~
Pydantic v2 request/response schemas for the Lyraa multi-tenant API.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, EmailStr, Field, field_validator


# ── Tenant ────────────────────────────────────────────────────────────────────

class TenantCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    slug: str = Field(
        ...,
        min_length=2,
        max_length=50,
        pattern=r"^[a-z0-9-]+$",
        description="Lowercase letters, numbers, hyphens only. Used as Pinecone namespace.",
    )

    @field_validator("slug")
    @classmethod
    def slug_no_reserved(cls, v: str) -> str:
        reserved = {"admin", "api", "lyraa", "www", "app", "mail"}
        if v in reserved:
            raise ValueError(f"'{v}' is a reserved slug.")
        return v


class TenantUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)


class TenantOut(BaseModel):
    id: uuid.UUID
    name: str
    slug: str
    email: str
    created_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}


# ── Agent Config ──────────────────────────────────────────────────────────────

class AgentConfigUpdate(BaseModel):
    agent_name: Optional[str] = Field(None, min_length=1, max_length=80)
    system_prompt: Optional[str] = Field(None, max_length=4000)
    greeting_msg: Optional[str] = Field(None, max_length=500)
    slack_channel: Optional[str] = Field(None, max_length=100)
    avatar_url: Optional[str] = Field(None, max_length=500)


class AgentConfigOut(BaseModel):
    tenant_id: uuid.UUID
    agent_name: str
    system_prompt: Optional[str]
    greeting_msg: Optional[str]
    slack_channel: Optional[str]
    avatar_url: Optional[str]

    model_config = {"from_attributes": True}


# ── API Keys ──────────────────────────────────────────────────────────────────

class ApiKeyCreate(BaseModel):
    label: Optional[str] = Field(None, max_length=100)


class ApiKeyCreated(BaseModel):
    """Returned only once — raw_key is never stored."""
    id: uuid.UUID
    key_prefix: str
    raw_key: str
    label: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class ApiKeyOut(BaseModel):
    id: uuid.UUID
    key_prefix: str
    label: Optional[str]
    created_at: datetime
    last_used_at: Optional[datetime]
    is_active: bool

    model_config = {"from_attributes": True}


# ── Analytics ─────────────────────────────────────────────────────────────────

class DailyCount(BaseModel):
    date: str   # ISO date string e.g. "2026-08-13"
    count: int


class IntentBreakdown(BaseModel):
    intent: str
    count: int


class AnalyticsOut(BaseModel):
    messages_today: int
    messages_this_month: int
    daily_counts: list[DailyCount]
    intent_breakdown: list[IntentBreakdown]
    total_documents: int


# ── Subscription / Billing ────────────────────────────────────────────────────

class SubscriptionOut(BaseModel):
    plan: Literal["free", "starter", "pro", "enterprise"]
    message_limit: int
    messages_used: int
    period_start: datetime
    period_end: Optional[datetime]
    usage_pct: float  # 0.0 – 1.0

    model_config = {"from_attributes": True}


# ── Chat ─────────────────────────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=4000)
    session_id: Optional[str] = Field(None, description="Optional session identifier for analytics")


class ChatResponse(BaseModel):
    response: str
    intent: str = "unknown"


# ── Upload / Ingest ───────────────────────────────────────────────────────────

class LinkRequest(BaseModel):
    url: str = Field(..., description="URL to scrape via Tavily")
    session_id: Optional[str] = None


class IngestRequest(BaseModel):
    mode: Literal["all", "recent"] = "all"


# ── Overview stats (dashboard home) ──────────────────────────────────────────

class OverviewOut(BaseModel):
    messages_today: int
    messages_this_month: int
    total_documents: int
    plan: str
    message_limit: int
    messages_used: int
