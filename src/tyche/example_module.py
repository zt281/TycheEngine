"""Example Module demonstrating all Tyche interface patterns.

This module serves as a reference implementation showing:
- on_{event}: Fire-and-forget event handling
- ack_{event}: Request-response with acknowledgment
- whisper_{target}_{event}: Direct P2P messaging
- on_common_{event}: Broadcast event handling
- Ping-pong: Broadcast message passing between modules
"""

import random
import threading
import time
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
        module_id: Optional[str] = None,
        heartbeat_receive_endpoint: Optional[Endpoint] = None
    ):
        # Use athena as default deity
        if module_id is None:
            from tyche.types import ModuleId
            module_id = ModuleId.generate("athena")

        super().__init__(
            engine_endpoint=engine_endpoint,
            module_id=module_id,
            heartbeat_receive_endpoint=heartbeat_receive_endpoint
        )

        # Track received events for demonstration
        self.received_events: list = []
        self.request_count = 0
        self.ping_count = 0
        self.pong_count = 0

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

    def on_common_ping(self, payload: Dict[str, Any]) -> None:
        """Handle ping broadcast - respond with pong after random delay.

        Pattern: on_common_{event}
        Creates a ping-pong message passing demonstration between modules.

        Args:
            payload: Broadcast data containing 'sender' module ID
        """
        sender = payload.get("sender", "unknown")
        self.ping_count += 1
        print(f"[{self.module_id}] ping received from {sender} (total: {self.ping_count})")

        # Broadcast pong after random delay (< 1 second)
        delay = random.uniform(0.1, 0.9)
        threading.Timer(delay, self._broadcast_pong).start()
        print(f"[{self.module_id}] scheduling pong in {delay:.2f}s")

    def on_common_pong(self, payload: Dict[str, Any]) -> None:
        """Handle pong broadcast - respond with ping after random delay.

        Pattern: on_common_{event}
        Creates a ping-pong message passing demonstration between modules.

        Args:
            payload: Broadcast data containing 'sender' module ID
        """
        sender = payload.get("sender", "unknown")
        self.pong_count += 1
        print(f"[{self.module_id}] pong received from {sender} (total: {self.pong_count})")

        # Broadcast ping after random delay (< 1 second)
        delay = random.uniform(0.1, 0.9)
        threading.Timer(delay, self._broadcast_ping).start()
        print(f"[{self.module_id}] scheduling ping in {delay:.2f}s")

    def _broadcast_ping(self) -> None:
        """Broadcast a ping message to all modules."""
        print(f"[{self.module_id}] broadcasting ping")
        self.send_event("broadcast_ping", {"sender": self.module_id})

    def _broadcast_pong(self) -> None:
        """Broadcast a pong message to all modules."""
        print(f"[{self.module_id}] broadcasting pong")
        self.send_event("broadcast_pong", {"sender": self.module_id})

    def start_ping_pong(self) -> None:
        """Start the ping-pong cycle by broadcasting initial ping."""
        print(f"[{self.module_id}] starting ping-pong cycle")
        self._broadcast_ping()

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
            "ping_count": self.ping_count,
            "pong_count": self.pong_count,
            "interfaces": [i.name for i in self._interfaces]
        }
