"""Tests for TycheModule core functionality (v2 interface patterns)."""

from unittest.mock import MagicMock, patch

from tyche.module import TycheModule
from tyche.message import Message
from tyche.types import (
    Endpoint,
    InterfacePattern,
    MessageType,
)


def test_module_init_with_explicit_id():
    """TycheModule stores the explicit module_id and engine endpoint."""
    module = TycheModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="test_mod_01",
    )
    assert module.module_id == "test_mod_01"
    assert module.engine_endpoint.port == 5555


def test_module_auto_generates_id():
    """TycheModule generates a deity-prefixed ID when none is provided."""
    module = TycheModule(engine_endpoint=Endpoint("127.0.0.1", 5555))
    assert len(module.module_id) >= 10
    assert len(module.module_id) <= 17


def test_module_auto_discovers_all_patterns():
    """Auto-discovery finds all 6 v2 interface patterns from method names."""

    class DiscoveryModule(TycheModule):
        def on_broadcasted_alert(self, payload: dict) -> None:
            pass

        def handle_broadcasted_request(self, payload: dict) -> dict:
            return {"ack": True}

        def on_whispered_message(self, payload: dict) -> None:
            pass

        def handle_whispered_command(self, payload: dict) -> dict:
            return {"done": True}

        def on_streaming_data(self, payload: dict) -> None:
            pass

        def handle_streaming_query(self, payload: dict) -> dict:
            return {"result": []}

    module = DiscoveryModule(engine_endpoint=Endpoint("127.0.0.1", 5555))
    patterns = {i.name: i.pattern for i in module.interfaces}

    assert patterns["on_broadcasted_alert"] == InterfacePattern.ON_BROADCASTED
    assert patterns["handle_broadcasted_request"] == InterfacePattern.HANDLE_BROADCASTED
    assert patterns["on_whispered_message"] == InterfacePattern.ON_WHISPERED
    assert patterns["handle_whispered_command"] == InterfacePattern.HANDLE_WHISPERED
    assert patterns["on_streaming_data"] == InterfacePattern.ON_STREAMING
    assert patterns["handle_streaming_query"] == InterfacePattern.HANDLE_STREAMING

    # Handlers are registered
    assert "on_broadcasted_alert" in module._handlers
    assert "handle_broadcasted_request" in module._handlers


def test_module_dispatch_on_prefix_returns_none():
    """Dispatching an on_* event calls handler and returns None."""

    class DispatchModule(TycheModule):
        def on_broadcasted_test(self, payload: dict) -> None:
            self.called = True

    module = DispatchModule(engine_endpoint=Endpoint("127.0.0.1", 5555))
    module.called = False

    msg = Message(
        msg_type=MessageType.EVENT,
        sender="test",
        event="on_broadcasted_test",
        payload={"key": "val"},
    )
    result = module._dispatch("on_broadcasted_test", msg)
    assert result is None
    assert module.called


def test_module_dispatch_handle_prefix_returns_result():
    """Dispatching a handle_* event calls handler and returns its result."""

    class DispatchModule(TycheModule):
        def handle_broadcasted_test(self, payload: dict) -> dict:
            return {"status": "ok", "data": payload}

    module = DispatchModule(engine_endpoint=Endpoint("127.0.0.1", 5555))

    msg = Message(
        msg_type=MessageType.EVENT,
        sender="test",
        event="handle_broadcasted_test",
        payload={"key": "val"},
    )
    result = module._dispatch("handle_broadcasted_test", msg)
    assert result == {"status": "ok", "data": {"key": "val"}}


def test_module_register_handler_dynamic():
    """_register_handler allows subclasses to add handlers dynamically."""
    module = TycheModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="dyn_mod",
    )

    def dynamic_handler(payload: dict) -> None:
        pass

    module._register_handler(
        "on_streaming_dynamic",
        dynamic_handler,
        InterfacePattern.ON_STREAMING,
    )

    assert "on_streaming_dynamic" in module._handlers
    assert len(module.interfaces) == 1
    assert module.interfaces[0].name == "on_streaming_dynamic"


def test_module_has_run_and_stop():
    """TycheModule exposes run(), stop(), and start_nonblocking() methods."""
    module = TycheModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="test_mod",
    )
    assert callable(getattr(module, "run", None))
    assert callable(getattr(module, "stop", None))
    assert callable(getattr(module, "start_nonblocking", None))


def test_module_no_event_endpoint_param():
    """event_endpoint parameter is removed from __init__."""
    import inspect

    sig = inspect.signature(TycheModule.__init__)
    params = list(sig.parameters.keys())
    assert "event_endpoint" not in params
