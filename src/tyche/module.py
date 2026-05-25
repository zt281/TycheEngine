"""TycheModule - Base implementation for Tyche Engine modules.

Modules connect to TycheEngine and handle events using interface patterns.
"""

import inspect
import logging
import threading
import time
import uuid
from typing import Any, Callable, Dict, List, Optional

import zmq

from src.tyche.message import Message, deserialize, serialize
from src.tyche.module_base import ModuleBase
from src.tyche.types import (
    HEARTBEAT_INTERVAL,
    DurabilityLevel,
    Endpoint,
    Interface,
    InterfacePattern,
    MessageType,
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
    - DEALER: job request/response (addressable via module_id)
    """

    def __init__(
        self,
        engine_endpoint: Endpoint,
        family_name: str = "unknown",
        heartbeat_receive_endpoint: Optional[Endpoint] = None,
    ):
        self._family_name = family_name
        self._module_id: Optional[str] = None
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
        self._engine_job_port: Optional[int] = None
        self._engine_heartbeat_recv_port: Optional[int] = None

        # ZMQ context and sockets
        self.context: Optional[zmq.Context] = None
        self._pub_socket: Optional[zmq.Socket] = None
        self._sub_socket: Optional[zmq.Socket] = None
        self._heartbeat_socket: Optional[zmq.Socket] = None
        self._job_socket: Optional[zmq.Socket] = None

        # Job request/response state
        self._pending_requests: Dict[str, Dict] = {}
        self._job_lock = threading.Lock()

        # Handler buffer tracking for availability reporting
        self._handler_buffers: Dict[str, dict] = {}

        # Threading
        self._threads: List[threading.Thread] = []
        self._running = False
        self._stop_event = threading.Event()
        self._registered = False

        # Admin lifecycle state
        self._start_time = time.time()
        self._decommissioned = False

        # Auto-discover interfaces from method names
        self._discover_and_register_handlers()

        # Register admin lifecycle handlers
        self._register_admin_handlers()

    @property
    def module_id(self) -> str:
        """Return module identifier.

        After registration, returns the Engine-assigned ID.
        Before registration, returns family_name for logging compatibility.
        """
        return self._module_id if self._module_id else self._family_name

    @property
    def family_name(self) -> str:
        """Return module family name (type identifier)."""
        return self._family_name

    @property
    def interfaces(self) -> List[Interface]:
        """Return discovered interfaces."""
        return self._interfaces

    # ── Admin Lifecycle Handlers ──────────────────────────────────

    def _register_admin_handlers(self) -> None:
        """Register admin lifecycle handlers with the engine."""
        self._admin_handler_map = {
            "health_check": self._admin_health_check,
            "availability_check": self._admin_availability_check,
            "respawn": self._admin_respawn,
            "decommission": self._admin_decommission,
        }

    # ── Interface Discovery ───────────────────────────────────────

    @staticmethod
    def _pattern_for_name(name: str) -> Optional[InterfacePattern]:
        """Determine interface pattern from method name (v3).

        Recognized prefixes:
        - on_*      -> consumer interface (event subscription)
        - send_*    -> producer declaration (event publishing)
        - handle_*  -> job handler (request/response consumer)
        - request_* -> job requester declaration (request/response producer)
        """
        if name.startswith("on_"):
            return InterfacePattern.ON
        if name.startswith("send_"):
            return InterfacePattern.SEND
        if name.startswith("handle_"):
            return InterfacePattern.HANDLE
        if name.startswith("request_"):
            return InterfacePattern.REQUEST
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
            if pattern in (InterfacePattern.SEND, InterfacePattern.REQUEST):
                self._register_producer(name, pattern)
            else:
                self._register_handler(name, method, pattern)

    def _register_handler(
        self,
        name: str,
        handler: Callable[..., Any],
        pattern: InterfacePattern = InterfacePattern.ON,
        durability: DurabilityLevel = DurabilityLevel.ASYNC_FLUSH,
    ) -> None:
        """Register an event handler interface (for internal/subclass use).

        Args:
            name: Interface name (e.g., "on_data", "handle_compute")
            handler: Function to handle events
            pattern: Interface pattern type
            durability: Message durability level
        """
        with self._handlers_lock:
            # Strip prefix to get bare event name for handler lookup
            if name.startswith("on_"):
                bare_name = name[3:]
            elif name.startswith("handle_"):
                bare_name = name[7:]
            else:
                bare_name = name
            self._handlers[bare_name] = (handler, pattern)
            # Track buffer for job handlers (handle_* methods)
            if pattern == InterfacePattern.HANDLE:
                self._handler_buffers[bare_name] = {"max_depth": 10, "current": 0}
            self._interfaces.append(
                Interface(
                    name=name,
                    pattern=pattern,
                    event_type=bare_name,
                    durability=durability,
                )
            )
        if self._sub_socket is not None:
            self._sub_socket.setsockopt(zmq.SUBSCRIBE, name.encode())

    def _register_producer(
        self,
        name: str,
        pattern: InterfacePattern = InterfacePattern.SEND,
        durability: DurabilityLevel = DurabilityLevel.ASYNC_FLUSH,
    ) -> None:
        """Register a producer declaration (send_* / request_* method).

        Producer declarations are recorded in _interfaces but do not
        create an inbound handler.
        """
        with self._handlers_lock:
            # Strip prefix to get bare event name for routing lookup
            if name.startswith("send_"):
                event_type = name[5:]
            elif name.startswith("request_"):
                event_type = name[8:]
            else:
                event_type = name
            self._interfaces.append(
                Interface(
                    name=name,
                    pattern=pattern,
                    event_type=event_type,
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
            logger.error("[%s] Failed to register with engine", self._family_name)
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
        # Prefer explicit endpoint; fall back to port from registration ACK
        heartbeat_recv_endpoint = self.heartbeat_receive_endpoint
        if heartbeat_recv_endpoint is None and self._engine_heartbeat_recv_port is not None:
            heartbeat_recv_endpoint = Endpoint(
                self.engine_endpoint.host, self._engine_heartbeat_recv_port
            )
        if heartbeat_recv_endpoint:
            self._heartbeat_socket = self.context.socket(zmq.DEALER)
            self._heartbeat_socket.setsockopt(zmq.LINGER, 0)
            self._heartbeat_socket.connect(str(heartbeat_recv_endpoint))

        # Set up job DEALER socket (for request/response communication)
        if self._engine_job_port is not None:
            self._job_socket = self.context.socket(zmq.DEALER)
            self._job_socket.setsockopt(zmq.LINGER, 0)
            self._job_socket.setsockopt(zmq.IDENTITY, self._module_id.encode())
            self._job_socket.connect(f"tcp://{host}:{self._engine_job_port}")

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

        if self._job_socket is not None:
            self._threads.append(
                threading.Thread(
                    target=self._job_receiver, name="job_recv", daemon=True
                )
            )

        for t in self._threads:
            t.start()

    def stop(self) -> None:
        """Stop the module gracefully.

        Idempotent: safe to call multiple times.  On Windows,
        context.destroy() can hang if sockets are still in use by
        daemon threads, so we wrap each cleanup step in try/except
        to ensure all resources are released.
        """
        if not self._running and self.context is None:
            return  # already stopped

        self._running = False
        self._stop_event.set()

        # Join worker threads (best-effort; daemon threads won't block)
        for t in self._threads:
            try:
                t.join(timeout=2.0)
            except Exception:
                pass

        # Close all sockets (LINGER=0 ensures no wait on pending sends)
        for sock in [
            self._pub_socket, self._sub_socket,
            self._heartbeat_socket, self._job_socket,
        ]:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass
        self._pub_socket = None
        self._sub_socket = None
        self._heartbeat_socket = None
        self._job_socket = None

        # Destroy ZMQ context (releases all OS-level resources)
        if self.context is not None:
            try:
                self.context.destroy(linger=0)
            except Exception:
                pass
            self.context = None

    # ── Registration ──────────────────────────────────────────────

    def _register(self) -> bool:
        """Register with TycheEngine via a one-shot REQ socket.

        Sends family_name to the Engine; receives Engine-assigned module_id
        in the ACK response.

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
                sender=self._family_name,
                event="register",
                payload={
                    "family_name": self._family_name,
                    "interfaces": interfaces_data,
                    "admin_handlers": list(self._admin_handler_map.keys()),
                    "metadata": {},
                },
            )

            sock.send(serialize(msg))

            reply_data = sock.recv()
            reply = deserialize(reply_data)

            if reply.msg_type == MessageType.ACK:
                self._registered = True
                self._module_id = reply.payload.get("module_id", self._family_name)
                self._engine_pub_port = reply.payload.get("event_pub_port")
                self._engine_sub_port = reply.payload.get("event_sub_port")
                self._engine_job_port = reply.payload.get("job_port")
                self._engine_heartbeat_recv_port = reply.payload.get("heartbeat_recv_port")
                logger.info(
                    "Module %s registered as %s",
                    self._family_name, self._module_id,
                )
                return True

        except zmq.error.Again:
            logger.warning("[%s] Registration timeout", self._family_name)
        except Exception as e:
            logger.error("[%s] Registration failed: %s", self._family_name, e)
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
        # v3 unified queue: strip on_ prefix for lookup since handlers
        # are registered under bare topic names
        lookup_topic = topic[3:] if topic.startswith("on_") else topic
        with self._handlers_lock:
            entry = self._handlers.get(lookup_topic)
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

    # ── Job Request/Response ────────────────────────────────────────

    def request_event(self, event: str, payload: dict, timeout: float = 5.0) -> dict:
        """Send a job request and block until a response is received.

        Args:
            event: The job event name to request
            payload: Request payload data
            timeout: Maximum seconds to wait for response

        Returns:
            The response payload dict

        Raises:
            TimeoutError: If no response received within timeout
            RuntimeError: If job socket is not connected
        """
        if self._job_socket is None:
            raise RuntimeError(
                f"[{self._module_id}] Cannot request: job socket not connected"
            )

        correlation_id = str(uuid.uuid4())

        msg = Message(
            msg_type=MessageType.REQUEST,
            sender=self._module_id,
            event=event,
            payload=payload,
            correlation_id=correlation_id,
        )

        wait_event = threading.Event()
        with self._job_lock:
            self._pending_requests[correlation_id] = {
                "event": wait_event,
                "result": None,
            }

        self._job_socket.send_multipart([b"", event.encode(), serialize(msg)])

        # Block until response or timeout
        if not wait_event.wait(timeout):
            with self._job_lock:
                self._pending_requests.pop(correlation_id, None)
            raise TimeoutError(
                f"Job request '{event}' timed out after {timeout}s"
            )

        with self._job_lock:
            entry = self._pending_requests.pop(correlation_id, None)

        return entry["result"] if entry else {}

    def _job_receiver(self) -> None:
        """Receive job messages (requests and responses) from the engine."""
        assert self._job_socket is not None

        poller = zmq.Poller()
        poller.register(self._job_socket, zmq.POLLIN)

        while self._running:
            try:
                socks = dict(poller.poll(timeout=100))
                if self._job_socket not in socks:
                    continue

                frames = self._job_socket.recv_multipart()
                if len(frames) < 3:
                    continue

                # Frames from ROUTER: [b'', topic, message]
                message_frame = frames[2]

                try:
                    msg = deserialize(message_frame)
                except Exception as e:
                    logger.error(
                        "[%s] Job deserialization failed: %s",
                        self._module_id, e,
                    )
                    continue

                if msg.msg_type == MessageType.REQUEST:
                    # Incoming job assignment - dispatch to handler
                    self._handle_job_request(msg)
                elif msg.msg_type == MessageType.RESPONSE:
                    # Response to our outgoing request
                    self._handle_job_response(msg)

            except Exception as e:
                if self._running:
                    logger.error(
                        "[%s] Job receiver error: %s", self._module_id, e
                    )

    def _handle_job_request(self, msg: Message) -> None:
        """Handle an incoming job request by dispatching to the appropriate handler."""
        # Check if this is an admin command
        if msg.event.startswith("admin."):
            admin_cmd = msg.event[len("admin."):]
            if admin_cmd in self._admin_handler_map:
                try:
                    result = self._admin_handler_map[admin_cmd]()
                    response_payload = {"result": result}
                except Exception as e:
                    logger.error(
                        "[%s] Admin handler '%s' raised: %s",
                        self._module_id, admin_cmd, e,
                    )
                    response_payload = {"error": str(e)}

                response = Message(
                    msg_type=MessageType.RESPONSE,
                    sender=self._module_id,
                    event=msg.event,
                    payload=response_payload,
                    correlation_id=msg.correlation_id,
                )
                self._job_socket.send_multipart(
                    [b"", msg.event.encode(), serialize(response)]
                )
                return

        with self._handlers_lock:
            entry = self._handlers.get(msg.event)

        if entry is None:
            # No handler for this job event, send error response
            response = Message(
                msg_type=MessageType.RESPONSE,
                sender=self._module_id,
                event=msg.event,
                payload={"error": f"No handler for job '{msg.event}'"},
                correlation_id=msg.correlation_id,
            )
            self._job_socket.send_multipart(
                [b"", msg.event.encode(), serialize(response)]
            )
            return

        handler, pattern = entry

        # Track buffer usage
        handler_name = msg.event
        if handler_name in self._handler_buffers:
            self._handler_buffers[handler_name]["current"] += 1
        try:
            result = handler(msg.payload)
            response_payload = {"result": result}
        except Exception as e:
            logger.error(
                "[%s] Job handler '%s' raised: %s",
                self._module_id, msg.event, e,
            )
            response_payload = {"error": str(e)}
        finally:
            if handler_name in self._handler_buffers:
                self._handler_buffers[handler_name]["current"] -= 1

        response = Message(
            msg_type=MessageType.RESPONSE,
            sender=self._module_id,
            event=msg.event,
            payload=response_payload,
            correlation_id=msg.correlation_id,
        )
        self._job_socket.send_multipart(
            [b"", msg.event.encode(), serialize(response)]
        )

    def _handle_job_response(self, msg: Message) -> None:
        """Handle an incoming job response by unblocking the waiting requester."""
        correlation_id = msg.correlation_id
        if not correlation_id:
            return

        with self._job_lock:
            entry = self._pending_requests.get(correlation_id)

        if entry is None:
            logger.warning(
                "[%s] Received response for unknown correlation_id=%s",
                self._module_id, correlation_id,
            )
            return

        entry["result"] = msg.payload
        entry["event"].set()

    # ── Availability ──────────────────────────────────────────────

    def _get_handler_availability(self) -> Dict[str, bool]:
        """Return availability dict: handler_name -> has_capacity."""
        return {
            name: info["current"] < info["max_depth"]
            for name, info in self._handler_buffers.items()
        }

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
                    payload={
                        "status": "alive",
                        "availability": self._get_handler_availability(),
                    },
                )
                self._heartbeat_socket.send(serialize(msg))
            except Exception as e:
                if self._running:
                    logger.error(
                        "[%s] Heartbeat send error: %s", self._module_id, e
                    )

            self._stop_event.wait(HEARTBEAT_INTERVAL)
