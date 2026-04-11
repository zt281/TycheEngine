"""Tests for ModuleBase abstract class."""

import pytest

from tyche.module_base import ModuleBase
from tyche.types import InterfacePattern


class ConcreteModule(ModuleBase):
    """Concrete test implementation of ModuleBase."""

    def __init__(self) -> None:
        self._id = "test_mod"
        self.started = False

    @property
    def module_id(self) -> str:
        return self._id

    @property
    def interfaces(self):  # type: ignore[override]
        return []

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.started = False

    def on_data(self, payload: dict) -> None:
        pass

    def ack_order(self, payload: dict) -> dict:
        return {"confirmed": True, "id": payload.get("id")}

    def on_common_alert(self, payload: dict) -> None:
        pass

    def whisper_target_msg(self, payload: dict) -> None:
        pass


def test_module_base_is_abstract():
    """ModuleBase cannot be instantiated directly."""
    with pytest.raises(TypeError):
        ModuleBase()  # type: ignore[abstract]


def test_concrete_module_can_instantiate():
    """A properly-implemented subclass can be instantiated."""
    mod = ConcreteModule()
    assert mod.module_id == "test_mod"


def test_interface_discovery_all_patterns():
    """discover_interfaces finds on_, ack_, on_common_, and whisper_ methods."""
    mod = ConcreteModule()
    interfaces = mod.discover_interfaces()
    patterns = {i.name: i.pattern for i in interfaces}

    assert patterns["on_data"] == InterfacePattern.ON
    assert patterns["ack_order"] == InterfacePattern.ACK
    assert patterns["on_common_alert"] == InterfacePattern.ON_COMMON
    assert patterns["whisper_target_msg"] == InterfacePattern.WHISPER


def test_get_handler_returns_callable():
    """get_handler returns the handler method for a known event."""
    mod = ConcreteModule()
    handler = mod.get_handler("on_data")
    assert handler is not None
    assert callable(handler)


def test_get_handler_returns_none_for_unknown():
    """get_handler returns None for an unregistered event name."""
    mod = ConcreteModule()
    assert mod.get_handler("on_nonexistent") is None


def test_handle_event_on_pattern():
    """handle_event for on_ pattern calls handler and returns None."""
    mod = ConcreteModule()
    result = mod.handle_event("on_data", {"key": "val"})
    assert result is None


def test_handle_event_ack_pattern():
    """handle_event for ack_ pattern returns handler's return value."""
    mod = ConcreteModule()
    result = mod.handle_event("ack_order", {"id": "42"})
    assert result == {"confirmed": True, "id": "42"}


def test_handle_event_unknown_raises():
    """handle_event raises ValueError for unknown events."""
    mod = ConcreteModule()
    with pytest.raises(ValueError, match="No handler for event"):
        mod.handle_event("unknown_event", {})
