"""Tests for ModuleBase abstract base class."""

import pytest

from tyche.module_base import ModuleBase


def test_module_base_is_abstract():
    """ModuleBase cannot be instantiated directly."""
    with pytest.raises(TypeError):
        ModuleBase()  # type: ignore[abstract]


def test_concrete_module_can_instantiate():
    """A properly-implemented subclass can be instantiated."""

    class ConcreteModule(ModuleBase):
        def __init__(self) -> None:
            self._id = "test_mod"

        @property
        def module_id(self) -> str:
            return self._id

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    mod = ConcreteModule()
    assert mod.module_id == "test_mod"


def test_concrete_module_lifecycle():
    """Concrete module implements start/stop lifecycle."""

    class LifecycleModule(ModuleBase):
        def __init__(self) -> None:
            self._id = "lifecycle_mod"
            self.running = False

        @property
        def module_id(self) -> str:
            return self._id

        def start(self) -> None:
            self.running = True

        def stop(self) -> None:
            self.running = False

    mod = LifecycleModule()
    assert not mod.running
    mod.start()
    assert mod.running
    mod.stop()
    assert not mod.running


def test_module_base_has_no_concrete_methods():
    """ModuleBase provides only abstract methods — no dispatch logic."""
    abstract_methods = getattr(ModuleBase, "__abstractmethods__", set())
    assert "module_id" in abstract_methods
    assert "start" in abstract_methods
    assert "stop" in abstract_methods
    # Concrete methods from old design are gone
    assert not hasattr(ModuleBase, "discover_interfaces")
    assert not hasattr(ModuleBase, "get_handler")
    assert not hasattr(ModuleBase, "handle_event")
