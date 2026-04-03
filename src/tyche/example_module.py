"""Example Module demonstrating all Tyche interface patterns.

This module serves as a reference implementation showing:
- on_{event}: Fire-and-forget event handling
- ack_{event}: Request-response with acknowledgment
- whisper_{target}_{event}: Direct P2P messaging
- on_common_{event}: Broadcast event handling
"""

from typing import Any, Dict, Optional
from tyche.module import TycheModule
from tyche.types import Endpoint


class ExampleModule(TycheModule):
    """Example module with all interface patterns.

    Demonstrates:
    - on_data: Fire-and-forget event handler
    - ack_request: Request-response handler
    - whisper_target_message: Direct P2P handler
    - on_common_broadcast: Broadcast event handler

    Args:
        engine_endpoint: TycheEngine registration endpoint
        module_id: Optional explicit module ID
    """

    def __init__(
        self,
        engine_endpoint: Endpoint,
        module_id: Optional[str] = None
    ):
        # Use athena as default deity
        if module_id is None:
            from tyche.types import ModuleId
            module_id = ModuleId.generate("athena")

        super().__init__(
            engine_endpoint=engine_endpoint,
            module_id=module_id
        )

        # Track received events for demonstration
        self.received_events: list = []
        self.request_count = 0

        # Auto-discover interfaces from methods
        self._interfaces = self.discover_interfaces()

    def on_data(self, payload: Dict[str, Any]) -> None:
        """Handle fire-and-forget data events.

        Pattern: on_{event}
        Delivery: At-least-once, FIFO
        Behavior: No response required

        Args:
            payload: Event data containing 'message' or other fields
        """
        self.received_events.append({
            "event": "on_data",
            "payload": payload
        })
        print(f"[{self.module_id}] on_data received: {payload}")

    def ack_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle request with acknowledgment.

        Pattern: ack_{event}
        Delivery: At-least-once with confirmation
        Behavior: Must return ACK response within timeout

        Args:
            payload: Request data containing 'request_id' and other fields

        Returns:
            ACK response with status and request_id
        """
        self.request_count += 1
        request_id = payload.get("request_id", "unknown")

        response = {
            "status": "acknowledged",
            "request_id": request_id,
            "module_id": self.module_id,
            "count": self.request_count
        }

        print(f"[{self.module_id}] ack_request processed: {request_id}")
        return response

    def whisper_athena_message(
        self,
        payload: Dict[str, Any],
        sender: Optional[str] = None
    ) -> None:
        """Handle direct P2P whisper message.

        Pattern: whisper_{target}_{event}
        Delivery: Best-effort or confirmed (configurable)
        Behavior: Direct module-to-module, bypasses Engine routing

        Args:
            payload: Message data
            sender: Optional sender module ID
        """
        self.received_events.append({
            "event": "whisper_athena_message",
            "payload": payload,
            "sender": sender
        })
        print(f"[{self.module_id}] whisper received from {sender}: {payload}")

    def on_common_broadcast(self, payload: Dict[str, Any]) -> None:
        """Handle broadcast events to ALL subscribers.

        Pattern: on_common_{event}
        Delivery: Best-effort broadcast
        Behavior: All subscribers receive, no back-pressure

        Args:
            payload: Broadcast data
        """
        self.received_events.append({
            "event": "on_common_broadcast",
            "payload": payload
        })
        print(f"[{self.module_id}] broadcast received: {payload}")

    def get_stats(self) -> Dict[str, Any]:
        """Return module statistics.

        Returns:
            Dict with event counts and status
        """
        return {
            "module_id": self.module_id,
            "registered": self._registered,
            "request_count": self.request_count,
            "events_received": len(self.received_events),
            "interfaces": [i.name for i in self._interfaces]
        }
