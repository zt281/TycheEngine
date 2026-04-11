"""Tests for TycheModule core functionality."""

from tyche.module import TycheModule
from tyche.types import Endpoint, InterfacePattern


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
    # Deity names range from 4 chars ("zeus") to 11 chars ("hephaestus")
    # plus 6 hex chars = 10 to 17 total
    assert len(module.module_id) >= 10
    assert len(module.module_id) <= 17


def test_module_add_interface():
    """add_interface registers handler and creates Interface entry."""
    module = TycheModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="test_mod",
    )

    def handler(payload: dict) -> None:
        pass

    module.add_interface("on_data", handler, pattern=InterfacePattern.ON)

    assert len(module.interfaces) == 1
    assert module.interfaces[0].name == "on_data"
    assert module.interfaces[0].pattern == InterfacePattern.ON
    assert module._handlers["on_data"] is handler


def test_module_add_multiple_interfaces():
    """Multiple interfaces can be added with different patterns."""
    module = TycheModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="test_mod",
    )

    module.add_interface("on_data", lambda p: None, pattern=InterfacePattern.ON)
    module.add_interface("ack_req", lambda p: {}, pattern=InterfacePattern.ACK)

    assert len(module.interfaces) == 2
    patterns = {i.name: i.pattern for i in module.interfaces}
    assert patterns["on_data"] == InterfacePattern.ON
    assert patterns["ack_req"] == InterfacePattern.ACK


def test_module_has_run_and_stop():
    """TycheModule exposes run(), stop(), and start_nonblocking() methods."""
    module = TycheModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="test_mod",
    )
    assert callable(getattr(module, "run", None))
    assert callable(getattr(module, "stop", None))
    assert callable(getattr(module, "start_nonblocking", None))
