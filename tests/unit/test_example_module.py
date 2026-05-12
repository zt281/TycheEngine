"""Tests for ExampleModule v3 interface patterns and handler behavior."""

from modules.example import ExampleModule
from tyche.types import Endpoint, InterfacePattern


def test_example_module_init():
    """ExampleModule generates an example-prefixed module ID."""
    module = ExampleModule(engine_endpoint=Endpoint("127.0.0.1", 5555))
    assert module.module_id.startswith("example")


def test_example_module_discovers_v3_interfaces():
    """ExampleModule only registers signal pair handlers (on_ping, on_pong)."""
    module = ExampleModule(engine_endpoint=Endpoint("127.0.0.1", 5555))
    names = {i.name: i.pattern for i in module.interfaces}

    assert names["on_ping"] == InterfacePattern.ON
    assert names["on_pong"] == InterfacePattern.ON
    assert len(module.interfaces) == 2

    # Generic demo handlers are NOT registered as interfaces
    assert "on_data" not in names
    assert "on_message" not in names
    assert "on_broadcast" not in names
    # Producer declarations are NOT registered
    assert "send_ping" not in names
    assert "send_pong" not in names


def test_on_data_handler_records_event():
    """on_data handler stores the event in received_events."""
    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="exampletest01",
    )
    module.on_data({"message": "hello"})

    assert len(module.received_events) == 1
    assert module.received_events[0]["event"] == "on_data"
    assert module.received_events[0]["payload"]["message"] == "hello"


def test_on_broadcast_records_event():
    """on_broadcast stores the event."""
    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="exampletest01",
    )
    module.on_broadcast({"topic": "alert"})

    assert len(module.received_events) == 1
    assert module.received_events[0]["event"] == "on_broadcast"


def test_on_ping_triggers_pong():
    """on_ping schedules a pong broadcast after a delay."""
    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="exampletest01",
    )
    module._running = True  # so _schedule_timer is not skipped
    module.on_ping({"sender": "other", "value": 42})

    assert module.ping_count == 1
    # A timer should be scheduled
    assert len(module._pending_timers) >= 1


def test_on_ping_ignores_self():
    """on_ping skips responding if the ping came from this module."""
    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="exampletest01",
    )
    module.on_ping({"sender": "exampletest01", "value": 42})

    assert module.ping_count == 0


def test_on_pong_ignores_self():
    """on_pong skips counting if the pong came from this module."""
    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="exampletest01",
    )
    module.on_pong({"sender": "exampletest01"})

    assert module.pong_count == 0


def test_get_stats():
    """get_stats returns correct module statistics."""
    module = ExampleModule(
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
