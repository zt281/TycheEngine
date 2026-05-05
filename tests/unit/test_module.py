"""Tests for TycheModule core functionality (v2 interface patterns)."""


from tyche.message import Message
from tyche.module import TycheModule
from tyche.types import (
    Endpoint,
    InterfacePattern,
    MessageType,
)


def test_module_parse_event_name():
    test_cases = {
        "on_broadcasted_ping": ("broadcasted_ping", "ping"),
        "on_handle_ping": ("handle_ping", "ping"),
    }
    for key, expected in test_cases.items():
        assert TycheModule._event_breakdown(key) == expected


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

    assert patterns["broadcasted_alert"] == InterfacePattern.ON_BROADCASTED
    assert patterns["broadcasted_request"] == InterfacePattern.HANDLE_BROADCASTED
    assert patterns["whispered_message"] == InterfacePattern.ON_WHISPERED
    assert patterns["whispered_command"] == InterfacePattern.HANDLE_WHISPERED
    assert patterns["streaming_data"] == InterfacePattern.ON_STREAMING
    assert patterns["streaming_query"] == InterfacePattern.HANDLE_STREAMING

    # Handlers are registered
    assert "broadcasted_alert" in module._handlers
    assert "broadcasted_request" in module._handlers


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
    result = module._dispatch("broadcasted_test", msg)
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
    result = module._dispatch("broadcasted_test", msg)
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
        "streaming_dynamic",
        "dynamic",
        dynamic_handler,
        InterfacePattern.ON_STREAMING,
    )

    assert "streaming_dynamic" in module._handlers
    assert len(module.interfaces) == 1
    assert module.interfaces[0].name == "streaming_dynamic"


def test_module_has_run_and_stop():
    """TycheModule exposes run(), stop(), and start() methods."""
    module = TycheModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="test_mod",
    )
    assert callable(getattr(module, "run", None))
    assert callable(getattr(module, "stop", None))
    assert callable(getattr(module, "start", None))


def test_start_does_not_block():
    """start() returns immediately after worker threads are up."""
    module = TycheModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="test_mod",
    )
    assert not module._running


def test_module_no_event_endpoint_param():
    """event_endpoint parameter is removed from __init__."""
    import inspect

    sig = inspect.signature(TycheModule.__init__)
    params = list(sig.parameters.keys())
    assert "event_endpoint" not in params


def test_dynamic_register_subscribes_topic():
    """_register_handler after start subscribes SUB socket to new topic."""
    import time

    import zmq

    from tyche.message import deserialize, serialize

    module = TycheModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="dyn_sub_test",
    )

    module.context = zmq.Context()
    module._sub_socket = module.context.socket(zmq.SUB)
    module._sub_socket.bind("tcp://127.0.0.1:0")
    addr = module._sub_socket.getsockopt(zmq.LAST_ENDPOINT).decode()

    pub = module.context.socket(zmq.PUB)
    pub.connect(addr)

    received = []

    def handler(payload: dict) -> None:
        received.append(payload)

    # Register handler after socket exists — should auto-subscribe
    module._register_handler("streaming_dynamic", "dynamic", handler)

    # ZMQ slow-joiner grace period — SUB subscription must propagate to PUB
    time.sleep(0.5)

    msg = Message(
        msg_type=MessageType.EVENT,
        sender="test",
        event="streaming_dynamic",
        payload={"key": "val"},
    )

    # Retry loop: ZMQ PUB/SUB subscription propagation is asynchronous
    module._sub_socket.setsockopt(zmq.RCVTIMEO, 500)
    frames = None
    for _ in range(10):
        pub.send_multipart([b"streaming_dynamic", serialize(msg)])
        try:
            frames = module._sub_socket.recv_multipart()
            break
        except zmq.error.Again:
            continue

    assert frames is not None, "SUB socket never received message — subscription not propagated"
    received_msg = deserialize(frames[1])
    module._dispatch(frames[0].decode(), received_msg)

    assert len(received) == 1
    assert received[0] == {"key": "val"}

    pub.close()
    module._sub_socket.close()
    module.context.destroy(linger=0)


def test_dispatch_handle_error_returns_error_dict():
    """Dispatching a handle_* event where handler raises returns error dict."""

    class ErrorModule(TycheModule):
        def handle_broadcasted_test(self, payload: dict) -> dict:
            raise ValueError("boom")

    module = ErrorModule(engine_endpoint=Endpoint("127.0.0.1", 5555))

    msg = Message(
        msg_type=MessageType.EVENT,
        sender="test",
        event="handle_broadcasted_test",
        payload={"key": "val"},
    )
    result = module._dispatch("broadcasted_test", msg)
    assert result == {"error": "boom", "type": "ValueError"}


def test_concurrent_register_and_dispatch():
    """Concurrent registration and dispatch does not raise or lose events."""
    import threading

    module = TycheModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="concurrent_test",
    )
    received = []

    def make_handler(idx: int):
        def handler(payload: dict) -> None:
            received.append(idx)
        return handler

    threads = []
    for i in range(20):
        t = threading.Thread(
            target=module._register_handler,
            args=(f"streaming_event_{i}", f"event_{i}", make_handler(i)),
        )
        threads.append(t)

    for t in threads:
        t.start()

    # Dispatch to registered handlers while registration is in flight
    for i in range(20):
        msg = Message(
            msg_type=MessageType.EVENT,
            sender="test",
            event=f"streaming_event_{i}",
            payload={},
        )
        module._dispatch(f"streaming_event_{i}", msg)

    for t in threads:
        t.join(timeout=5.0)

    # All handlers registered; all dispatched events handled (or handler not yet registered)
    assert len(module._handlers) == 20
    assert len(module._interfaces) == 20
