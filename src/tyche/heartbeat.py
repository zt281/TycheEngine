"""Paranoid Pirate Pattern heartbeat implementation.

Implements reliable worker heartbeating as described in the ZeroMQ Guide.
Workers send periodic heartbeats; broker tracks liveness.
"""

import threading
import time

import zmq

from tyche.message import Message, serialize
from tyche.types import HEARTBEAT_INTERVAL, HEARTBEAT_LIVENESS, MessageType


class HeartbeatMonitor:
    """Monitors heartbeat liveness for a connected peer.

    Per Paranoid Pirate pattern, peer is considered dead after
    HEARTBEAT_LIVENESS missed heartbeats.
    """

    def __init__(
        self,
        interval: float = HEARTBEAT_INTERVAL,
        liveness: int = HEARTBEAT_LIVENESS,
        initial_grace_period: bool = True
    ):
        self.interval = interval
        # Give extra liveness for initial registration grace period
        self.liveness = liveness * 2 if initial_grace_period else liveness
        self.last_seen = time.time()

    def update(self) -> None:
        """Update last seen time and reset liveness."""
        self.liveness = HEARTBEAT_LIVENESS
        self.last_seen = time.time()

    def tick(self) -> None:
        """Decrement liveness counter (called on expected heartbeat interval)."""
        self.liveness -= 1

    def is_expired(self) -> bool:
        """Check if peer has exceeded liveness threshold."""
        return self.liveness <= 0

    def time_since_last(self) -> float:
        """Return seconds since last heartbeat."""
        return time.time() - self.last_seen


class HeartbeatSender:
    """Sends periodic heartbeats to broker.

    Workers send heartbeats at HEARTBEAT_INTERVAL seconds.
    """

    def __init__(
        self,
        socket: zmq.Socket,
        module_id: str,
        interval: float = HEARTBEAT_INTERVAL
    ):
        self.socket = socket
        self.module_id = module_id
        self.interval = interval
        self.next_heartbeat = time.time() + interval

    def should_send(self) -> bool:
        """Check if it's time to send a heartbeat."""
        return time.time() >= self.next_heartbeat

    def send(self) -> None:
        """Send heartbeat message."""
        msg = Message(
            msg_type=MessageType.HEARTBEAT,
            sender=self.module_id,
            event="heartbeat",
            payload={"status": "alive"}
        )

        frames = [
            self.module_id.encode(),
            serialize(msg)
        ]

        self.socket.send_multipart(frames)
        self.next_heartbeat = time.time() + self.interval


class HeartbeatManager:
    """Manages heartbeats for multiple peers.

    Used by broker to track all connected modules.
    """

    def __init__(
        self,
        interval: float = HEARTBEAT_INTERVAL,
        liveness: int = HEARTBEAT_LIVENESS
    ):
        self.interval = interval
        self.liveness = liveness
        self.monitors: dict[str, HeartbeatMonitor] = {}
        self._lock = threading.Lock()

    def register(self, peer_id: str) -> None:
        """Register a new peer for monitoring."""
        with self._lock:
            self.monitors[peer_id] = HeartbeatMonitor(self.interval, self.liveness)

    def unregister(self, peer_id: str) -> None:
        """Remove peer from monitoring."""
        with self._lock:
            self.monitors.pop(peer_id, None)

    def update(self, peer_id: str) -> None:
        """Record heartbeat from peer."""
        with self._lock:
            if peer_id in self.monitors:
                self.monitors[peer_id].update()
            else:
                self.monitors[peer_id] = HeartbeatMonitor(self.interval, self.liveness)

    def tick_all(self) -> list[str]:
        """Decrement all monitors, return expired peer IDs."""
        with self._lock:
            expired = []
            for peer_id, monitor in list(self.monitors.items()):
                monitor.tick()
                if monitor.is_expired():
                    expired.append(peer_id)
            return expired

    def get_expired(self) -> list[str]:
        """Get list of expired peer IDs without ticking."""
        with self._lock:
            return [
                peer_id for peer_id, monitor in self.monitors.items()
                if monitor.is_expired()
            ]

    def get_liveness(self, peer_id: str) -> int:
        """Get current liveness value for a peer.

        Returns:
            Current liveness counter value, or -1 if peer not found.
        """
        with self._lock:
            if peer_id in self.monitors:
                return self.monitors[peer_id].liveness
            return -1
