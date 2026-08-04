import importlib
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Pre-warm heavy singletons and enable tracing when the optional packages are available."""
    print("[startup] Pre-warming query engine and support agent...")

    try:
        llama_index_module = importlib.import_module("openinference.instrumentation.llama_index")
        phoenix_module = importlib.import_module("phoenix.otel")
    except Exception:
        print("[startup] Phoenix tracing dependencies are unavailable; continuing without tracing.")
    else:
        try:
            LlamaIndexInstrumentor = llama_index_module.LlamaIndexInstrumentor
            register = phoenix_module.register
            os.environ["PHOENIX_COLLECTOR_ENDPOINT"] = os.getenv("PHOENIX_COLLECTOR_ENDPOINT", "")
            os.environ["PHOENIX_API_KEY"] = os.getenv("PHOENIX_API_KEY", "")
            tracer_provider = register(project_name="llamaindex-tracing-tutorial", protocol="http/protobuf")
            LlamaIndexInstrumentor().instrument(tracer_provider=tracer_provider)
            print("[startup] Phoenix tracing enabled.")
        except Exception as exc:
            print(f"[startup] Phoenix tracing setup failed: {exc}")

    try:
        try:
            from agent.rag import get_query_engine
            from agent.bot import get_support_agent
        except ImportError:
            from Back_end.agent.rag import get_query_engine
            from Back_end.agent.bot import get_support_agent

        get_query_engine()   # builds + caches Pinecone, embeddings, Groq, Cohere
        get_support_agent()  # builds + caches the ReAct agent
        print("[startup] Warm-up complete. Server ready.")
    except Exception as exc:
        print(f"[startup] Warning: Warm-up failed: {exc}")

    yield  # server runs here
    print("[shutdown] Server shutting down.")


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
    from Back_end.app.api.endpoints import router as api_router
    

app.include_router(api_router, prefix="/api")

@app.get("/health")
def health_check():
    return {"status": "healthy"}
