"""TycheEngine - Central broker using threads for multi-process support."""

import threading
import time
from typing import Any, Dict, List, Optional

import zmq

from tyche.heartbeat import HeartbeatManager
from tyche.message import Message, deserialize, serialize
from tyche.types import (
    HEARTBEAT_INTERVAL,
    DurabilityLevel,
    Endpoint,
    Interface,
    InterfacePattern,
    MessageType,
    ModuleInfo,
)


class TycheEngine:
    """Central broker for Tyche Engine - runs in standalone process."""

    def __init__(
        self,
        registration_endpoint: Endpoint,
        event_endpoint: Endpoint,
        heartbeat_endpoint: Endpoint,
        ack_endpoint: Optional[Endpoint] = None,
        heartbeat_receive_endpoint: Optional[Endpoint] = None
    ):
        self.registration_endpoint = registration_endpoint
        self.event_endpoint = event_endpoint
        self.heartbeat_endpoint = heartbeat_endpoint
        self.ack_endpoint = ack_endpoint or Endpoint(
            event_endpoint.host, event_endpoint.port + 10
        )
        self.heartbeat_receive_endpoint = heartbeat_receive_endpoint or Endpoint(
            heartbeat_endpoint.host, heartbeat_endpoint.port + 1
        )

        self.modules: Dict[str, ModuleInfo] = {}
        self.interfaces: Dict[str, List[tuple]] = {}
        self.heartbeat_manager = HeartbeatManager()

        self.context: Optional[zmq.Context] = None
        self._running = False
        self._threads: List[threading.Thread] = []
        self._stop_event = threading.Event()

    def run(self) -> None:
        """Start the engine - blocks until stop() is called."""
        self._start_workers()

        # Block main thread - use wait() instead of sleep() for signal compatibility
        while not self._stop_event.is_set():
            self._stop_event.wait(0.1)

    def start_nonblocking(self) -> None:
        """Start the engine without blocking (for testing)."""
        self._start_workers()

    def _start_workers(self) -> None:
        """Start worker threads."""
        self.context = zmq.Context()
        self._running = True
        self._stop_event.clear()

        # Start worker threads
        self._threads = [
            threading.Thread(target=self._registration_worker, name="registration"),
            threading.Thread(target=self._heartbeat_worker, name="heartbeat"),
            threading.Thread(target=self._heartbeat_receive_worker, name="hb_recv"),
            threading.Thread(target=self._monitor_worker, name="monitor"),
        ]

        for t in self._threads:
            t.start()

    def stop(self) -> None:
        """Stop the engine."""
        self._running = False
        self._stop_event.set()

        for t in self._threads:
            t.join(timeout=2.0)

        if self.context:
            self.context.term()
            self.context = None

    def _registration_worker(self) -> None:
        """Handle module registrations in dedicated thread."""
        assert self.context is not None
        socket = self.context.socket(zmq.ROUTER)
        socket.setsockopt(zmq.LINGER, 0)  # Don't wait on close
        socket.bind(str(self.registration_endpoint))
        socket.setsockopt(zmq.RCVTIMEO, 100)  # 100ms timeout for polling

        while self._running:
            try:
                frames = socket.recv_multipart()
                self._process_registration(socket, frames)
            except zmq.error.Again:
                continue  # Timeout, check _running
            except Exception as e:
                if self._running:
                    print(f"Registration error: {e}")

        socket.close()

    def _process_registration(self, socket: zmq.Socket, frames: List[bytes]) -> None:
        """Process registration request."""
        if len(frames) < 3:
            return

        identity = frames[0]
        msg_data = frames[2] if frames[1] == b"" else frames[1]

        try:
            msg = deserialize(msg_data)

            if msg.msg_type == MessageType.REGISTER:
                # Register module
                module_info = self._create_module_info(msg)
                self.register_module(module_info)

                # Send ACK (ROUTER socket format: [identity, empty, message])
                ack = Message(
                    msg_type=MessageType.ACK,
                    sender="engine",
                    event="register_ack",
                    payload={"status": "ok", "module_id": module_info.module_id}
                )
                socket.send_multipart([identity, b"", serialize(ack)])
                print(f"Registered module: {module_info.module_id}")

        except Exception as e:
            print(f"Failed to process registration: {e}")

    def _create_module_info(self, msg: Message) -> ModuleInfo:
        """Create ModuleInfo from registration message."""

        module_id = msg.payload.get("module_id", "")
        if not module_id:
            module_id = "unknown_module"
        interfaces_data = msg.payload.get("interfaces", [])

        interfaces = [
            Interface(
                name=i["name"],
                pattern=InterfacePattern(i["pattern"]),
                event_type=i.get("event_type", i["name"]),
                durability=DurabilityLevel(i.get("durability", 1))
            )
            for i in interfaces_data
        ]

        return ModuleInfo(
            module_id=module_id,
            endpoint=Endpoint("127.0.0.1", 0),  # Will be updated with actual
            interfaces=interfaces,
            metadata=msg.payload.get("metadata", {})
        )

    def register_module(self, module_info: ModuleInfo) -> None:
        """Register a module and its interfaces."""
        self.modules[module_info.module_id] = module_info

        for interface in module_info.interfaces:
            event_name = interface.name
            if event_name not in self.interfaces:
                self.interfaces[event_name] = []
            self.interfaces[event_name].append(
                (module_info.module_id, interface)
            )

        self.heartbeat_manager.register(module_info.module_id)

    def unregister_module(self, module_id: str) -> None:
        """Unregister a module."""
        if module_id not in self.modules:
            return

        module_info = self.modules[module_id]

        for interface in module_info.interfaces:
            event_name = interface.name
            if event_name in self.interfaces:
                self.interfaces[event_name] = [
                    (mid, iface) for mid, iface in self.interfaces[event_name]
                    if mid != module_id
                ]

        del self.modules[module_id]
        self.heartbeat_manager.unregister(module_id)

    def _heartbeat_worker(self) -> None:
        """Send heartbeat broadcasts."""
        assert self.context is not None
        socket = self.context.socket(zmq.PUB)
        socket.setsockopt(zmq.LINGER, 0)  # Don't wait on close
        socket.bind(str(self.heartbeat_endpoint))

        while self._running:
            try:
                # Send heartbeat to all modules
                msg = Message(
                    msg_type=MessageType.HEARTBEAT,
                    sender="engine",
                    event="heartbeat",
                    payload={"timestamp": time.time()}
                )
                socket.send_multipart([b"heartbeat", serialize(msg)])
                time.sleep(HEARTBEAT_INTERVAL)
            except Exception as e:
                if self._running:
                    print(f"Heartbeat error: {e}")

        socket.close()

    def _monitor_worker(self) -> None:
        """Monitor peer health."""
        while self._running:
            expired = self.heartbeat_manager.tick_all()
            for module_id in expired:
                print(f"Module {module_id} expired")
                self.unregister_module(module_id)

            time.sleep(HEARTBEAT_INTERVAL)

    def _heartbeat_receive_worker(self) -> None:
        """Receive heartbeats from modules and update liveness."""
        assert self.context is not None
        socket = self.context.socket(zmq.ROUTER)
        socket.setsockopt(zmq.LINGER, 0)
        socket.bind(str(self.heartbeat_receive_endpoint))
        socket.setsockopt(zmq.RCVTIMEO, 100)  # 100ms timeout for polling

        while self._running:
            try:
                frames = socket.recv_multipart()
                if len(frames) >= 2:
                    _identity = frames[0]  # noqa: F841
                    msg_data = frames[2] if len(frames) > 2 and frames[1] == b"" else frames[1]

                    try:
                        msg = deserialize(msg_data)
                        if msg.msg_type == MessageType.HEARTBEAT:
                            module_id = msg.sender
                            self.heartbeat_manager.update(module_id)
                    except Exception:
                        pass  # Ignore malformed messages
            except zmq.error.Again:
                continue  # Timeout, check _running
            except Exception as e:
                if self._running:
                    print(f"Heartbeat receive error: {e}")

        socket.close()

    async def broadcast_event(self, event: str, payload: Dict[str, Any]) -> None:
        """Broadcast event to all subscribers (async version for compatibility)."""
        # TODO: Implement actual event broadcasting with XPUB socket
        # For now, this is a placeholder that does nothing
        pass
