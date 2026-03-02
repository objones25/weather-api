"""OpenTelemetry tracing setup.

Both functions are no-ops when settings.otel_enabled is False, so tests and
local dev without a collector run without any OTel overhead or configuration.
"""

import logging

from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from app.config import Settings

logger = logging.getLogger(__name__)


def setup_tracing(app: FastAPI, settings: Settings) -> None:
    """Initialise the tracer provider and instrument FastAPI, httpx, and Redis.

    Call this early in the lifespan, before client connections are made, so the
    monkey-patching applied by the Redis and httpx instrumentors is in place
    when those clients are created.
    """
    if not settings.otel_enabled:
        return

    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.redis import RedisInstrumentor
    from opentelemetry.sdk.resources import SERVICE_NAME, Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    resource = Resource.create({SERVICE_NAME: settings.otel_service_name})
    provider = TracerProvider(resource=resource)
    provider.add_span_processor(
        BatchSpanProcessor(
            OTLPSpanExporter(endpoint=f"{settings.otel_endpoint}/v1/traces")
        )
    )
    trace.set_tracer_provider(provider)

    # Exclude /metrics — it's a high-frequency Prometheus scrape target and
    # would flood the trace backend with low-value spans.
    FastAPIInstrumentor.instrument_app(app, excluded_urls="/metrics")
    HTTPXClientInstrumentor().instrument()
    RedisInstrumentor().instrument()

    logger.info(
        "OpenTelemetry tracing enabled (endpoint=%s, service=%s)",
        settings.otel_endpoint,
        settings.otel_service_name,
    )


def instrument_sqlalchemy(engine: AsyncEngine, settings: Settings) -> None:
    """Instrument the SQLAlchemy async engine.

    Must be called after the engine is created in lifespan. The SQLAlchemy
    instrumentor hooks into the sync engine's event system, so we pass
    engine.sync_engine rather than the async wrapper.
    """
    if not settings.otel_enabled:
        return

    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

    SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
