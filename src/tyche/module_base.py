"""Protocol / abstract base class for Tyche modules."""

import time
from typing import Protocol, runtime_checkable


@runtime_checkable
class ModuleBase(Protocol):
    """Lightweight protocol defining the module contract.

    Subclasses must implement:
    - ``module_id`` property
    - ``start()`` lifecycle method
    - ``stop()`` lifecycle method

    All event discovery, dispatch, and registration logic lives in
    ``TycheModule`` — this base class intentionally provides no
    concrete methods.
    """

    @property
    def module_id(self) -> str:
        """Return unique module identifier."""
        ...

    def start(self) -> None:
        """Start the module."""
        ...

    def stop(self) -> None:
        """Stop the module gracefully."""
        ...

    # ── Default Admin Handler Implementations ─────────────────────

    def _admin_health_check(self) -> dict:
        """Return module health status."""
        return {
            "status": "healthy",
            "module_id": self.module_id,
            "uptime": time.time() - self._start_time if hasattr(self, '_start_time') else 0,
        }

    def _admin_availability_check(self) -> dict:
        """Return detailed handler availability information."""
        return {
            "module_id": self.module_id,
            "handlers": self._get_handler_availability() if hasattr(self, '_get_handler_availability') else {},
        }

    def _admin_respawn(self) -> dict:
        """Trigger module restart. Override for custom behavior."""
        # Default: signal for restart (the actual restart is handled externally)
        return {"status": "respawn_requested", "module_id": self.module_id}

    def _admin_decommission(self) -> dict:
        """Graceful shutdown. Override for custom behavior."""
        # Set a flag that the module's run loop should check
        self._decommissioned = True
        return {"status": "decommissioning", "module_id": self.module_id}
