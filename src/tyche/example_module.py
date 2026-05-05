"""Example Module demonstrating Tyche v3 unified queue interface model.

This module serves as a reference implementation showing:
- on_{event}: Fire-and-forget event handler
- send_{event}: Producer declaration (optional, for pre-warming queues)
- Event chaining: on_ping receives, schedules pong response
"""

import random
import threading
from typing import Any, Dict, List, Optional

from tyche.module import TycheModule
from tyche.types import Endpoint, ModuleId


class ExampleModule(TycheModule):
    """Example module with v3 unified queue patterns.

    Demonstrates:
    - on_data: Generic event handler
    - on_message: Generic event handler
    - on_broadcast: Generic event handler
    - on_ping/on_pong: Event chaining pattern

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

    # ── Event handlers (on_*) ────────────────────────────────────

    def on_data(self, payload: Dict[str, Any]) -> None:
        """Handle generic data events."""
        self.received_events.append({"event": "on_data", "payload": payload})

    def on_message(self, payload: Dict[str, Any]) -> None:
        """Handle generic message events."""
        self.received_events.append(
            {"event": "on_message", "payload": payload}
        )

    def on_broadcast(self, payload: Dict[str, Any]) -> None:
        """Handle broadcast events to ALL subscribers."""
        self.received_events.append(
            {"event": "on_broadcast", "payload": payload}
        )

    def on_ping(self, payload: Dict[str, Any]) -> None:
        """Handle ping event — respond with pong after random delay.

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

    def on_pong(self, payload: Dict[str, Any]) -> None:
        """Handle pong event."""
        sender = payload.get("sender")
        if sender == self.module_id:
            return
        self.pong_count += 1

    # ── Producer declarations (send_*) ───────────────────────────

    def send_ping(self, payload: Dict[str, Any]) -> None:
        """Declare intent to publish ping events (optional documentation)."""
        self.send_event("ping", payload)

    def send_pong(self, payload: Dict[str, Any]) -> None:
        """Declare intent to publish pong events (optional documentation)."""
        self.send_event("pong", payload)

    # ── Internal helpers ─────────────────────────────────────────

    def _broadcast_ping(self) -> None:
        """Broadcast a ping message to all modules with a random value."""
        if self._running:
            value = random.randint(0, 100)
            self.send_event("ping", {"sender": self.module_id, "value": value})
            delay = random.uniform(0, 3)
            self._schedule_timer(delay, self._broadcast_ping)

    def _broadcast_pong(self, value: Optional[int] = None) -> None:
        """Broadcast a pong message to all modules."""
        if self._running:
            payload: Dict[str, Any] = {"sender": self.module_id}
            if value is not None:
                payload["value"] = value
            self.send_event("pong", payload)

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
