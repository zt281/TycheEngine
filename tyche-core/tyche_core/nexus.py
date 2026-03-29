"""Nexus service - module registration and lifecycle management."""

import zmq
import threading
import logging
import json
import time
import random
from typing import Dict, Optional
from dataclasses import dataclass

from .protocol import READY, ACK, HB, CMD, REPLY, DISCO


@dataclass
class ModuleDescriptor:
    """Registration info for a connected module."""
    service_name: str
    service_version: str
    protocol_version: int
    subscriptions: list
    heartbeat_interval_ms: int
    capabilities: list
    metadata: dict
    correlation_id: int
    assigned_id: str
    last_heartbeat_ns: int = 0
    status: str = "registered"


class Nexus:
    """Nexus - ROUTER socket for module registration and control."""

    def __init__(
        self,
        endpoint: str,
        cpu_core: Optional[int] = None,
        heartbeat_interval_ms: int = 1000,
        heartbeat_timeout_ms: int = 3000,
    ):
        self.endpoint = endpoint
        self.cpu_core = cpu_core
        self.heartbeat_interval_ms = heartbeat_interval_ms
        self.heartbeat_timeout_ms = heartbeat_timeout_ms

        self._modules: Dict[str, ModuleDescriptor] = {}
        self._modules_by_correlation: Dict[int, str] = {}
        self._lock = threading.Lock()
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._ctx: Optional[zmq.Context] = None
        self._socket: Optional[zmq.Socket] = None
        self._logger = logging.getLogger("tyche.nexus")
        self._correlation_counter = 0

    def start(self) -> None:
        """Start the Nexus service."""
        self._running = True
        self._ctx = zmq.Context()
        self._socket = self._ctx.socket(zmq.ROUTER)
        self._socket.bind(self.endpoint)

        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._logger.info(f"Nexus started on {self.endpoint}")

    def stop(self) -> None:
        """Stop the Nexus service."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        if self._ctx:
            try:
                self._ctx.term()
            except zmq.ZMQError:
                pass
        self._logger.info("Nexus stopped")

    def _run(self) -> None:
        """Main run loop."""
        if self.cpu_core is not None:
            self._set_cpu_affinity(self.cpu_core)

        poller = zmq.Poller()
        poller.register(self._socket, zmq.POLLIN)

        last_check = time.time_ns()

        while self._running:
            events = dict(poller.poll(timeout=100))

            if self._socket in events:
                self._handle_message()

            # Check for heartbeat timeouts every 100ms
            now = time.time_ns()
            if now - last_check > 100_000_000:  # 100ms
                self._check_timeouts()
                last_check = now

        self._socket.close()
        try:
            self._ctx.term()
        except zmq.ZMQError:
            pass

    def _handle_message(self) -> None:
        """Handle incoming message."""
        frames = self._socket.recv_multipart()
        # ROUTER prepends identity
        identity = frames[0]
        msg_type = frames[1]

        if msg_type == READY:
            self._handle_ready(identity, frames[2:])
        elif msg_type == HB:
            self._handle_heartbeat(identity, frames[2:])
        elif msg_type == REPLY:
            self._handle_reply(identity, frames[2:])
        elif msg_type == DISCO:
            self._handle_disconnect(identity, frames[2:])
        else:
            self._logger.warning(f"Unknown message type: {msg_type}")

    def _handle_ready(self, identity: bytes, frames: list) -> None:
        """Handle module registration."""
        if len(frames) < 2:
            self._logger.error("Invalid READY message")
            return

        protocol_version = int.from_bytes(frames[0], "big")
        descriptor_json = frames[1].decode()

        try:
            descriptor_data = json.loads(descriptor_json)
        except json.JSONDecodeError as e:
            self._logger.error(f"Invalid descriptor JSON: {e}")
            return

        # Generate IDs
        self._correlation_counter += 1
        correlation_id = self._correlation_counter
        assigned_id = f"{descriptor_data['service_name']}.{correlation_id}"

        descriptor = ModuleDescriptor(
            service_name=descriptor_data["service_name"],
            service_version=descriptor_data.get("service_version", "1.0.0"),
            protocol_version=protocol_version,
            subscriptions=descriptor_data.get("subscriptions", []),
            heartbeat_interval_ms=descriptor_data.get(
                "heartbeat_interval_ms", self.heartbeat_interval_ms
            ),
            capabilities=descriptor_data.get("capabilities", []),
            metadata=descriptor_data.get("metadata", {}),
            correlation_id=correlation_id,
            assigned_id=assigned_id,
            last_heartbeat_ns=time.time_ns(),
        )

        with self._lock:
            self._modules[identity.hex()] = descriptor
            self._modules_by_correlation[correlation_id] = identity.hex()

        self._logger.info(f"Registered module: {assigned_id}")

        # Send ACK
        self._socket.send_multipart([
            identity,
            ACK,
            correlation_id.to_bytes(8, "big"),
            assigned_id.encode(),
            descriptor.heartbeat_interval_ms.to_bytes(4, "big"),
        ])

    def _handle_heartbeat(self, identity: bytes, frames: list) -> None:
        """Handle heartbeat."""
        if len(frames) < 2:
            return

        timestamp_ns = int.from_bytes(frames[0], "big")
        _correlation_id = int.from_bytes(frames[1], "big")

        with self._lock:
            key = identity.hex()
            if key in self._modules:
                self._modules[key].last_heartbeat_ns = timestamp_ns

    def _handle_reply(self, identity: bytes, frames: list) -> None:
        """Handle command reply."""
        if len(frames) < 2:
            return

        correlation_id = int.from_bytes(frames[0], "big")
        status = frames[1]
        message = frames[2].decode() if len(frames) > 2 else ""

        self._logger.debug(f"Reply from {correlation_id}: {status} - {message}")

    def _handle_disconnect(self, identity: bytes, frames: list) -> None:
        """Handle disconnect."""
        key = identity.hex()
        with self._lock:
            if key in self._modules:
                descriptor = self._modules.pop(key)
                self._modules_by_correlation.pop(descriptor.correlation_id, None)
                self._logger.info(f"Module disconnected: {descriptor.assigned_id}")

    def _check_timeouts(self) -> None:
        """Check for heartbeat timeouts."""
        now = time.time_ns()
        timeout_ns = self.heartbeat_timeout_ms * 1_000_000

        with self._lock:
            dead_modules = []
            for key, descriptor in self._modules.items():
                if now - descriptor.last_heartbeat_ns > timeout_ns:
                    dead_modules.append(key)
                    self._logger.warning(f"Heartbeat timeout: {descriptor.assigned_id}")

            for key in dead_modules:
                descriptor = self._modules.pop(key)
                self._modules_by_correlation.pop(descriptor.correlation_id, None)

    def send_command(self, assigned_id: str, command: bytes, payload: bytes = b"") -> bool:
        """Send command to a module."""
        with self._lock:
            for key, descriptor in self._modules.items():
                if descriptor.assigned_id == assigned_id:
                    identity = bytes.fromhex(key)
                    self._socket.send_multipart([
                        identity,
                        CMD,
                        command,
                        payload,
                    ])
                    return True
        return False

    def broadcast_command(self, command: bytes, payload: bytes = b"") -> None:
        """Send command to all modules."""
        with self._lock:
            for key in self._modules:
                identity = bytes.fromhex(key)
                self._socket.send_multipart([
                    identity,
                    CMD,
                    command,
                    payload,
                ])

    def get_modules(self) -> Dict[str, ModuleDescriptor]:
        """Get copy of module registry."""
        with self._lock:
            return dict(self._modules)

    def calculate_backoff(self, retry_count: int, base_ms: int = 100, max_ms: int = 5000) -> int:
        """Calculate exponential backoff with jitter.

        Args:
            retry_count: Current retry attempt (1-based)
            base_ms: Base delay in milliseconds
            max_ms: Maximum delay cap

        Returns:
            Delay in milliseconds
        """
        delay = base_ms * (2 ** (retry_count - 1))
        # Add ±20% jitter
        jitter = delay * 0.2 * (random.random() * 2 - 1)
        delay = delay + jitter
        return max(1, min(int(delay), max_ms))

    def _set_cpu_affinity(self, core: int) -> None:
        """Set CPU affinity."""
        import sys
        if sys.platform == "linux":
            import os
            os.sched_setaffinity(0, {core})
        elif sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.SetThreadAffinityMask(-1, 1 << core)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
