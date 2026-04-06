"""Tests for module base class."""
import pytest

from tyche.module_base import ModuleBase


def test_module_base_is_abstract():
    """ModuleBase cannot be instantiated directly."""
    with pytest.raises(TypeError):
        ModuleBase()


def test_concrete_module_can_instantiate():
    """Concrete subclass can be instantiated."""
    class TestModule(ModuleBase):
        @property
        def module_id(self) -> str:
            return "test123"

        @property
        def interfaces(self) -> list:
            return []

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    module = TestModule()
    assert module.module_id == "test123"


def test_interface_discovery():
    """Module discovers interfaces from methods."""
    class TestModule(ModuleBase):
        @property
        def module_id(self) -> str:
            return "test123"

        def on_data(self, payload: dict) -> None:
            """Handle data event."""
            pass

        def ack_request(self, payload: dict) -> dict:
            """Handle request with ACK."""
            return {"status": "ok"}

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    module = TestModule()
    interfaces = module.discover_interfaces()

    names = [i.name for i in interfaces]
    assert "on_data" in names
    assert "ack_request" in names
