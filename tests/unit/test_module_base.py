"""Tests for ModuleBase protocol."""

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


def test_protocol_structural_subtyping():
    """ModuleBase supports structural subtyping via Protocol."""

    class DuckModule:
        def __init__(self) -> None:
            self._id = "duck_mod"

        @property
        def module_id(self) -> str:
            return self._id

        def start(self) -> None:
            pass

        def stop(self) -> None:
            pass

    mod = DuckModule()
    assert isinstance(mod, ModuleBase)


def test_protocol_rejects_incomplete_class():
    """A class missing protocol methods is not an instance of ModuleBase."""

    class IncompleteModule:
        def __init__(self) -> None:
            self._id = "incomplete"

        @property
        def module_id(self) -> str:
            return self._id

        # missing start() and stop()

    mod = IncompleteModule()
    assert not isinstance(mod, ModuleBase)


def test_module_base_has_no_concrete_methods():
    """ModuleBase provides only protocol methods — no dispatch logic."""
    # __protocol_attrs__ is only available on Python 3.12+
    protocol_attrs = getattr(ModuleBase, "__protocol_attrs__", None)
    if protocol_attrs is not None:
        assert "module_id" in protocol_attrs
        assert "start" in protocol_attrs
        assert "stop" in protocol_attrs
    # Concrete methods from old design are gone
    assert not hasattr(ModuleBase, "discover_interfaces")
    assert not hasattr(ModuleBase, "get_handler")
    assert not hasattr(ModuleBase, "handle_event")
