"""Tests for ExampleModule interface patterns and handler behavior."""

from tyche.example_module import ExampleModule
from tyche.types import Endpoint


def test_example_module_init():
    """ExampleModule generates an athena-prefixed module ID."""
    module = ExampleModule(engine_endpoint=Endpoint("127.0.0.1", 5555))
    assert module.module_id.startswith("athena")


def test_example_module_discovers_all_interfaces():
    """ExampleModule auto-discovers all handler methods as interfaces."""
    module = ExampleModule(engine_endpoint=Endpoint("127.0.0.1", 5555))
    names = {i.name for i in module.interfaces}

    assert "on_streaming_data" in names
    assert "handle_broadcasted_request" in names
    assert "on_whispered_message" in names
    assert "on_broadcasted_broadcast" in names
    assert "on_broadcasted_ping" in names
    # Note: on_broadcasted_pong handler is intentionally not implemented to avoid infinite ping-pong loops


def test_on_streaming_data_handler_records_event():
    """on_streaming_data handler stores the event in received_events."""
    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="athenatest01",
    )
    module.on_streaming_data({"message": "hello"})

    assert len(module.received_events) == 1
    assert module.received_events[0]["event"] == "on_streaming_data"
    assert module.received_events[0]["payload"]["message"] == "hello"


def test_handle_broadcasted_request_returns_response():
    """handle_broadcasted_request handler returns acknowledgment with request details."""
    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="athenatest01",
    )
    response = module.handle_broadcasted_request({"request_id": "req_123"})

    assert response["status"] == "acknowledged"
    assert response["request_id"] == "req_123"
    assert response["module_id"] == "athenatest01"
    assert response["count"] == 1


def test_handle_broadcasted_request_increments_count():
    """handle_broadcasted_request handler increments request_count on each call."""
    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="athenatest01",
    )
    module.handle_broadcasted_request({"request_id": "1"})
    module.handle_broadcasted_request({"request_id": "2"})
    resp = module.handle_broadcasted_request({"request_id": "3"})

    assert resp["count"] == 3
    assert module.request_count == 3


def test_on_broadcasted_broadcast_records_event():
    """on_broadcasted_broadcast stores the event."""
    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="athenatest01",
    )
    module.on_broadcasted_broadcast({"topic": "alert"})

    assert len(module.received_events) == 1
    assert module.received_events[0]["event"] == "on_broadcasted_broadcast"


def test_get_stats():
    """get_stats returns correct module statistics."""
    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="athenatest01",
    )
    module.on_streaming_data({"a": 1})
    module.handle_broadcasted_request({"request_id": "r1"})

    stats = module.get_stats()
    assert stats["module_id"] == "athenatest01"
    assert stats["request_count"] == 1
    assert stats["events_received"] == 1
    assert "on_streaming_data" in stats["interfaces"]
    assert "handle_broadcasted_request" in stats["interfaces"]
