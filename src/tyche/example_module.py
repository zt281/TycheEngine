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
from typing import Any, Dict, List, Optional

from tyche.module import TycheModule
from tyche.types import Endpoint, ModuleId


class ExampleModule(TycheModule):
    """Example module with all interface patterns.

    Demonstrates:
    - on_data: Fire-and-forget event handler
    - ack_request: Request-response handler
    - whisper_athena_message: Direct P2P handler
    - on_common_broadcast: Broadcast event handler

    Args:
        engine_endpoint: TycheEngine registration endpoint
        module_id: Optional explicit module ID
    """

    def __init__(
        self,
        engine_endpoint: Endpoint,
        module_id: Optional[str] = None,
        heartbeat_receive_endpoint: Optional[Endpoint] = None,
    ):
        if module_id is None:
            module_id = ModuleId.generate("athena")

        super().__init__(
            engine_endpoint=engine_endpoint,
            module_id=module_id,
            heartbeat_receive_endpoint=heartbeat_receive_endpoint,
        )

        # Track received events for demonstration
        self.received_events: List[Dict[str, Any]] = []
        self.request_count = 0
        self.ping_count = 0
        self.pong_count = 0

        # Track pending timers so we can cancel them on stop
        self._pending_timers: List[threading.Timer] = []
        self._timer_lock = threading.Lock()

        # Auto-discover interfaces from methods and register handlers
        for iface in self.discover_interfaces():
            handler = getattr(self, iface.name, None)
            if handler is not None:
                self.add_interface(iface.name, handler, iface.pattern, iface.durability)

    def _start_workers(self) -> None:
        """Start workers and kick off the ping-pong cycle."""
        super()._start_workers()
        if self._running and self._registered:
            self.start_ping_pong()

    def stop(self) -> None:
        """Stop the module and cancel all pending timers."""
        # Cancel outstanding timers before shutting down sockets
        with self._timer_lock:
            for timer in self._pending_timers:
                timer.cancel()
            self._pending_timers.clear()

        super().stop()

    def _schedule_timer(self, delay: float, fn: Any) -> None:
        """Schedule a timer and track it for cleanup."""
        with self._timer_lock:
            if not self._running:
                return
            timer = threading.Timer(delay, fn)
            self._pending_timers.append(timer)
            timer.start()

    def on_data(self, payload: Dict[str, Any]) -> None:
        """Handle fire-and-forget data events.

        Pattern: on_{event}
        """
        self.received_events.append({"event": "on_data", "payload": payload})

    def ack_request(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Handle request with acknowledgment.

        Pattern: ack_{event}
        """
        self.request_count += 1
        request_id = payload.get("request_id", "unknown")

        return {
            "status": "acknowledged",
            "request_id": request_id,
            "module_id": self.module_id,
            "count": self.request_count,
        }

    def whisper_athena_message(
        self,
        payload: Dict[str, Any],
        sender: Optional[str] = None,
    ) -> None:
        """Handle direct P2P whisper message.

        Pattern: whisper_{target}_{event}
        """
        self.received_events.append(
            {"event": "whisper_athena_message", "payload": payload, "sender": sender}
        )

    def on_common_broadcast(self, payload: Dict[str, Any]) -> None:
        """Handle broadcast events to ALL subscribers.

        Pattern: on_common_{event}
        """
        self.received_events.append(
            {"event": "on_common_broadcast", "payload": payload}
        )

    def on_common_ping(self, payload: Dict[str, Any]) -> None:
        """Handle ping broadcast - respond with pong after random delay.

        Pattern: on_common_{event}
        Echoes back the same value from the ping payload in the pong reply.
        Skips responding if the ping came from this module itself.
        """
        sender = payload.get("sender")
        if sender == self.module_id:
            return

        self.ping_count += 1
        value = payload.get("value")
        delay = random.uniform(0.1, 0.9)
        self._schedule_timer(delay, lambda: self._broadcast_pong(value))

    # def on_common_pong(self, payload: Dict[str, Any]) -> None:
    #     """Handle pong broadcast - respond with ping after random delay.

    #     Pattern: on_common_{event}
    #     """
    #     self.pong_count += 1
    #     delay = random.uniform(0.1, 0.9)
    #     self._schedule_timer(delay, self._broadcast_ping)

    def _broadcast_ping(self) -> None:
        """Broadcast a ping message to all modules with a random value.

        Generates a random integer between 0 and 100, includes it in the payload,
        and schedules the next ping with a random delay of 0-3 seconds.
        """
        if self._running:
            value = random.randint(0, 100)
            self.send_event("on_common_ping", {"sender": self.module_id, "value": value})
            delay = random.uniform(0, 3)
            self._schedule_timer(delay, self._broadcast_ping)

    def _broadcast_pong(self, value: Optional[int] = None) -> None:
        """Broadcast a pong message to all modules.

        Args:
            value: The value to echo back from the original ping (if provided).
        """
        if self._running:
            payload: Dict[str, Any] = {"sender": self.module_id}
            if value is not None:
                payload["value"] = value
            self.send_event("on_common_pong", payload)

    def start_ping_pong(self) -> None:
        """Start the ping-pong cycle by broadcasting initial ping."""
        self._broadcast_ping()

    def get_stats(self) -> Dict[str, Any]:
        """Return module statistics."""
        return {
            "module_id": self.module_id,
            "registered": self._registered,
            "request_count": self.request_count,
            "events_received": len(self.received_events),
            "ping_count": self.ping_count,
            "pong_count": self.pong_count,
            "interfaces": [i.name for i in self._interfaces],
        }
