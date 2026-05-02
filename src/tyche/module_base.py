"""Protocol / abstract base class for Tyche modules."""

from abc import ABC, abstractmethod


class ModuleBase(ABC):
    """Lightweight abstract base defining the module contract.

    Subclasses must implement:
    - ``module_id`` property
    - ``start()`` lifecycle method
    - ``stop()`` lifecycle method

    All event discovery, dispatch, and registration logic lives in
    ``TycheModule`` — this base class intentionally provides no
    concrete methods.
    """

    @property
    @abstractmethod
    def module_id(self) -> str:
        """Return unique module identifier."""
        pass

    @abstractmethod
    def start(self) -> None:
        """Start the module."""
        pass

    @abstractmethod
    def stop(self) -> None:
        """Stop the module gracefully."""
        pass
