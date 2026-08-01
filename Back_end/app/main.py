import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-warm all heavy singletons at server startup so the first user request is fast."""
    print("[Startup] Pre-warming query engine and support agent...")
    try:
        try:
            from agent.rag import get_query_engine
            from agent.bot import get_support_agent
        except ImportError:
            from backend.agent.rag import get_query_engine
            from backend.agent.bot import get_support_agent

        get_query_engine()   # builds + caches Pinecone, embeddings, Groq, Cohere
        get_support_agent()  # builds + caches the ReAct agent
        print("[Startup] Warm-up complete. Server ready.")
    except Exception as e:
        print(f"[Startup] Warning: Warm-up failed: {e}")
    yield  # server runs here
    print("[Shutdown] Server shutting down.")


app = FastAPI(
    title="Lyraa Agent",
    description="Customer support Agent API",
    version="1.0.0",
    lifespan=lifespan,
)

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
try: 
    from app.api.endpoints import router as api_router
except ImportError:
    from backend.app.api.endpoints import router as api_router
    

app.include_router(api_router, prefix="/api")

@app.get("/health")
def health_check():
    return {"status": "healthy"}
