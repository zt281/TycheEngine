"""Unit tests for OpenTelemetry tracing integration."""

import os
from unittest.mock import patch

import pytest

from src.tyche.tracing import (
    TycheTracer,
    extract_trace_context,
    get_tracer,
    init_tracing,
    inject_trace_context,
    make_messaging_attributes,
    make_rpc_attributes,
    shutdown_tracing,
    start_as_current_span,
    start_span,
    strip_trace_context,
    TRACE_CONTEXT_KEY,
)


class TestTycheTracer:
    """Tests for TycheTracer SDK initialization."""

    def test_tracer_init_defaults(self):
        """Tracer initializes with sensible defaults."""
        tracer = TycheTracer()
        assert tracer.is_enabled is True
        assert tracer._service_name == "tyche"
        assert tracer._exporter_type == "console"

    def test_tracer_disabled_via_env(self):
        """Tracer respects TYCHE_TRACING_ENABLED=false."""
        with patch.dict(os.environ, {"TYCHE_TRACING_ENABLED": "false"}):
            tracer = TycheTracer()
            assert tracer.is_enabled is False

    def test_tracer_init_explicit_params(self):
        """Tracer uses explicit constructor params over env vars."""
        tracer = TycheTracer(
            service_name="test-service",
            enabled=False,
            exporter_type="none",
        )
        assert tracer._service_name == "test-service"
        assert tracer.is_enabled is False
        assert tracer._exporter_type == "none"

    def test_tracer_lazy_init(self):
        """Tracer initializes lazily on first use."""
        tracer = TycheTracer(enabled=True, exporter_type="none")
        assert tracer._initialized is False
        tracer.init()
        assert tracer._initialized is True

    def test_tracer_disabled_no_init(self):
        """Disabled tracer does not initialize."""
        tracer = TycheTracer(enabled=False)
        tracer.init()
        assert tracer._initialized is False

    def test_tracer_shutdown(self):
        """Tracer shuts down cleanly."""
        tracer = TycheTracer(enabled=True, exporter_type="none")
        tracer.init()
        tracer.shutdown()
        assert tracer._initialized is False

    def test_tracer_no_op_when_disabled(self):
        """Disabled tracer returns no-op tracer."""
        tracer = TycheTracer(enabled=False)
        t = tracer.tracer
        assert t is not None

    def test_sampler_always_on(self):
        """Sampler always_on captures all traces."""
        tracer = TycheTracer(
            enabled=True,
            exporter_type="none",
            sampler_name="always_on",
        )
        sampler = tracer._build_sampler()
        assert sampler is not None

    def test_sampler_always_off(self):
        """Sampler always_off drops all traces."""
        tracer = TycheTracer(
            enabled=True,
            exporter_type="none",
            sampler_name="always_off",
        )
        sampler = tracer._build_sampler()
        assert sampler is not None

    def test_sampler_traceidratio(self):
        """Sampler traceidratio respects ratio."""
        tracer = TycheTracer(
            enabled=True,
            exporter_type="none",
            sampler_name="traceidratio",
            sampler_ratio=0.5,
        )
        sampler = tracer._build_sampler()
        assert sampler is not None

    def test_console_exporter(self):
        """Console exporter builds successfully."""
        tracer = TycheTracer(exporter_type="console")
        exporter = tracer._build_exporter()
        assert exporter is not None

    def test_otlp_exporter(self):
        """OTLP exporter builds successfully."""
        tracer = TycheTracer(exporter_type="otlp", otlp_endpoint="http://localhost:4317")
        exporter = tracer._build_exporter()
        assert exporter is not None

    def test_none_exporter(self):
        """None exporter returns None."""
        tracer = TycheTracer(exporter_type="none")
        exporter = tracer._build_exporter()
        assert exporter is None


class TestTraceContextPropagation:
    """Tests for trace context inject/extract."""

    def test_inject_creates_trace_context(self):
        """Inject adds __otel_ctx__ to payload."""
        tracer = init_tracing(enabled=True, exporter_type="none")
        payload = {"data": "test"}

        with start_as_current_span("test"):
            inject_trace_context(payload)

        assert TRACE_CONTEXT_KEY in payload
        assert "traceparent" in payload[TRACE_CONTEXT_KEY]
        shutdown_tracing()

    def test_extract_returns_context(self):
        """Extract returns valid context from payload."""
        tracer = init_tracing(enabled=True, exporter_type="none")
        payload = {"data": "test"}

        with start_as_current_span("test"):
            inject_trace_context(payload)

        ctx = extract_trace_context(payload)
        assert ctx is not None
        shutdown_tracing()

    def test_extract_no_context_returns_none(self):
        """Extract returns None when no context present."""
        init_tracing(enabled=True, exporter_type="none")
        payload = {"data": "test"}
        ctx = extract_trace_context(payload)
        assert ctx is None
        shutdown_tracing()

    def test_roundtrip_preserves_trace_id(self):
        """Inject then extract preserves trace context."""
        tracer = init_tracing(enabled=True, exporter_type="none")
        payload = {"data": "test"}

        with start_as_current_span("producer"):
            inject_trace_context(payload)
            # Get the traceparent from injected context
            injected = payload[TRACE_CONTEXT_KEY]["traceparent"]

        # Now extract
        ctx = extract_trace_context(payload)
        assert ctx is not None

        # Verify traceparent is preserved
        assert payload[TRACE_CONTEXT_KEY]["traceparent"] == injected
        shutdown_tracing()

    def test_strip_removes_context(self):
        """Strip removes __otel_ctx__ from payload."""
        payload = {"data": "test", TRACE_CONTEXT_KEY: {"traceparent": "00-..."}}
        strip_trace_context(payload)
        assert TRACE_CONTEXT_KEY not in payload
        assert payload["data"] == "test"

    def test_inject_disabled_tracing(self):
        """Inject is a no-op when tracing disabled."""
        init_tracing(enabled=False, exporter_type="none")
        payload = {"data": "test"}
        inject_trace_context(payload)
        assert TRACE_CONTEXT_KEY not in payload
        shutdown_tracing()

    def test_extract_disabled_tracing(self):
        """Extract returns None when tracing disabled."""
        init_tracing(enabled=False, exporter_type="none")
        payload = {"data": "test", TRACE_CONTEXT_KEY: {"traceparent": "00-..."}}
        ctx = extract_trace_context(payload)
        assert ctx is None
        shutdown_tracing()


class TestSpanHelpers:
    """Tests for span creation helpers."""

    def test_start_span_returns_span(self):
        """start_span returns a usable span."""
        init_tracing(enabled=True, exporter_type="none")
        span = start_span("test", attributes={"key": "value"})
        assert span is not None
        span.end()
        shutdown_tracing()

    def test_start_span_disabled(self):
        """start_span returns no-op when disabled."""
        init_tracing(enabled=False, exporter_type="none")
        span = start_span("test")
        assert span is not None
        span.end()
        shutdown_tracing()

    def test_start_as_current_span_context_manager(self):
        """start_as_current_span works as context manager."""
        init_tracing(enabled=True, exporter_type="none")
        with start_as_current_span("test") as span:
            assert span is not None
        shutdown_tracing()

    def test_start_as_current_span_disabled(self):
        """start_as_current_span returns no-op when disabled."""
        init_tracing(enabled=False, exporter_type="none")
        with start_as_current_span("test") as span:
            assert span is not None
        shutdown_tracing()


class TestAttributeHelpers:
    """Tests for attribute creation helpers."""

    def test_messaging_attributes(self):
        """make_messaging_attributes creates correct dict."""
        attrs = make_messaging_attributes(
            operation="publish",
            destination="quote",
            sender_id="mod_1",
            correlation_id="abc123",
            message_size=256,
        )
        assert attrs["messaging.system"] == "tyche"
        assert attrs["messaging.destination"] == "quote"
        assert attrs["messaging.operation"] == "publish"
        assert attrs["sender_id"] == "mod_1"
        assert attrs["correlation_id"] == "abc123"
        assert attrs["message_size"] == 256

    def test_messaging_attributes_minimal(self):
        """make_messaging_attributes works with minimal args."""
        attrs = make_messaging_attributes(operation="receive", destination="trade")
        assert attrs["messaging.system"] == "tyche"
        assert attrs["messaging.destination"] == "trade"
        assert attrs["messaging.operation"] == "receive"
        assert "sender_id" not in attrs

    def test_rpc_attributes(self):
        """make_rpc_attributes creates correct dict."""
        attrs = make_rpc_attributes(
            method="compute",
            service="worker",
            correlation_id="abc123",
        )
        assert attrs["rpc.system"] == "tyche"
        assert attrs["rpc.method"] == "compute"
        assert attrs["rpc.service"] == "worker"
        assert attrs["correlation_id"] == "abc123"

    def test_rpc_attributes_minimal(self):
        """make_rpc_attributes works with minimal args."""
        attrs = make_rpc_attributes(method="compute")
        assert attrs["rpc.system"] == "tyche"
        assert attrs["rpc.method"] == "compute"
        assert "rpc.service" not in attrs


class TestGlobalTracer:
    """Tests for global tracer singleton."""

    def test_get_tracer_returns_instance(self):
        """get_tracer returns a TycheTracer."""
        shutdown_tracing()
        tracer = get_tracer()
        assert isinstance(tracer, TycheTracer)

    def test_init_tracing_returns_instance(self):
        """init_tracing returns a TycheTracer."""
        shutdown_tracing()
        tracer = init_tracing(enabled=True, exporter_type="none")
        assert isinstance(tracer, TycheTracer)
        shutdown_tracing()

    def test_init_tracing_overrides_global(self):
        """init_tracing replaces the global instance."""
        shutdown_tracing()
        t1 = init_tracing(service_name="first", enabled=False, exporter_type="none")
        t2 = init_tracing(service_name="second", enabled=False, exporter_type="none")
        assert t1._service_name == "first"
        assert t2._service_name == "second"
        assert get_tracer()._service_name == "second"
        shutdown_tracing()
