"""Tests for src.tyche.module_base module."""
import time

from src.tyche.module_base import ModuleBase


class DummyModule(ModuleBase):
    """Concrete implementation of ModuleBase Protocol for testing."""

    @property
    def module_id(self) -> str:
        return "dummy_mod"

    def start(self) -> None:
        self._start_time = time.time()

    def stop(self) -> None:
        pass


def test_module_base_is_protocol():
    """ModuleBase is a runtime-checkable Protocol."""
    assert isinstance(DummyModule(), ModuleBase)


def test_admin_health_check_without_start_time():
    """health_check without _start_time should report 0 uptime."""
    mod = DummyModule()
    result = mod._admin_health_check()
    assert result["status"] == "healthy"
    assert result["module_id"] == "dummy_mod"
    assert result["uptime"] == 0


def test_admin_health_check_with_start_time():
    """health_check with _start_time should report positive uptime."""
    mod = DummyModule()
    mod._start_time = time.time() - 5.0
    result = mod._admin_health_check()
    assert result["status"] == "healthy"
    assert result["uptime"] >= 4.5
    assert result["uptime"] < 10.0


def test_admin_availability_check_without_get_handler_availability():
    """availability_check without _get_handler_availability returns empty dict."""
    mod = DummyModule()
    result = mod._admin_availability_check()
    assert result["module_id"] == "dummy_mod"
    assert result["handlers"] == {}


def test_admin_availability_check_with_get_handler_availability():
    """availability_check uses _get_handler_availability if available."""
    mod = DummyModule()
    mod._get_handler_availability = lambda: {"compute": True, "fetch": False}
    result = mod._admin_availability_check()
    assert result["handlers"] == {"compute": True, "fetch": False}


def test_admin_respawn():
    """respawn returns expected status."""
    mod = DummyModule()
    result = mod._admin_respawn()
    assert result["status"] == "respawn_requested"
    assert result["module_id"] == "dummy_mod"


def test_admin_decommission_sets_flag():
    """decommission sets _decommissioned to True."""
    mod = DummyModule()
    assert not hasattr(mod, "_decommissioned")
    result = mod._admin_decommission()
    assert mod._decommissioned is True
    assert result["status"] == "decommissioning"
    assert result["module_id"] == "dummy_mod"
