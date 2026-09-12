import os
import logging
from llama_index.observability.otel import LlamaIndexOpenTelemetry

from langfuse import get_client

langfuse = get_client()

# Verify connection
if langfuse.auth_check():
    print("Langfuse client is authenticated and ready!")
else:
    print("Authentication failed. Please check your credentials and host.")

logger = logging.getLogger(__name__)

def setup_tracing():
    """
    Bootstrap Langfuse tracing for the Lyraa backend.
    Reads LANGFUSE_SECRET_KEY, LANGFUSE_PUBLIC_KEY, and LANGFUSE_HOST from environment.
    """
    secret_key = os.getenv("LANGFUSE_SECRET_KEY")
    public_key = os.getenv("LANGFUSE_PUBLIC_KEY")

    if not secret_key or not public_key:
        logger.warning("Langfuse tracing disabled: Missing keys")
        return None

    try:
        instrumentor = LlamaIndexOpenTelemetry()
        instrumentor.start()
        
        logger.info("Langfuse tracing enabled.")
        return instrumentor
    except ImportError as e:
        logger.error(f"Langfuse tracing unavailable. Missing dependencies: {e}")
        return None
    except Exception as exc:
        logger.error(f"Failed to initialize Langfuse tracing: {exc}")
        return None

def get_tracer(name: str):
    """
    Helper to get an OpenTelemetry tracer for manual span instrumentation.
    Returns a dummy tracer if opentelemetry is not installed or configured.
    """
    try:
        from opentelemetry import trace
        return trace.get_tracer(name)
    except ImportError:
        class DummySpan:
            def __enter__(self): return self
            def __exit__(self, *args): pass
            def set_attribute(self, key, value): pass
            def record_exception(self, exc): pass

        class DummyTracer:
            def start_as_current_span(self, *args, **kwargs):
                return DummySpan()
            
        return DummyTracer()
