import os
import logging

logger = logging.getLogger(__name__)

def setup_tracing():
    """
    Bootstrap Phoenix / OpenTelemetry tracing for the Lyraa backend.
    Reads PHOENIX_COLLECTOR_ENDPOINT and PHOENIX_API_KEY from environment.
    """
    endpoint = os.getenv("PHOENIX_COLLECTOR_ENDPOINT")
    api_key = os.getenv("PHOENIX_API_KEY")

    if not endpoint or not api_key:
        logger.warning("Phoenix tracing disabled: Missing PHOENIX_COLLECTOR_ENDPOINT or PHOENIX_API_KEY")
        return None

    try:
        from phoenix.otel import register
        from openinference.instrumentation.llama_index import LlamaIndexInstrumentor
        
        # We explicitly set protocol to http/protobuf
        # Phoenix register automatically picks up PHOENIX_COLLECTOR_ENDPOINT 
        # and PHOENIX_API_KEY from os.environ
        tracer_provider = register(
            project_name="lyraa-multi-tenant",
            endpoint=endpoint,
            protocol="http/protobuf"
        )
        
        # Instrument LlamaIndex
        LlamaIndexInstrumentor().instrument(tracer_provider=tracer_provider)
        
        logger.info(f"Phoenix tracing enabled. Project: lyraa-multi-tenant")
        return tracer_provider
    except ImportError as e:
        logger.error(f"Phoenix tracing unavailable. Missing dependencies: {e}")
        return None
    except Exception as exc:
        logger.error(f"Failed to initialize Phoenix tracing: {exc}")
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
