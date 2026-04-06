"""Abstract base class for Tyche modules."""

import inspect
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, cast

from tyche.types import DurabilityLevel, Interface, InterfacePattern


class ModuleBase(ABC):
    """Abstract base for all Tyche Engine modules.

    Modules implement event handlers using naming conventions:
    - on_{event}: Fire-and-forget event handler
    - ack_{event}: Handler that must return ACK
    - whisper_{target}_{event}: Direct P2P handler
    - on_common_{event}: Broadcast event handler

    Example:
        class MyModule(ModuleBase):
            @property
            def module_id(self) -> str:
                return ModuleId.generate("athena")

            def on_price_update(self, payload: dict) -> None:
                print(f"Price: {payload}")

            def ack_order(self, payload: dict) -> dict:
                return {"status": "confirmed", "id": payload['id']}
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

    def discover_interfaces(self) -> List[Interface]:
        """Auto-discover interfaces from method names.

        Scans methods for naming patterns:
        - on_* -> ON pattern
        - ack_* -> ACK pattern
        - whisper_* -> WHISPER pattern
        - on_common_* -> ON_COMMON pattern

        Returns:
            List of Interface definitions
        """
        interfaces = []

        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            pattern = self._get_pattern_for_name(name)
            if pattern:
                interfaces.append(Interface(
                    name=name,
                    pattern=pattern,
                    event_type=name,  # Event type matches method name
                    durability=DurabilityLevel.ASYNC_FLUSH
                ))

        return interfaces

    def _get_pattern_for_name(self, name: str) -> Optional[InterfacePattern]:
        """Determine interface pattern from method name."""
        if name.startswith("on_common_"):
            return InterfacePattern.ON_COMMON
        elif name.startswith("whisper_"):
            return InterfacePattern.WHISPER
        elif name.startswith("ack_"):
            return InterfacePattern.ACK
        elif name.startswith("on_"):
            return InterfacePattern.ON
        return None

    def get_handler(self, event: str) -> Optional[Callable]:
        """Get handler method for an event.

        Args:
            event: Event name (e.g., "on_data", "ack_request")

        Returns:
            Handler method or None
        """
        handler = getattr(self, event, None)
        if callable(handler):
            return cast(Callable[..., Any], handler)
        return None

    def handle_event(self, event: str, payload: Dict[str, Any]) -> Any:
        """Route event to appropriate handler.

        Args:
            event: Event name
            payload: Event payload

        Returns:
            Handler result (None for ON pattern, dict for ACK pattern)
        """
        handler = self.get_handler(event)
        if handler is None:
            raise ValueError(f"No handler for event: {event}")

        # Check if this is an ack pattern (needs return value)
        if event.startswith("ack_"):
            return handler(payload)
        else:
            handler(payload)
            return None
