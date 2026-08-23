"""
main.py
~~~~~~~
FastAPI application entry point for the Lyraa multi-tenant backend.

Changes from single-tenant version:
  - Startup warm-up removed (engines/agents are now per-tenant, built on first request)
  - Supabase client is pre-warmed on startup to surface config errors early
  - Admin router added at /api/admin
  - CORS tightened for production (set ALLOWED_ORIGINS in .env)
"""
import os
import sys
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent
for candidate in (str(PROJECT_ROOT), str(PROJECT_ROOT.parent)):
    if candidate not in sys.path:
        sys.path.insert(0, candidate)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup / shutdown lifecycle."""
    print("[startup] Lyraa multi-tenant backend starting...")

    # ── Optional Phoenix tracing ──────────────────────────────────────────────
    try:
        import importlib
        llama_index_module = importlib.import_module("openinference.instrumentation.llama_index")
        phoenix_module = importlib.import_module("phoenix.otel")
        LlamaIndexInstrumentor = llama_index_module.LlamaIndexInstrumentor
        register = phoenix_module.register
        os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "")
        os.environ["PHOENIX_API_KEY"] = os.getenv("PHOENIX_API_KEY", "")
        tracer_provider = register(project_name="lyraa-multi-tenant", protocol="http/protobuf")
        LlamaIndexInstrumentor().instrument(tracer_provider=tracer_provider)
        print("[startup] Phoenix tracing enabled.")
    except Exception as exc:
        print(f"[startup] Phoenix tracing unavailable: {exc}")

    # ── Pre-warm Supabase client (surfaces missing config early) ─────────────
    try:
        from app.db import get_supabase_client
        get_supabase_client()
        print("[startup] Supabase client ready.")
    except Exception as exc:
        print(f"[startup] WARNING: Supabase client failed to initialise: {exc}")

    print("[startup] Server ready.")
    yield
    print("[shutdown] Server shutting down.")


app = FastAPI(
    title="Lyraa Agent",
    description="Multi-tenant Customer Support Agent API",
    version="2.0.0",
    lifespan=lifespan,
)

# ── CORS ──────────────────────────────────────────────────────────────────────
# In production set ALLOWED_ORIGINS=https://yourdomain.com,https://app.yourdomain.com
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_raw_origins,   # later change it to original domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ───────────────────────────────────────────────────────────────────
from app.api.endpoints import router as api_router
from app.api.admin_endpoints import router as admin_router

app.include_router(api_router, prefix="/api")
app.include_router(admin_router, prefix="/api/admin")


@app.get("/health")
def health_check():
    return {"status": "healthy", "version": "2.0.0"}
