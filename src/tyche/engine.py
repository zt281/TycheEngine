"""TycheEngine - Central broker using threads for multi-process support."""

import logging
import threading
import time
from typing import Dict, List, Optional, Tuple

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

logger = logging.getLogger(__name__)


class TycheEngine:
    """Central broker for Tyche Engine - runs in standalone process.

    Provides:
    - Module registration via ROUTER socket
    - Event routing via XPUB/XSUB proxy
    - Heartbeat monitoring (Paranoid Pirate pattern)
    """

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
        # XSUB endpoint for modules to publish events to the engine
        self.event_sub_endpoint = Endpoint(
            event_endpoint.host, event_endpoint.port + 1
        )

        # Thread-safe registry
        self._lock = threading.Lock()
        self.modules: Dict[str, ModuleInfo] = {}
        self.interfaces: Dict[str, List[Tuple[str, Interface]]] = {}
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

        self._threads = [
            threading.Thread(
                target=self._registration_worker, name="registration", daemon=True
            ),
            threading.Thread(
                target=self._heartbeat_worker, name="heartbeat", daemon=True
            ),
            threading.Thread(
                target=self._heartbeat_receive_worker, name="hb_recv", daemon=True
            ),
            threading.Thread(
                target=self._monitor_worker, name="monitor", daemon=True
            ),
            threading.Thread(
                target=self._event_proxy_worker, name="event_proxy", daemon=True
            ),
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
            # destroy(linger=0) forcibly closes any lingering sockets
            self.context.destroy(linger=0)
            self.context = None

    # ── Registration ──────────────────────────────────────────────

    def _registration_worker(self) -> None:
        """Handle module registrations in dedicated thread."""
        assert self.context is not None
        socket = self.context.socket(zmq.ROUTER)
        socket.setsockopt(zmq.LINGER, 0)
        try:
            socket.bind(str(self.registration_endpoint))
            socket.setsockopt(zmq.RCVTIMEO, 100)

            while self._running:
                try:
                    frames = socket.recv_multipart()
                    self._process_registration(socket, frames)
                except zmq.error.Again:
                    continue
                except Exception as e:
                    if self._running:
                        logger.error("Registration error: %s", e)
        except Exception as e:
            logger.error("Registration worker failed to start: %s", e)
        finally:
            socket.close()

    def _process_registration(
        self, socket: zmq.Socket, frames: List[bytes]
    ) -> None:
        """Process a registration request from a module."""
        if len(frames) < 2:
            return

        identity = frames[0]
        # ROUTER adds identity frame; REQ adds empty delimiter
        msg_data = frames[2] if len(frames) >= 3 and frames[1] == b"" else frames[1]

        try:
            msg = deserialize(msg_data)

            if msg.msg_type == MessageType.REGISTER:
                module_info = self._create_module_info(msg)
                self.register_module(module_info)

                ack = Message(
                    msg_type=MessageType.ACK,
                    sender="engine",
                    event="register_ack",
                    payload={
                        "status": "ok",
                        "module_id": module_info.module_id,
                        "event_pub_port": self.event_endpoint.port,
                        "event_sub_port": self.event_sub_endpoint.port,
                    },
                )
                socket.send_multipart([identity, b"", serialize(ack)])
                logger.info("Registered module: %s", module_info.module_id)
        except Exception as e:
            logger.error("Failed to process registration: %s", e)

    def _create_module_info(self, msg: Message) -> ModuleInfo:
        """Create ModuleInfo from registration message."""
        module_id = msg.payload.get("module_id", "") or "unknown_module"
        interfaces_data = msg.payload.get("interfaces", [])

        interfaces = [
            Interface(
                name=i["name"],
                pattern=InterfacePattern(i["pattern"]),
                event_type=i.get("event_type", i["name"]),
                durability=DurabilityLevel(i.get("durability", 1)),
            )
            for i in interfaces_data
        ]

        return ModuleInfo(
            module_id=module_id,
            endpoint=Endpoint("127.0.0.1", 0),
            interfaces=interfaces,
            metadata=msg.payload.get("metadata", {}),
        )

    def register_module(self, module_info: ModuleInfo) -> None:
        """Register a module and its interfaces (thread-safe)."""
        with self._lock:
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
        """Unregister a module (thread-safe)."""
        with self._lock:
            if module_id not in self.modules:
                return

            module_info = self.modules[module_id]

            for interface in module_info.interfaces:
                event_name = interface.name
                if event_name in self.interfaces:
                    self.interfaces[event_name] = [
                        (mid, iface)
                        for mid, iface in self.interfaces[event_name]
                        if mid != module_id
                    ]

            del self.modules[module_id]

        self.heartbeat_manager.unregister(module_id)

    # ── Event Proxy (XPUB/XSUB) ──────────────────────────────────

    def _event_proxy_worker(self) -> None:
        """XSUB/XPUB proxy for event distribution.

        Modules publish events to the XSUB socket.
        Modules subscribe to events via the XPUB socket.
        The proxy forwards between them.
        """
        assert self.context is not None

        xpub = self.context.socket(zmq.XPUB)
        xpub.setsockopt(zmq.LINGER, 0)
        xsub = self.context.socket(zmq.XSUB)
        xsub.setsockopt(zmq.LINGER, 0)

        try:
            xpub.bind(str(self.event_endpoint))
            xsub.bind(str(self.event_sub_endpoint))

            poller = zmq.Poller()
            poller.register(xpub, zmq.POLLIN)
            poller.register(xsub, zmq.POLLIN)

            while self._running:
                try:
                    events = dict(poller.poll(100))
                except zmq.error.ZMQError:
                    break

                if xpub in events:
                    frame = xpub.recv_multipart()
                    xsub.send_multipart(frame)

                if xsub in events:
                    frame = xsub.recv_multipart()
                    xpub.send_multipart(frame)
        except Exception as e:
            logger.error("Event proxy worker failed: %s", e)
        finally:
            xpub.close()
            xsub.close()

    # ── Heartbeat ─────────────────────────────────────────────────

    def _heartbeat_worker(self) -> None:
        """Send heartbeat broadcasts via PUB socket."""
        assert self.context is not None
        socket = self.context.socket(zmq.PUB)
        socket.setsockopt(zmq.LINGER, 0)
        try:
            socket.bind(str(self.heartbeat_endpoint))

            while self._running:
                try:
                    msg = Message(
                        msg_type=MessageType.HEARTBEAT,
                        sender="engine",
                        event="heartbeat",
                        payload={"timestamp": time.time()},
                    )
                    socket.send_multipart([b"heartbeat", serialize(msg)])
                    time.sleep(HEARTBEAT_INTERVAL)
                except Exception as e:
                    if self._running:
                        logger.error("Heartbeat error: %s", e)
        except Exception as e:
            logger.error("Heartbeat worker failed to start: %s", e)
        finally:
            socket.close()

    def _heartbeat_receive_worker(self) -> None:
        """Receive heartbeats from modules and update liveness."""
        assert self.context is not None
        socket = self.context.socket(zmq.ROUTER)
        socket.setsockopt(zmq.LINGER, 0)
        try:
            socket.bind(str(self.heartbeat_receive_endpoint))
            socket.setsockopt(zmq.RCVTIMEO, 100)

            while self._running:
                try:
                    frames = socket.recv_multipart()
                    if len(frames) >= 2:
                        msg_data = (
                            frames[2]
                            if len(frames) > 2 and frames[1] == b""
                            else frames[1]
                        )
                        try:
                            msg = deserialize(msg_data)
                            if msg.msg_type == MessageType.HEARTBEAT:
                                self.heartbeat_manager.update(msg.sender)
                        except Exception:
                            pass  # Ignore malformed heartbeat messages
                except zmq.error.Again:
                    continue
                except Exception as e:
                    if self._running:
                        logger.error("Heartbeat receive error: %s", e)
        except Exception as e:
            logger.error("Heartbeat receive worker failed to start: %s", e)
        finally:
            socket.close()

    def _monitor_worker(self) -> None:
        """Monitor peer health and unregister expired modules."""
        while self._running:
            expired = self.heartbeat_manager.tick_all()
            for module_id in expired:
                logger.info("Module %s expired", module_id)
                self.unregister_module(module_id)

            time.sleep(HEARTBEAT_INTERVAL)
