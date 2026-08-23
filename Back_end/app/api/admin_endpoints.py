"""
admin_endpoints.py
~~~~~~~~~~~~~~~~~~
FastAPI router for all /api/admin/* routes.

All endpoints require a valid Supabase JWT (Authorization: Bearer <token>).
API-key authentication is intentionally NOT allowed here — the admin panel
is only accessible to authenticated tenant owners.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.auth import generate_api_key, get_current_tenant, verify_supabase_token
from app.db import get_db, get_supabase_client
from app.models import AgentConfig, ApiKey, Subscription, Tenant, UsageLog
from app.schemas import (
    AgentConfigOut,
    AgentConfigUpdate,
    AnalyticsOut,
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    DailyCount,
    IntentBreakdown,
    OverviewOut,
    SubscriptionOut,
    TenantCreate,
    TenantOut,
    TenantUpdate,
)
from agent.bot import invalidate_agent

router = APIRouter(tags=["admin"])


# ---------------------------------------------------------------------------
# Tenant registration / profile
# ---------------------------------------------------------------------------

@router.post("/tenants", response_model=TenantOut, status_code=status.HTTP_201_CREATED)
async def register_tenant(
    body: TenantCreate,
    db: AsyncSession = Depends(get_db),
    # We can't use get_current_tenant here because the tenant row doesn't exist yet.
    # Instead we validate the raw JWT and pull the supabase_uid from it.
    authorization: str = None,
):
    """
    Register a new tenant.

    Call this once after signing up via Supabase Auth.
    Requires: Authorization: Bearer <supabase_jwt>
    """
    # Re-implement minimal JWT extraction for first-time registration
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authorization header required.",
        )
    token = authorization.removeprefix("Bearer ").strip()
    payload = verify_supabase_token(token)
    supabase_uid: str | None = payload.get("sub")
    email: str = payload.get("email", "")

    if not supabase_uid:
        raise HTTPException(status_code=400, detail="Invalid token: missing 'sub'.")

    # Check if already registered
    existing = await db.execute(
        select(Tenant).where(Tenant.supabase_uid == supabase_uid)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A tenant is already registered for this account.",
        )

    # Check slug uniqueness
    slug_check = await db.execute(select(Tenant).where(Tenant.slug == body.slug))
    if slug_check.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Slug '{body.slug}' is already taken.",
        )

    # Create tenant
    tenant = Tenant(
        name=body.name,
        slug=body.slug,
        supabase_uid=supabase_uid,
        email=email,
    )
    db.add(tenant)
    await db.flush()  # get tenant.id before creating related rows

    # Default agent config
    db.add(AgentConfig(tenant_id=tenant.id))

    # Default subscription (free tier)
    db.add(Subscription(
        tenant_id=tenant.id,
        period_end=datetime.now(timezone.utc) + timedelta(days=30),
    ))

    await db.commit()
    await db.refresh(tenant)
    return tenant


@router.get("/tenants/me", response_model=TenantOut)
async def get_my_tenant(tenant: Tenant = Depends(get_current_tenant)):
    """Return the authenticated tenant's profile."""
    return tenant


@router.put("/tenants/me", response_model=TenantOut)
async def update_my_tenant(
    body: TenantUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Update tenant display name."""
    if body.name is not None:
        tenant.name = body.name
    db.add(tenant)
    await db.commit()
    await db.refresh(tenant)
    return tenant


# ---------------------------------------------------------------------------
# API Keys
# ---------------------------------------------------------------------------

@router.post("/api-keys", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: ApiKeyCreate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate a new API key for widget/integration use.

    ⚠️ The raw key is returned ONCE and never stored — save it immediately.
    """
    raw_key, key_prefix, key_hash = generate_api_key()
    key_row = ApiKey(
        tenant_id=tenant.id,
        key_hash=key_hash,
        key_prefix=key_prefix,
        label=body.label,
    )
    db.add(key_row)
    await db.commit()
    await db.refresh(key_row)

    return ApiKeyCreated(
        id=key_row.id,
        key_prefix=key_prefix,
        raw_key=raw_key,
        label=body.label,
        created_at=key_row.created_at,
    )


@router.get("/api-keys", response_model=List[ApiKeyOut])
async def list_api_keys(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """List all API keys for the tenant (raw key is never returned)."""
    result = await db.execute(
        select(ApiKey)
        .where(ApiKey.tenant_id == tenant.id)
        .order_by(ApiKey.created_at.desc())
    )
    return list(result.scalars().all())


@router.delete("/api-keys/{key_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_api_key(
    key_id: uuid.UUID,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Revoke (deactivate) an API key. The key will immediately stop working."""
    result = await db.execute(
        select(ApiKey).where(ApiKey.id == key_id, ApiKey.tenant_id == tenant.id)
    )
    key_row = result.scalar_one_or_none()
    if not key_row:
        raise HTTPException(status_code=404, detail="API key not found.")
    key_row.is_active = False
    db.add(key_row)
    await db.commit()


# ---------------------------------------------------------------------------
# Agent Persona Config
# ---------------------------------------------------------------------------

@router.get("/agent-config", response_model=AgentConfigOut)
async def get_agent_config(tenant: Tenant = Depends(get_current_tenant)):
    """Return the tenant's current agent persona configuration."""
    if not tenant.agent_config:
        raise HTTPException(status_code=404, detail="Agent config not found. This shouldn't happen — contact support.")
    return tenant.agent_config


@router.put("/agent-config", response_model=AgentConfigOut)
async def update_agent_config(
    body: AgentConfigUpdate,
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """
    Update the agent's name, system prompt, greeting message, or avatar.

    Changes take effect on the next chat request (the agent cache is invalidated).
    """
    config = tenant.agent_config
    if not config:
        # Create default if missing
        config = AgentConfig(tenant_id=tenant.id)
        db.add(config)

    update_data = body.model_dump(exclude_none=True)
    for field, value in update_data.items():
        setattr(config, field, value)

    db.add(config)
    await db.commit()
    await db.refresh(config)

    # Bust the agent cache so the new system_prompt is used immediately
    invalidate_agent(str(tenant.id))

    return config


# ---------------------------------------------------------------------------
# Analytics
# ---------------------------------------------------------------------------

@router.get("/analytics", response_model=AnalyticsOut)
async def get_analytics(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return usage analytics for the past 30 days."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    thirty_days_ago = now - timedelta(days=30)

    # Messages today
    today_result = await db.execute(
        select(func.count(UsageLog.id)).where(
            UsageLog.tenant_id == tenant.id,
            UsageLog.created_at >= today_start,
        )
    )
    messages_today = today_result.scalar() or 0

    # Messages this month
    month_result = await db.execute(
        select(func.count(UsageLog.id)).where(
            UsageLog.tenant_id == tenant.id,
            UsageLog.created_at >= month_start,
        )
    )
    messages_this_month = month_result.scalar() or 0

    # Daily counts (last 30 days)
    daily_result = await db.execute(
        select(
            func.date(UsageLog.created_at).label("date"),
            func.count(UsageLog.id).label("count"),
        )
        .where(
            UsageLog.tenant_id == tenant.id,
            UsageLog.created_at >= thirty_days_ago,
        )
        .group_by(func.date(UsageLog.created_at))
        .order_by(func.date(UsageLog.created_at))
    )
    daily_counts = [
        DailyCount(date=str(row.date), count=row.count)
        for row in daily_result.all()
    ]

    # Intent breakdown
    intent_result = await db.execute(
        select(UsageLog.intent, func.count(UsageLog.id).label("count"))
        .where(
            UsageLog.tenant_id == tenant.id,
            UsageLog.created_at >= thirty_days_ago,
            UsageLog.intent.isnot(None),
        )
        .group_by(UsageLog.intent)
        .order_by(func.count(UsageLog.id).desc())
    )
    intent_breakdown = [
        IntentBreakdown(intent=row.intent, count=row.count)
        for row in intent_result.all()
    ]

    # Document count (from Cloudinary)
    from storage.cloudinary_storage import CloudinaryStorage
    try:
        storage = CloudinaryStorage()
        docs = storage.list_files(user_id=f"tenant_{tenant.slug}")
        total_documents = len(docs)
    except Exception:
        total_documents = 0

    return AnalyticsOut(
        messages_today=messages_today,
        messages_this_month=messages_this_month,
        daily_counts=daily_counts,
        intent_breakdown=intent_breakdown,
        total_documents=total_documents,
    )


# ---------------------------------------------------------------------------
# Subscription / Billing (Placeholder — no Stripe yet)
# ---------------------------------------------------------------------------

@router.get("/subscription", response_model=SubscriptionOut)
async def get_subscription(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return the tenant's current subscription/billing info (placeholder)."""
    sub = tenant.subscription
    if not sub:
        # Return default free tier data if subscription row is missing
        return SubscriptionOut(
            plan="free",
            message_limit=1000,
            messages_used=0,
            period_start=datetime.now(timezone.utc),
            period_end=None,
            usage_pct=0.0,
        )

    usage_pct = min(sub.messages_used / sub.message_limit, 1.0) if sub.message_limit > 0 else 0.0
    return SubscriptionOut(
        plan=sub.plan,
        message_limit=sub.message_limit,
        messages_used=sub.messages_used,
        period_start=sub.period_start,
        period_end=sub.period_end,
        usage_pct=usage_pct,
    )


# ---------------------------------------------------------------------------
# Overview (dashboard home card)
# ---------------------------------------------------------------------------

@router.get("/overview", response_model=OverviewOut)
async def get_overview(
    tenant: Tenant = Depends(get_current_tenant),
    db: AsyncSession = Depends(get_db),
):
    """Return summary stats for the dashboard home page."""
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    today_r = await db.execute(
        select(func.count(UsageLog.id)).where(
            UsageLog.tenant_id == tenant.id, UsageLog.created_at >= today_start
        )
    )
    month_r = await db.execute(
        select(func.count(UsageLog.id)).where(
            UsageLog.tenant_id == tenant.id, UsageLog.created_at >= month_start
        )
    )

    from storage.cloudinary_storage import CloudinaryStorage
    try:
        docs = CloudinaryStorage().list_files(user_id=f"tenant_{tenant.slug}")
        doc_count = len(docs)
    except Exception:
        doc_count = 0

    sub = tenant.subscription
    plan = sub.plan if sub else "free"
    message_limit = sub.message_limit if sub else 1000
    messages_used = sub.messages_used if sub else 0

    return OverviewOut(
        messages_today=today_r.scalar() or 0,
        messages_this_month=month_r.scalar() or 0,
        total_documents=doc_count,
        plan=plan,
        message_limit=message_limit,
        messages_used=messages_used,
    )
