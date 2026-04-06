"""Tests for TycheModule."""
from tyche.module import TycheModule
from tyche.types import Endpoint


def test_module_init():
    """Module initializes with engine endpoint."""
    module = TycheModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="zeus3f7a9c"
    )
    assert module.module_id == "zeus3f7a9c"
    assert module.engine_endpoint.port == 5555


def test_module_auto_generates_id():
    """Module auto-generates ID if not provided."""
    module = TycheModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555)
    )
    assert module.module_id is not None
    # Format: {deity}{6-char MD5} - deity varies in length (4-10 chars)
    assert len(module.module_id) >= 10  # min 4 + 6
    assert len(module.module_id) <= 16  # max 10 (hephaestus) + 6


def test_module_adds_interface():
    """Module can add interfaces."""
    module = TycheModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="zeus3f7a9c"
    )

    def handler(payload):
        pass

    module.add_interface("on_data", handler)

    assert "on_data" in module._handlers
    assert module._handlers["on_data"] == handler
