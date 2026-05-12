"""Tests for RustExampleModule - verifies parity with Python ExampleModule."""

import pytest

from tyche.types import Endpoint


try:
    from rust_module.example import RustExampleModule
except ImportError:
    pytest.skip("Rust module not compiled", allow_module_level=True)


def test_rust_example_module_init():
    """RustExampleModule generates an example-prefixed module ID."""
    module = RustExampleModule(engine_endpoint=Endpoint("127.0.0.1", 5555))
    assert module.module_id.startswith("example")


def test_rust_example_module_discovers_v3_interfaces():
    """RustExampleModule only registers signal pair handlers (on_ping, on_pong)."""
    module = RustExampleModule(engine_endpoint=Endpoint("127.0.0.1", 5555))
    names = {i["name"]: i["pattern"] for i in module.interfaces}

    assert names["on_ping"] == "on"
    assert names["on_pong"] == "on"
    assert len(module.interfaces) == 2

    # Generic demo handlers and producer declarations NOT registered
    assert "on_data" not in names
    assert "on_message" not in names
    assert "on_broadcast" not in names
    assert "send_ping" not in names
    assert "send_pong" not in names


def test_on_data_handler_records_event():
    """on_data handler stores the event in received_events."""
    module = RustExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="exampletest01",
    )
    module.on_data({"message": "hello"})

    assert len(module.received_events) == 1
    assert module.received_events[0]["event"] == "on_data"
    assert module.received_events[0]["payload"]["message"] == "hello"


def test_on_broadcast_records_event():
    """on_broadcast stores the event."""
    module = RustExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="exampletest01",
    )
    module.on_broadcast({"topic": "alert"})

    assert len(module.received_events) == 1
    assert module.received_events[0]["event"] == "on_broadcast"


def test_on_ping_ignores_self():
    """on_ping skips responding if the ping came from this module."""
    module = RustExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="exampletest01",
    )
    module.on_ping({"sender": "exampletest01", "value": 42})

    assert module.ping_count == 0


def test_on_pong_ignores_self():
    """on_pong skips counting if the pong came from this module."""
    module = RustExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="exampletest01",
    )
    module.on_pong({"sender": "exampletest01"})

    assert module.pong_count == 0


def test_get_stats():
    """get_stats returns correct module statistics."""
    module = RustExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="exampletest01",
    )
    module.on_data({"a": 1})
    module.on_broadcast({"b": 2})

    stats = module.get_stats()
    assert stats["module_id"] == "exampletest01"
    assert stats["events_received"] == 2
    assert "on_ping" in stats["interfaces"]
    assert "on_pong" in stats["interfaces"]
    assert len(stats["interfaces"]) == 2
