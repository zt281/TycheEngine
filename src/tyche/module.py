"""TycheModule - Base implementation for Tyche Engine modules.

Modules connect to TycheEngine and handle events using interface patterns.
"""

import inspect
import logging
import threading
from typing import Any, Callable, Dict, List, Optional

import zmq

from tyche.message import Message, deserialize, serialize
from tyche.module_base import ModuleBase
from tyche.types import (
    HEARTBEAT_INTERVAL,
    DurabilityLevel,
    Endpoint,
    Interface,
    InterfacePattern,
    MessageType,
    ModuleId,
)

logger = logging.getLogger(__name__)


class TycheModule(ModuleBase):
    """Base class for Tyche Engine modules.

    Connects to TycheEngine, registers interfaces, subscribes to events,
    and dispatches incoming messages to handler methods.

    Socket architecture:
    - REQ: one-shot registration handshake (closed after use)
    - PUB: publish events to engine's XSUB
    - SUB: subscribe to events from engine's XPUB
    - DEALER: send heartbeats to engine
    """

    def __init__(
        self,
        engine_endpoint: Endpoint,
        module_id: Optional[str] = None,
        heartbeat_receive_endpoint: Optional[Endpoint] = None,
    ):
        self._module_id = module_id or ModuleId.generate()
        self.engine_endpoint = engine_endpoint
        self.heartbeat_receive_endpoint = heartbeat_receive_endpoint

        # Event handlers: event_name -> (handler_function, pattern)
        self._handlers: Dict[str, tuple[Callable[..., Any], InterfacePattern]] = {}
        self._handlers_lock = threading.RLock()

        # ZMQ socket locks (sockets are not thread-safe)
        self._pub_lock = threading.Lock()

        # Discovered interfaces
        self._interfaces: List[Interface] = []

        # Ports returned by engine during registration
        self._engine_pub_port: Optional[int] = None
        self._engine_sub_port: Optional[int] = None

        # ZMQ context and sockets
        self.context: Optional[zmq.Context] = None
        self._pub_socket: Optional[zmq.Socket] = None
        self._sub_socket: Optional[zmq.Socket] = None
        self._heartbeat_socket: Optional[zmq.Socket] = None

        # Threading
        self._threads: List[threading.Thread] = []
        self._running = False
        self._stop_event = threading.Event()
        self._registered = False

        # Auto-discover interfaces from method names
        self._discover_and_register_handlers()

    @property
    def module_id(self) -> str:
        """Return module identifier."""
        return self._module_id

    @property
    def interfaces(self) -> List[Interface]:
        """Return discovered interfaces."""
        return self._interfaces

    # ── Interface Discovery ───────────────────────────────────────

    @staticmethod
    def _pattern_for_name(name: str) -> Optional[InterfacePattern]:
        """Determine interface pattern from method name (v3).

        Only two prefixes are recognized:
        - on_*   -> consumer interface
        - send_* -> producer declaration
        """
        if name.startswith("on_"):
            return InterfacePattern.ON
        if name.startswith("send_"):
            return InterfacePattern.SEND
        return None

    @staticmethod
    def _event_breakdown(name: str) -> Optional[tuple[str, str]]:
        handler_name_segmented = name.split('_')
        if len(handler_name_segmented) >= 3:
            return '_'.join(handler_name_segmented[1:]), '_'.join(handler_name_segmented[2:])
        return None

    def _discover_and_register_handlers(self) -> None:
        """Auto-discover interfaces from method names and register handlers."""
        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            pattern = self._pattern_for_name(name)
            if pattern is None:
                continue
            # Skip methods defined on TycheModule itself (e.g. send_event)
            if getattr(method, "__qualname__", "").startswith("TycheModule."):
                continue
            # Skip abstract methods — subclasses implement these as callbacks,
            # not as event handlers (e.g. StrategyModule.on_quote)
            if getattr(method, "__isabstractmethod__", False):
                continue
            if pattern == InterfacePattern.SEND:
                self._register_producer(name, pattern)
            else:
                self._register_handler(name, method, pattern)

    def _register_handler(
        self,
        handler_name: str,
        event_name: str,
        handler: Callable[..., Any],
        pattern: InterfacePattern = InterfacePattern.ON,
        durability: DurabilityLevel = DurabilityLevel.ASYNC_FLUSH,
    ) -> None:
        """Register an event handler interface (for internal/subclass use).

        Args:
            name: Interface name (e.g., "on_data")
            handler: Function to handle events
            pattern: Interface pattern type
            durability: Message durability level
        """
        with self._handlers_lock:
            self._handlers[name] = handler
            # v3 unified queue: also register under bare topic name so
            # producers can send_event("data", ...) and it routes to on_data.
            if name.startswith("on_"):
                bare_name = name[3:]
                self._handlers[bare_name] = handler
            self._interfaces.append(
                Interface(
                    name=handler_name,
                    pattern=pattern,
                    event_type=event_name,
                    durability=durability,
                )
            )
        if self._sub_socket is not None:
            self._sub_socket.setsockopt(zmq.SUBSCRIBE, handler_name.encode())

    def _register_producer(
        self,
        name: str,
        pattern: InterfacePattern = InterfacePattern.SEND,
        durability: DurabilityLevel = DurabilityLevel.ASYNC_FLUSH,
    ) -> None:
        """Register a producer declaration (send_* method).

        Producer declarations are recorded in _interfaces but do not
        create an inbound handler.
        """
        with self._handlers_lock:
            self._interfaces.append(
                Interface(
                    name=name,
                    pattern=pattern,
                    event_type=name,
                    durability=durability,
                )
            )

    def start(self) -> None:
        """Start the module - returns once worker threads are up."""
        self._start_workers()

    def run(self) -> None:
        """Start the module - blocks until stop() is called."""
        self.start()
        self._stop_event.wait()

    def _start_workers(self) -> None:
        """Start worker threads and connect to engine."""
        self.context = zmq.Context()
        self._running = True
        self._stop_event.clear()

        # Register with engine (blocking, one-shot REQ/REP)
        if not self._register():
            logger.error("[%s] Failed to register with engine", self._module_id)
            return

        # Set up event PUB socket (module -> engine XSUB)
        host = self.engine_endpoint.host
        if self._engine_sub_port is not None:
            self._pub_socket = self.context.socket(zmq.PUB)
            self._pub_socket.setsockopt(zmq.LINGER, 0)
            self._pub_socket.setsockopt(zmq.SNDHWM, 10000)
            self._pub_socket.connect(f"tcp://{host}:{self._engine_sub_port}")

        # Set up event SUB socket (engine XPUB -> module)
        if self._engine_pub_port is not None:
            self._sub_socket = self.context.socket(zmq.SUB)
            self._sub_socket.setsockopt(zmq.LINGER, 0)
            self._sub_socket.setsockopt(zmq.RCVHWM, 10000)
            self._sub_socket.connect(f"tcp://{host}:{self._engine_pub_port}")
            # Subscribe to events matching our handlers
            self._subscribe_to_interfaces()

        # Set up heartbeat DEALER socket
        if self.heartbeat_receive_endpoint:
            self._heartbeat_socket = self.context.socket(zmq.DEALER)
            self._heartbeat_socket.setsockopt(zmq.LINGER, 0)
            self._heartbeat_socket.connect(str(self.heartbeat_receive_endpoint))

        # Start background threads
        self._threads = []

        if self._sub_socket is not None:
            self._threads.append(
                threading.Thread(
                    target=self._event_receiver, name="event_recv", daemon=True
                )
            )

        if self._heartbeat_socket is not None:
            self._threads.append(
                threading.Thread(
                    target=self._send_heartbeats, name="heartbeat_send", daemon=True
                )
            )

        for t in self._threads:
            t.start()

    def stop(self) -> None:
        """Stop the module gracefully."""
        self._running = False
        self._stop_event.set()

        for t in self._threads:
            t.join(timeout=2.0)

        for sock in [self._pub_socket, self._sub_socket, self._heartbeat_socket]:
            if sock is not None:
                sock.close()
        self._pub_socket = None
        self._sub_socket = None
        self._heartbeat_socket = None

        if self.context:
            self.context.destroy(linger=0)
            self.context = None

    # ── Registration ──────────────────────────────────────────────

    def _register(self) -> bool:
        """Register with TycheEngine via a one-shot REQ socket.

        Returns:
            True if registration successful
        """
        assert self.context is not None

        sock = self.context.socket(zmq.REQ)
        sock.setsockopt(zmq.LINGER, 0)
        sock.setsockopt(zmq.RCVTIMEO, 5000)
        sock.connect(str(self.engine_endpoint))

        try:
            interfaces_data = [
                {
                    "name": iface.name,
                    "pattern": iface.pattern.value,
                    "event_type": iface.event_type,
                    "durability": iface.durability.value,
                }
                for iface in self._interfaces
            ]

            msg = Message(
                msg_type=MessageType.REGISTER,
                sender=self._module_id,
                event="register",
                payload={
                    "module_id": self._module_id,
                    "interfaces": interfaces_data,
                    "metadata": {},
                },
            )

            sock.send(serialize(msg))

            reply_data = sock.recv()
            reply = deserialize(reply_data)

            if reply.msg_type == MessageType.ACK:
                self._registered = True
                self._engine_pub_port = reply.payload.get("event_pub_port")
                self._engine_sub_port = reply.payload.get("event_sub_port")
                logger.info("[%s] Registered with engine", self._module_id)
                return True

        except zmq.error.Again:
            logger.warning("[%s] Registration timeout", self._module_id)
        except Exception as e:
            logger.error("[%s] Registration failed: %s", self._module_id, e)
        finally:
            sock.close()

        return False

    # ── Event Subscription & Dispatch ─────────────────────────────

    def _subscribe_to_interfaces(self) -> None:
        """Subscribe the SUB socket to topics matching our handler names."""
        assert self._sub_socket is not None

        with self._handlers_lock:
            for name in self._handlers:
                self._sub_socket.setsockopt(zmq.SUBSCRIBE, name.encode())

    def _event_receiver(self) -> None:
        """Receive events from the engine's XPUB and dispatch to handlers."""
        assert self._sub_socket is not None
        self._sub_socket.setsockopt(zmq.RCVTIMEO, 100)

        while self._running:
            try:
                frames = self._sub_socket.recv_multipart()
                if len(frames) >= 2:
                    topic = frames[0].decode()
                    try:
                        msg = deserialize(frames[1])
                    except Exception as e:
                        logger.error(
                            "[%s] Deserialization failed on topic=%s frames=%s all_frames=%r: %s",
                            self._module_id,
                            topic,
                            len(frames),
                            [f[:100] for f in frames],
                            e,
                        )
                        continue
                    # Ignore messages sent by ourselves
                    if msg.sender == self._module_id:
                        continue
                    self._dispatch(topic, msg)
            except zmq.error.Again:
                continue
            except Exception as e:
                if self._running:
                    logger.error("[%s] Event receive error: %s", self._module_id, e)

    def _dispatch(self, topic: str, msg: Message) -> None:
        """Route an incoming message to the correct handler.

        All handlers are fire-and-forget; return value is always None.
        """
        with self._handlers_lock:
            entry = self._handlers.get(topic)
        if entry is None:
            return None
        handler, pattern = entry

        try:
            handler(msg.payload)
        except Exception as e:
            logger.error(
                "[%s] Handler %s raised: %s", self._module_id, topic, e
            )
        return None

    # ── Event Publishing ──────────────────────────────────────────

    def send_event(
        self,
        event: str,
        payload: Dict[str, Any],
        recipient: Optional[str] = None,
    ) -> None:
        """Publish an event through the engine's event proxy.

        Args:
            event: Event/topic name
            payload: Event data
            recipient: Optional specific recipient module (included in payload)
        """
        if self._pub_socket is None:
            logger.warning(
                "[%s] Cannot send event: not connected to event proxy",
                self._module_id,
            )
            return

        msg = Message(
            msg_type=MessageType.EVENT,
            sender=self._module_id,
            recipient=recipient,
            event=event,
            payload=payload,
        )

        with self._pub_lock:
            self._pub_socket.send_multipart([event.encode(), serialize(msg)])

    # ── Heartbeat ─────────────────────────────────────────────────

    def _send_heartbeats(self) -> None:
        """Send periodic heartbeats to engine."""
        if self._heartbeat_socket is None:
            return

        while self._running:
            try:
                msg = Message(
                    msg_type=MessageType.HEARTBEAT,
                    sender=self._module_id,
                    event="heartbeat",
                    payload={"status": "alive"},
                )
                self._heartbeat_socket.send(serialize(msg))
            except Exception as e:
                if self._running:
                    logger.error(
                        "[%s] Heartbeat send error: %s", self._module_id, e
                    )

            self._stop_event.wait(HEARTBEAT_INTERVAL)
