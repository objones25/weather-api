"""
Unit tests for app/telemetry.py.

The enabled code paths are tested by mocking the external OTel packages.
This avoids real monkey-patching side-effects (global state mutation) while
covering every line that is otherwise skipped when otel_enabled=False.

Key mocking insight: telemetry.py uses lazy imports inside each function body
(`from opentelemetry.X import Y`). patch() replaces the attribute on the
already-loaded module object, so the lazy `from ... import` picks up the mock
on the next call — no import-time patching required.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.telemetry import instrument_sqlalchemy, setup_tracing
from app.config import Settings


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def enabled_settings():
    return Settings(
        weather_api_key="dummy",
        redis_password="dummy",
        api_key="dummy",
        otel_enabled=True,
        otel_endpoint="http://localhost:4318",
        otel_service_name="test-service",
    )


@pytest.fixture
def disabled_settings():
    return Settings(
        weather_api_key="dummy",
        redis_password="dummy",
        api_key="dummy",
        otel_enabled=False,
    )


# ---------------------------------------------------------------------------
# setup_tracing
# ---------------------------------------------------------------------------


def test_setup_tracing_noop_when_disabled(disabled_settings):
    """No OTel internals are touched when otel_enabled=False."""
    app = MagicMock()
    with patch("opentelemetry.trace.set_tracer_provider") as mock_set:
        setup_tracing(app, disabled_settings)
    mock_set.assert_not_called()


def test_setup_tracing_configures_provider_and_instrumentors(enabled_settings):
    """Enabled path: provider is built and all three instrumentors are called."""
    app = MagicMock()

    with (
        patch("opentelemetry.sdk.trace.TracerProvider") as MockProvider,
        patch("opentelemetry.sdk.resources.Resource") as MockResource,
        patch(
            "opentelemetry.exporter.otlp.proto.http.trace_exporter.OTLPSpanExporter"
        ) as MockExporter,
        patch("opentelemetry.sdk.trace.export.BatchSpanProcessor"),
        patch("opentelemetry.trace.set_tracer_provider") as mock_set_provider,
        patch(
            "opentelemetry.instrumentation.fastapi.FastAPIInstrumentor"
        ) as MockFastAPI,
        patch(
            "opentelemetry.instrumentation.httpx.HTTPXClientInstrumentor"
        ) as MockHTTPX,
        patch("opentelemetry.instrumentation.redis.RedisInstrumentor") as MockRedis,
    ):
        setup_tracing(app, enabled_settings)

    # Tracer provider set as the global provider
    mock_set_provider.assert_called_once_with(MockProvider.return_value)

    # Resource created with the configured service name
    resource_attrs = MockResource.create.call_args.args[0]
    assert "test-service" in resource_attrs.values()

    # OTLP exporter pointed at the configured endpoint
    MockExporter.assert_called_once_with(endpoint="http://localhost:4318/v1/traces")

    # FastAPI instrumented with /metrics excluded
    MockFastAPI.instrument_app.assert_called_once_with(app, excluded_urls="/metrics")

    # httpx and Redis instrumented globally
    MockHTTPX.return_value.instrument.assert_called_once()
    MockRedis.return_value.instrument.assert_called_once()


# ---------------------------------------------------------------------------
# instrument_sqlalchemy
# ---------------------------------------------------------------------------


def test_instrument_sqlalchemy_noop_when_disabled(disabled_settings):
    """No SQLAlchemy instrumentation when otel_enabled=False."""
    engine = MagicMock()
    with patch(
        "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor"
    ) as MockInstr:
        instrument_sqlalchemy(engine, disabled_settings)
    MockInstr.assert_not_called()


def test_instrument_sqlalchemy_passes_sync_engine(enabled_settings):
    """Enabled path: instrumentor receives engine.sync_engine, not the async wrapper."""
    engine = MagicMock()

    with patch(
        "opentelemetry.instrumentation.sqlalchemy.SQLAlchemyInstrumentor"
    ) as MockInstr:
        instrument_sqlalchemy(engine, enabled_settings)

    MockInstr.return_value.instrument.assert_called_once_with(engine=engine.sync_engine)
