"""Protocol / abstract base class for Tyche modules."""

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
