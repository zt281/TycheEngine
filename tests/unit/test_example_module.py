"""Tests for ExampleModule."""
import pytest
from tyche.example_module import ExampleModule
from tyche.types import Endpoint


def test_example_module_init():
    """ExampleModule initializes correctly."""
    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555)
    )
    assert module.module_id.startswith("athena")


def test_example_module_has_on_handler():
    """ExampleModule has on_data handler."""
    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="athena123456"
    )

    # Add interfaces
    module._interfaces = module.discover_interfaces()

    names = [i.name for i in module._interfaces]
    assert "on_data" in names


def test_example_module_has_ack_handler():
    """ExampleModule has ack_request handler."""
    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="athena123456"
    )

    module._interfaces = module.discover_interfaces()

    names = [i.name for i in module._interfaces]
    assert "ack_request" in names


def test_on_data_handler():
    """on_data handler processes payload."""
    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="athena123456"
    )

    payload = {"message": "hello"}
    result = module.on_data(payload)

    assert result is None  # on_ pattern returns None


def test_ack_request_handler():
    """ack_request handler returns ACK."""
    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="athena123456"
    )

    payload = {"request_id": "123", "data": "test"}
    result = module.ack_request(payload)

    assert result is not None
    assert result["status"] == "acknowledged"
    assert result["request_id"] == "123"
    assert "module_id" in result
