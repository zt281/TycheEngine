"""Unit tests for Message trace context integration."""

import pytest

from src.tyche.message import Message, deserialize, serialize
from src.tyche.tracing import (
    TRACE_CONTEXT_KEY,
    extract_trace_context,
    init_tracing,
    inject_trace_context,
    shutdown_tracing,
    start_as_current_span,
)
from src.tyche.types import DurabilityLevel, MessageType


class TestMessageTraceContext:
    """Tests for Message trace context helpers."""

    def setup_method(self):
        """Reset tracing state before each test."""
        shutdown_tracing()

    def teardown_method(self):
        """Clean up tracing state after each test."""
        shutdown_tracing()

    def test_with_trace_context_injects(self):
        """with_trace_context injects trace context into payload."""
        init_tracing(enabled=True, exporter_type="none")
        msg = Message(
            msg_type=MessageType.EVENT,
            sender="test",
            event="quote",
            payload={"price": 100.0},
        )

        with start_as_current_span("test"):
            msg.with_trace_context()

        assert TRACE_CONTEXT_KEY in msg.payload
        assert "traceparent" in msg.payload[TRACE_CONTEXT_KEY]

    def test_get_trace_context_extracts(self):
        """get_trace_context extracts trace context from payload."""
        init_tracing(enabled=True, exporter_type="none")
        msg = Message(
            msg_type=MessageType.EVENT,
            sender="test",
            event="quote",
            payload={"price": 100.0},
        )

        with start_as_current_span("test"):
            msg.with_trace_context()

        ctx = msg.get_trace_context()
        assert ctx is not None

    def test_get_trace_context_none_when_empty(self):
        """get_trace_context returns None when no context present."""
        init_tracing(enabled=True, exporter_type="none")
        msg = Message(
            msg_type=MessageType.EVENT,
            sender="test",
            event="quote",
            payload={"price": 100.0},
        )
        ctx = msg.get_trace_context()
        assert ctx is None

    def test_strip_trace_context_removes(self):
        """strip_trace_context removes trace context from payload."""
        init_tracing(enabled=True, exporter_type="none")
        msg = Message(
            msg_type=MessageType.EVENT,
            sender="test",
            event="quote",
            payload={"price": 100.0},
        )

        with start_as_current_span("test"):
            msg.with_trace_context()

        assert TRACE_CONTEXT_KEY in msg.payload
        msg.strip_trace_context()
        assert TRACE_CONTEXT_KEY not in msg.payload
        assert msg.payload["price"] == 100.0

    def test_serialization_roundtrip_with_trace_context(self):
        """Serialization preserves trace context through encode/decode."""
        init_tracing(enabled=True, exporter_type="none")
        msg = Message(
            msg_type=MessageType.EVENT,
            sender="test",
            event="quote",
            payload={"price": 100.0},
        )

        with start_as_current_span("producer"):
            msg.with_trace_context()

        # Serialize and deserialize
        data = serialize(msg)
        restored = deserialize(data)

        assert TRACE_CONTEXT_KEY in restored.payload
        assert "traceparent" in restored.payload[TRACE_CONTEXT_KEY]

        # Extract context from restored message
        ctx = restored.get_trace_context()
        assert ctx is not None

    def test_with_trace_context_disabled(self):
        """with_trace_context is no-op when tracing disabled."""
        init_tracing(enabled=False, exporter_type="none")
        msg = Message(
            msg_type=MessageType.EVENT,
            sender="test",
            event="quote",
            payload={"price": 100.0},
        )
        msg.with_trace_context()
        assert TRACE_CONTEXT_KEY not in msg.payload

    def test_chaining_with_trace_context(self):
        """with_trace_context returns self for chaining."""
        init_tracing(enabled=True, exporter_type="none")
        msg = Message(
            msg_type=MessageType.EVENT,
            sender="test",
            event="quote",
            payload={"price": 100.0},
        )

        with start_as_current_span("test"):
            result = msg.with_trace_context()

        assert result is msg
