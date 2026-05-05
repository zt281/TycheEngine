"""Tests for ExampleModule interface patterns and handler behavior."""

from tyche.example_module import ExampleModule
from tyche.types import Endpoint


def test_example_module_init():
    """ExampleModule generates an athena-prefixed module ID."""
    module = ExampleModule(engine_endpoint=Endpoint("127.0.0.1", 5555))
    assert module.module_id.startswith("athena")


def test_example_module_discovers_all_interfaces():
    """ExampleModule auto-discovers handler methods as interfaces."""
    module = ExampleModule(engine_endpoint=Endpoint("127.0.0.1", 5555))
    names = {i.name for i in module.interfaces}

    assert "broadcasted_ping" in names
    assert "broadcasted_pong" not in names  # no handler for pong


def test_on_broadcasted_ping_handler():
    """on_broadcasted_ping handler increments ping_count."""
    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="athenatest01",
    )
    module.on_broadcasted_ping({"sender": "other", "value": 42})

    assert module.ping_count == 1


def test_on_broadcasted_ping_skips_self():
    """on_broadcasted_ping skips messages from itself."""
    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="athenatest01",
    )
    module.on_broadcasted_ping({"sender": "athenatest01", "value": 42})

    assert module.ping_count == 0


def test_get_stats():
    """get_stats returns correct module statistics."""
    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="athenatest01",
    )

    stats = module.get_stats()
    assert stats["module_id"] == "athenatest01"
    assert stats["registered"] is False
    assert "broadcasted_ping" in stats["interfaces"]
