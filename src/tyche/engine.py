"""TycheEngine - Central broker using threads for multi-process support."""

import logging
import queue
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import msgpack
import zmq

from src.tyche.dead_letter import DeadLetterStore
from src.tyche.heartbeat import HeartbeatManager
from src.tyche.message import Message, deserialize, serialize
from src.tyche.types import (
    ADMIN_PORT_DEFAULT,
    HEARTBEAT_INTERVAL,
    BackpressureStrategy,
    DurabilityLevel,
    Endpoint,
    Interface,
    InterfacePattern,
    MessageType,
    ModuleId,
    ModuleInfo,
)

logger = logging.getLogger(__name__)


class ZmqLogHandler(logging.Handler):
    """Logging handler that publishes log records via ZeroMQ XPUB socket.

    Serializes each log record as a multipart message:
        [b"engine_log", msgpack-packed payload]
    where payload = {"timestamp": float, "level": str, "message": str}.
    """

    def __init__(self, engine: "TycheEngine"):
        super().__init__(level=logging.INFO)
        self._engine = engine

    def emit(self, record: logging.LogRecord) -> None:
        try:
            socket = self._engine._xpub_socket
            if socket is None:
                return
            payload = {
                "event": "engine_log",
                "timestamp": record.created,
                "level": record.levelname,
                "message": self.format(record),
            }
            data = msgpack.packb(payload)
            with self._engine._xpub_lock:
                socket.send_multipart([b"engine_log", data])
        except Exception:
            pass


class TopicQueue:
    """Thread-safe queue with capacity, processed, and dropped stats.

    Items are stored as (enqueue_time, frames) tuples to support TTL tracking.
    """

    def __init__(self, capacity: Optional[int] = None):
        self._items: List[Tuple[float, List[bytes]]] = []
        self.capacity = capacity
        self.processed = 0
        self.dropped = 0
        self._lock = threading.Lock()

    def put(self, item: Tuple[float, List[bytes]]) -> bool:
        with self._lock:
            if self.capacity is not None and len(self._items) >= self.capacity:
                self.dropped += 1
                return False
            self._items.append(item)
            return True

    def get(self) -> Optional[Tuple[float, List[bytes]]]:
        with self._lock:
            if not self._items:
                return None
            self.processed += 1
            return self._items.pop(0)

    def popleft(self) -> Tuple[float, List[bytes]]:
        with self._lock:
            return self._items.pop(0)

    def __len__(self) -> int:
        with self._lock:
            return len(self._items)


class TrackedQueue(queue.Queue):
    """Standard queue with capacity, processed, and dropped stats."""

    def __init__(self, maxsize: int = 0):
        super().__init__(maxsize)
        self.capacity = maxsize if maxsize > 0 else None
        self.dropped = 0
        self._processed = 0
        self._stats_lock = threading.Lock()

    def put(self, item: Any, block: bool = False, timeout: Optional[float] = None) -> None:
        try:
            super().put(item, block=block, timeout=timeout)
        except queue.Full:
            with self._stats_lock:
                self.dropped += 1

    def get(self, block: bool = True, timeout: Optional[float] = None) -> Any:
        item = super().get(block=block, timeout=timeout)
        with self._stats_lock:
            self._processed += 1
        return item

    def get_nowait(self) -> Any:
        item = super().get_nowait()
        with self._stats_lock:
            self._processed += 1
        return item

    @property
    def processed(self) -> int:
        with self._stats_lock:
            return self._processed


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
        heartbeat_receive_endpoint: Optional[Endpoint] = None,
        admin_endpoint: Optional[Endpoint] = None,
        job_endpoint: Optional[Endpoint] = None,
        queue_capacity: Optional[int] = 10000,
        data_dir: Optional[str] = None,
    ):
        self.registration_endpoint = registration_endpoint
        self.event_endpoint = event_endpoint
        self.heartbeat_endpoint = heartbeat_endpoint
        self.heartbeat_receive_endpoint = heartbeat_receive_endpoint or Endpoint(
            heartbeat_endpoint.host, heartbeat_endpoint.port + 1
        )
        # XSUB endpoint for modules to publish events to the engine
        self.event_sub_endpoint = Endpoint(
            event_endpoint.host, event_endpoint.port + 1
        )
        self._admin_endpoint = admin_endpoint

        # Job ROUTER endpoint (default: ADMIN_PORT_DEFAULT + 4 = 5564)
        self._job_endpoint = job_endpoint or Endpoint(
            registration_endpoint.host, ADMIN_PORT_DEFAULT + 4
        )
        self._job_port = self._job_endpoint.port

        # Thread-safe registry
        self._lock = threading.Lock()
        self.modules: Dict[str, ModuleInfo] = {}
        self.interfaces: Dict[str, List[Tuple[str, Interface]]] = {}
        self.heartbeat_manager = HeartbeatManager()

        # Uptime and counters
        self._start_time = time.time()
        self._event_count = 0
        self._register_count = 0

        self._queue_capacity = queue_capacity

        # Topic -> queue_key mapping (queue_key = {event_type}:{pattern})
        self._topic_event_map: Dict[str, str] = {}

        # Per-event topic queues (created on module registration).
        # Foundation for per-topic backpressure, prioritisation, and
        # future transport swaps (e.g. Aeron per-channel publication).
        self._topic_queues: Dict[str, TopicQueue] = {}
        self._topic_queues_lock = threading.Lock()

        # Per-topic backpressure strategy and max depth
        self._topic_backpressure: Dict[str, BackpressureStrategy] = {}
        self._topic_max_depth: Dict[str, int] = {}

        # Broadcast TTL configuration
        self._default_broadcast_ttl: float = 60.0  # seconds
        self._topic_ttl: Dict[str, float] = {}

        # Topic subscriber/producer maps for unified queue routing
        self._topic_subscribers: Dict[str, List[str]] = {}
        self._topic_producers: Dict[str, List[str]] = {}
        self._topic_last_access: Dict[str, float] = {}
        self._topic_queue_ttl: float = 60.0  # seconds
        self._message_queues: Dict[MessageType, TrackedQueue] = {
            MessageType.REGISTER: TrackedQueue(),
            MessageType.ACK: TrackedQueue(),
        }
        # Thread-safe queue for forwarding module heartbeats to PUB socket
        self._heartbeat_queue: TrackedQueue = TrackedQueue(maxsize=10000)

        # Wakeup queue for the egress worker — enqueue a sentinel whenever
        # a message is added to a topic queue so the egress worker blocks
        # instead of spinning.
        self._egress_wakeup: queue.Queue[None] = queue.Queue()

        # Event proxy sockets (shared between proxy ingress and egress workers)
        self._xpub_socket: Optional[zmq.Socket] = None
        self._xsub_socket: Optional[zmq.Socket] = None
        self._xpub_lock = threading.Lock()

        # Registration socket (shared between ingress and egress workers)
        self._registration_socket: Optional[zmq.Socket] = None
        self._registration_lock = threading.Lock()

        # Job routing state
        self._job_handlers: Dict[str, List[str]] = {}      # topic -> [module_ids] with handle_*
        self._job_round_robin: Dict[str, int] = {}          # topic -> round-robin index
        self._pending_jobs: Dict[str, bytes] = {}           # correlation_id -> requester identity
        self._job_router: Optional[zmq.Socket] = None

        # Job timeout tracking
        # Key: correlation_id, Value: dict with tracking info
        self._job_tracking: Dict[str, dict] = {}
        self._job_tracking_lock = threading.Lock()

        # Track handlers marked as unavailable due to timeout
        # Key: module_id, Value: set of topic names that are unavailable
        self._unavailable_handlers: Dict[str, Set[str]] = {}

        # Module availability reported via heartbeat
        # Key: module_id, Value: dict of handler_name -> bool (has capacity)
        self._module_availability: Dict[str, Dict[str, bool]] = {}

        # Admin handlers advertised by each module during registration
        # Key: module_id, Value: list of admin handler names
        self._module_admin_handlers: Dict[str, List[str]] = {}

        # Dead letter store for persisting failed jobs
        self._dead_letter_store = DeadLetterStore(base_dir=Path(data_dir or "./data"))

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
        logger.info("Initializing ZeroMQ context...")
        self.context = zmq.Context()
        self._running = True
        self._stop_event.clear()

        workers = [
            ("registration", self._registration_worker),
            ("registration_egress", self._registration_egress_worker),
            ("heartbeat", self._heartbeat_worker),
            ("heartbeat_receive", self._heartbeat_receive_worker),
            ("monitor", self._monitor_worker),
            ("event_proxy", self._event_proxy_worker),
            ("event_egress", self._event_egress_worker),
            ("admin", self._admin_worker),
            ("job_router", self._job_router_worker),
            ("job_timeout", self._job_timeout_worker),
        ]

        self._threads = []
        for name, target in workers:
            t = threading.Thread(target=target, name=name, daemon=True)
            self._threads.append(t)
            t.start()
            logger.info("Worker '%s' started", name)

        # Attach ZmqLogHandler so engine logs are published to TUI subscribers
        self._zmq_log_handler = ZmqLogHandler(self)
        self._zmq_log_handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(self._zmq_log_handler)

        logger.info(
            "All %d workers started — TycheEngine is running", len(self._threads)
        )
        logger.info(
            "Endpoints: registration=%s, event=%s, heartbeat=%s, "
            "heartbeat_recv=%s, admin=%s, job=%s",
            self.registration_endpoint,
            self.event_endpoint,
            self.heartbeat_endpoint,
            self.heartbeat_receive_endpoint,
            self._admin_endpoint,
            self._job_endpoint,
        )

    def stop(self) -> None:
        """Stop the engine."""
        if not self._running:
            return
        logger.info("Stopping TycheEngine...")
        self._running = False
        self._stop_event.set()

        for t in self._threads:
            t.join(timeout=2.0)
            if t.is_alive():
                logger.warning("Worker '%s' did not stop within timeout", t.name)
            else:
                logger.info("Worker '%s' stopped", t.name)

        # Remove ZmqLogHandler before destroying context to avoid send on closed socket
        if hasattr(self, '_zmq_log_handler'):
            logger.removeHandler(self._zmq_log_handler)

        if self.context:
            logger.info("Destroying ZeroMQ context...")
            self.context.destroy(linger=0)
            self.context = None

        logger.info("TycheEngine shutdown complete")

    # ── Registration ──────────────────────────────────────────────

    def _registration_worker(self) -> None:
        """Receive registration requests and enqueue to typed queue."""
        assert self.context is not None
        self._registration_socket = self.context.socket(zmq.ROUTER)
        assert self._registration_socket is not None
        self._registration_socket.setsockopt(zmq.LINGER, 0)
        try:
            self._registration_socket.bind(str(self.registration_endpoint))
            self._registration_socket.setsockopt(zmq.RCVTIMEO, 100)

            while self._running:
                try:
                    frames = self._registration_socket.recv_multipart()
                    self._message_queues[MessageType.REGISTER].put(frames)
                except zmq.error.Again:
                    continue
                except Exception as e:
                    if self._running:
                        logger.error("Registration error: %s", e)
        except Exception as e:
            logger.error("Registration worker failed to start: %s", e)
        finally:
            if self._registration_socket is not None:
                self._registration_socket.close()
                self._registration_socket = None

    def _registration_egress_worker(self) -> None:
        """Dequeue registration requests and send ACK replies."""
        while self._running:
            try:
                frames = self._message_queues[MessageType.REGISTER].get(timeout=0.1)
            except queue.Empty:
                continue
            self._process_registration(frames)

    def _process_registration(self, frames: List[bytes]) -> None:
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
                with self._lock:
                    self._register_count += 1

                ack = Message(
                    msg_type=MessageType.ACK,
                    sender="engine",
                    event="register_ack",
                    payload={
                        "status": "ok",
                        "module_id": module_info.module_id,
                        "event_pub_port": self.event_endpoint.port,
                        "event_sub_port": self.event_sub_endpoint.port,
                        "job_port": self._job_port,
                        "heartbeat_recv_port": self.heartbeat_receive_endpoint.port,
                    },
                )
                if self._registration_socket is not None:
                    with self._registration_lock:
                        self._registration_socket.send_multipart(
                            [identity, b"", serialize(ack)]
                        )
                logger.info(
                    "Module %s registered as %s",
                    module_info.family_name, module_info.module_id,
                )
        except Exception as e:
            logger.error("Failed to process registration: %s", e)

    def _create_module_info(self, msg: Message) -> ModuleInfo:
        """Create ModuleInfo from registration message.

        The Engine is the sole authority for module_id generation.
        Modules send their family_name during registration; the Engine
        assigns a unique module_id using ModuleId.generate(family_name),
        producing an ID in the format {family}_{6-char hex}.
        """
        family_name = msg.payload.get("family_name") or msg.sender or "unknown"
        module_id = ModuleId.generate(family_name)
        interfaces_data = msg.payload.get("interfaces", [])

        interfaces = [
            Interface(
                name=i["name"],
                pattern=InterfacePattern(i["pattern"]),
                event_type=i.get("event_type", i["name"]),
                durability=DurabilityLevel(i.get("durability", 1)),
                backpressure=BackpressureStrategy(
                    i.get("backpressure", BackpressureStrategy.DROP_OLDEST.value)
                ),
                max_queue_depth=i.get("max_queue_depth", 10000),
                wait_timeout=i.get("wait_timeout"),
            )
            for i in interfaces_data
        ]

        # Extract and store admin handlers
        admin_handlers = msg.payload.get("admin_handlers", [])
        self._module_admin_handlers[module_id] = admin_handlers

        return ModuleInfo(
            module_id=module_id,
            interfaces=interfaces,
            metadata=msg.payload.get("metadata", {}),
            family_name=family_name,
        )

    def register_module(self, module_info: ModuleInfo) -> None:
        """Register a module and its interfaces (thread-safe).

        Creates a dedicated queue for every interface/topic declared by the
        module, and updates subscriber/producer maps for unified routing.
        """
        with self._lock:
            self.modules[module_info.module_id] = module_info

            for interface in module_info.interfaces:
                topic = interface.event_type
                if topic not in self.interfaces:
                    self.interfaces[topic] = []
                self.interfaces[topic].append(
                    (module_info.module_id, interface)
                )
                queue_key = interface.event_type
                self._topic_event_map[topic] = queue_key

                # Store per-topic backpressure strategy and max depth
                self._topic_backpressure[queue_key] = interface.backpressure
                self._topic_max_depth[queue_key] = interface.max_queue_depth

                # Store per-topic TTL if the interface specifies wait_timeout
                if hasattr(interface, 'wait_timeout') and interface.wait_timeout is not None:
                    self._topic_ttl[queue_key] = interface.wait_timeout

                with self._topic_queues_lock:
                    if queue_key not in self._topic_queues:
                        self._topic_queues[queue_key] = TopicQueue(
                            capacity=interface.max_queue_depth,
                        )
                        logger.info("Created topic queue: %s (strategy=%s, depth=%d)",
                                    queue_key, interface.backpressure.value,
                                    interface.max_queue_depth)
                # Update subscriber/producer maps (v3 unified queue)
                if interface.pattern == InterfacePattern.ON:
                    subs = self._topic_subscribers.setdefault(queue_key, [])
                    if module_info.module_id not in subs:
                        subs.append(module_info.module_id)
                elif interface.pattern == InterfacePattern.SEND:
                    prods = self._topic_producers.setdefault(queue_key, [])
                    if module_info.module_id not in prods:
                        prods.append(module_info.module_id)
                elif interface.pattern == InterfacePattern.HANDLE:
                    handlers = self._job_handlers.setdefault(topic, [])
                    if module_info.module_id not in handlers:
                        handlers.append(module_info.module_id)
                    if topic not in self._job_round_robin:
                        self._job_round_robin[topic] = 0
                    logger.info(
                        "Registered job handler: %s for topic '%s'",
                        module_info.module_id, topic,
                    )
                elif interface.pattern == InterfacePattern.REQUEST:
                    prods = self._topic_producers.setdefault(queue_key, [])
                    if module_info.module_id not in prods:
                        prods.append(module_info.module_id)
                    logger.info(
                        "Registered job producer: %s for topic '%s'",
                        module_info.module_id, topic,
                    )

        self.heartbeat_manager.register(module_info.module_id)

    def unregister_module(self, module_id: str) -> None:
        """Unregister a module (thread-safe)."""
        with self._lock:
            if module_id not in self.modules:
                return

            module_info = self.modules[module_id]

            for interface in module_info.interfaces:
                queue_key = interface.event_type
                if queue_key in self.interfaces:
                    self.interfaces[queue_key] = [
                        (mid, iface)
                        for mid, iface in self.interfaces[queue_key]
                        if mid != module_id
                    ]
                # Clean up subscriber/producer maps
                if queue_key in self._topic_subscribers:
                    self._topic_subscribers[queue_key] = [
                        mid for mid in self._topic_subscribers[queue_key]
                        if mid != module_id
                    ]
                if queue_key in self._topic_producers:
                    self._topic_producers[queue_key] = [
                        mid for mid in self._topic_producers[queue_key]
                        if mid != module_id
                    ]

            del self.modules[module_id]

            # Clean up job handler registrations
            for topic, handler_list in list(self._job_handlers.items()):
                self._job_handlers[topic] = [
                    mid for mid in handler_list if mid != module_id
                ]

            # Clean up unavailable handlers tracking
            self._unavailable_handlers.pop(module_id, None)

            # Clean up module availability
            self._module_availability.pop(module_id, None)

            # Clean up admin handler registrations
            self._module_admin_handlers.pop(module_id, None)

        # Clean up any pending jobs tracked against this module as handler
        with self._job_tracking_lock:
            for corr_id, info in list(self._job_tracking.items()):
                if info.get("handler_id") == module_id:
                    # Handler unregistered — mark as needing re-dispatch
                    info["handler_id"] = None
                    info["dispatch_time"] = None

        self.heartbeat_manager.unregister(module_id)

    # ── Admin Handler Invocation ─────────────────────────────────

    def invoke_admin_handler(
        self, module_id: str, handler_name: str, timeout: float = 10.0
    ) -> Optional[dict]:
        """Invoke an admin handler on a specific module.

        Args:
            module_id: Target module
            handler_name: One of: health_check, availability_check, respawn, decommission
            timeout: How long to wait for response

        Returns:
            Response dict from the module, or None on timeout
        """
        if module_id not in self._module_admin_handlers:
            logger.warning("Module %s not registered", module_id)
            return None
        if handler_name not in self._module_admin_handlers[module_id]:
            logger.warning(
                "Module %s does not support admin handler: %s",
                module_id, handler_name,
            )
            return None

        # Send admin job via job router
        topic = f"admin.{handler_name}"
        correlation_id = str(uuid.uuid4())
        msg = Message(
            msg_type=MessageType.REQUEST,
            sender="engine",
            event=topic,
            payload={"command": handler_name},
            correlation_id=correlation_id,
        )
        # Route directly to the specific module (bypass round-robin)
        frames = [module_id.encode(), b"", topic.encode(), serialize(msg)]
        try:
            if self._job_router is not None:
                self._job_router.send_multipart(frames)
            else:
                logger.warning("Job router not available")
                return None
        except Exception as e:
            logger.error("Failed to send admin command to %s: %s", module_id, e)
            return None

        # For now, this is fire-and-forget
        # Full synchronous waiting can be added later
        return {"status": "sent", "correlation_id": correlation_id}

    def health_check_module(self, module_id: str) -> Optional[dict]:
        """Check health of a specific module."""
        return self.invoke_admin_handler(module_id, "health_check")

    def decommission_module(self, module_id: str) -> Optional[dict]:
        """Gracefully decommission a module."""
        return self.invoke_admin_handler(module_id, "decommission")

    # ── Event Proxy (XPUB/XSUB) ──────────────────────────────────

    def _event_proxy_worker(self) -> None:
        """XSUB/XPUB proxy for event distribution.

        Modules publish events to the XSUB socket.
        Modules subscribe to events via the XPUB socket.
        The proxy forwards between them directly for minimum latency.

        Per-topic queues are maintained for all events (unified queue
        in v3) and future backpressure / persistence features,
        but the hot path bypasses them to preserve throughput.
        """
        assert self.context is not None

        self._xpub_socket = self.context.socket(zmq.XPUB)
        assert self._xpub_socket is not None
        self._xpub_socket.setsockopt(zmq.LINGER, 0)
        self._xpub_socket.setsockopt(zmq.SNDHWM, 10000)
        self._xpub_socket.setsockopt(zmq.RCVHWM, 10000)
        self._xsub_socket = self.context.socket(zmq.XSUB)
        assert self._xsub_socket is not None
        self._xsub_socket.setsockopt(zmq.LINGER, 0)
        self._xsub_socket.setsockopt(zmq.SNDHWM, 10000)
        self._xsub_socket.setsockopt(zmq.RCVHWM, 10000)

        try:
            self._xpub_socket.bind(str(self.event_endpoint))
            self._xsub_socket.bind(str(self.event_sub_endpoint))

            # Pre-subscribe XSUB to all topics (empty prefix = match everything).
            # This ensures upstream PUB sockets start sending immediately,
            # solving the ZMQ "slow joiner" problem where messages are
            # dropped if no subscription has been forwarded yet.
            # Without this, a publisher's PUB socket silently drops all
            # messages until XSUB forwards a matching subscription.
            self._xsub_socket.send_multipart([b'\x01'])
            logger.debug("XSUB pre-subscribed to all topics")

            poller = zmq.Poller()
            poller.register(self._xpub_socket, zmq.POLLIN)
            poller.register(self._xsub_socket, zmq.POLLIN)

            while self._running:
                try:
                    events = dict(poller.poll(100))
                except zmq.error.ZMQError:
                    break

                if self._xpub_socket in events:
                    with self._xpub_lock:
                        frame = self._xpub_socket.recv_multipart()
                    self._xsub_socket.send_multipart(frame)

                if self._xsub_socket in events:
                    # Batch drain — forward directly to XPUB AND enqueue to topic queues.
                    # Direct forwarding (hot path) ensures minimum latency for
                    # live subscribers.  Topic queues serve as a secondary path
                    # for dead-letter / TTL / monitoring.
                    batch_count = 0
                    while self._running:
                        try:
                            frames = self._xsub_socket.recv_multipart(zmq.NOBLOCK)
                            # Hot path: direct forward to XPUB
                            if self._xpub_socket is not None:
                                try:
                                    with self._xpub_lock:
                                        self._xpub_socket.send_multipart(frames)
                                except Exception:
                                    pass  # egress will retry from queue
                            # Secondary path: enqueue for monitoring / dead-letter
                            self._enqueue_from_xsub(frames)
                            batch_count += 1
                        except zmq.error.Again:
                            break
                    if batch_count:
                        with self._lock:
                            self._event_count += batch_count
        except Exception as e:
            logger.error("Event proxy worker failed: %s", e)
        finally:
            if self._xpub_socket is not None:
                self._xpub_socket.close()
                self._xpub_socket = None
            if self._xsub_socket is not None:
                self._xsub_socket.close()
                self._xsub_socket = None

    def _apply_backpressure(
        self, q: TopicQueue, topic: str, frames: List[bytes],
    ) -> bool:
        """Apply backpressure strategy when queue is at max depth.

        Wraps frames with an enqueue timestamp before storing.
        Returns True if the message was enqueued, False if dropped.
        """
        strategy = self._topic_backpressure.get(
            topic, BackpressureStrategy.DROP_OLDEST,
        )
        max_depth = self._topic_max_depth.get(topic, self._queue_capacity or 10000)
        entry = (time.time(), frames)

        if len(q) < max_depth:
            q.put(entry)
            return True

        if strategy == BackpressureStrategy.DROP_OLDEST:
            q.popleft()
            q.put(entry)
            q.dropped += 1
            logger.debug("Queue full for %s, dropped oldest message", topic)
            return True
        elif strategy == BackpressureStrategy.DROP_NEWEST:
            # Don't enqueue the new message
            q.dropped += 1
            logger.debug("Queue full for %s, dropped newest message", topic)
            return False
        elif strategy == BackpressureStrategy.BLOCK_PRODUCER:
            # For ZMQ we can't truly block the producer in XSUB/XPUB pattern.
            # Graceful degradation: log warning and drop newest.
            q.dropped += 1
            logger.warning(
                "Queue full for %s, BLOCK_PRODUCER not fully supported "
                "in broker pattern, dropping newest",
                topic,
            )
            return False

        # Default fallback
        q.popleft()
        q.put(entry)
        return True

    def _enqueue_from_xsub(self, frames: List[bytes]) -> None:
        """Route XSUB data to the dedicated topic queue.

        Topic is taken from frame[0]; queue is created on-demand if a module
        has not yet registered for this topic (dynamic subscription).
        Fast path avoids the dict lock when the queue already exists.
        Backpressure strategy is applied per-topic (v3 unified queue).
        """
        if len(frames) < 2:
            return
        topic = frames[0].decode()
        queue_key = self._topic_event_map.get(topic, topic)
        # Fast path: lock-free lookup for existing queues (hot path)
        q = self._topic_queues.get(queue_key)
        if q is not None:
            self._apply_backpressure(q, queue_key, frames)
            self._topic_last_access[topic] = time.time()
            self._egress_wakeup.put(None)
            return
        # Slow path: create queue under lock
        with self._topic_queues_lock:
            q = self._topic_queues.get(queue_key)
            if q is None:
                q = TopicQueue(capacity=self._queue_capacity)
                self._topic_queues[queue_key] = q
                logger.debug("Created dynamic topic queue: %s", queue_key)
            self._apply_backpressure(q, queue_key, frames)
        self._egress_wakeup.put(None)

    def _event_egress_worker(self) -> None:
        """Background drainer for all topic queues.

        The proxy worker now directly forwards XSUB→XPUB (hot path), so
        this worker only drains topic queues for monitoring, TTL checking,
        and dead-lettering expired messages.  It does NOT re-send via XPUB
        (that would duplicate messages already sent directly).
        """
        while self._running:
            try:
                self._egress_wakeup.get(timeout=1.0)
            except queue.Empty:
                continue

            # Drain all topic queues completely
            with self._topic_queues_lock:
                queues = list(self._topic_queues.items())

            for topic, q in queues:
                while self._running:
                    item = q.get()
                    if item is None:
                        break

                    enqueue_time, frames = item
                    now = time.time()

                    # Determine effective TTL for this topic
                    topic_ttl = self._topic_ttl.get(
                        topic, self._default_broadcast_ttl
                    )

                    if now - enqueue_time > topic_ttl:
                        # Message expired — dead-letter it
                        try:
                            # Deserialize only for dead-letter persistence
                            if len(frames) >= 2:
                                msg = deserialize(frames[1])
                            else:
                                msg = deserialize(frames[0])
                            self._dead_letter_store.persist(
                                message=msg,
                                topic=topic,
                                reason="broadcast_ttl_expired",
                            )
                        except Exception as e:
                            logger.debug(
                                "Failed to dead-letter expired broadcast "
                                "for topic %s: %s", topic, e,
                            )
                        logger.debug(
                            "Broadcast message expired for topic %s, "
                            "dead-lettered (age=%.2fs, ttl=%.2fs)",
                            topic, now - enqueue_time, topic_ttl,
                        )

                    # Update last access time for monitoring
                    self._topic_last_access[topic] = time.time()

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
                    # Send engine heartbeat
                    msg = Message(
                        msg_type=MessageType.HEARTBEAT,
                        sender="engine",
                        event="heartbeat",
                        payload={"timestamp": time.time()},
                    )
                    socket.send_multipart([b"heartbeat", serialize(msg)])

                    # Forward any module heartbeats from the queue
                    while True:
                        try:
                            module_msg = self._heartbeat_queue.get_nowait()
                            socket.send_multipart([b"heartbeat", serialize(module_msg)])
                        except queue.Empty:
                            break

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
                                # Extract availability from heartbeat payload
                                if msg.payload and "availability" in msg.payload:
                                    self._module_availability[msg.sender] = msg.payload["availability"]
                                # Forward module heartbeat to PUB socket via queue
                                self._heartbeat_queue.put(msg)
                                # Recovery: if handler was marked unavailable, restore it
                                self._recover_handler(msg.sender)
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
        """Monitor peer health and unregister expired modules.

        Also garbage-collect topic queues that have been idle with no
        subscribers or producers for longer than TOPIC_QUEUE_TTL_SECONDS.
        """
        while self._running:
            expired = self.heartbeat_manager.tick_all()
            for module_id in expired:
                logger.info("Module %s expired", module_id)
                self.unregister_module(module_id)

            # Topic queue GC
            now = time.time()
            with self._topic_queues_lock:
                dead_topics = []
                for topic, q in self._topic_queues.items():
                    subs = self._topic_subscribers.get(topic, [])
                    prods = self._topic_producers.get(topic, [])
                    last_access = self._topic_last_access.get(topic, now)
                    if not subs and not prods and (now - last_access) > self._topic_queue_ttl:
                        dead_topics.append(topic)
                for topic in dead_topics:
                    del self._topic_queues[topic]
                    self._topic_last_access.pop(topic, None)
                    logger.debug("GC'd idle topic queue: %s", topic)

            time.sleep(HEARTBEAT_INTERVAL)

    # ── Job Routing ───────────────────────────────────────────────

    def _job_router_worker(self) -> None:
        """Route job requests and responses between modules via ROUTER socket."""
        assert self.context is not None
        self._job_router = self.context.socket(zmq.ROUTER)
        assert self._job_router is not None
        self._job_router.setsockopt(zmq.LINGER, 0)
        try:
            self._job_router.bind(str(self._job_endpoint))
            logger.info("Job router bound to %s", self._job_endpoint)

            poller = zmq.Poller()
            poller.register(self._job_router, zmq.POLLIN)

            while self._running:
                try:
                    events = dict(poller.poll(100))
                except zmq.error.ZMQError:
                    break

                if self._job_router not in events:
                    continue

                try:
                    frames = self._job_router.recv_multipart()
                except zmq.error.Again:
                    continue
                except Exception as e:
                    if self._running:
                        logger.error("Job router recv error: %s", e)
                    continue

                # Expected frames from DEALER via ROUTER: [identity, b'', topic, message]
                if len(frames) < 4:
                    logger.warning("Job router: malformed frame (len=%d)", len(frames))
                    continue

                identity = frames[0]
                topic_frame = frames[2]
                message_frame = frames[3]

                try:
                    msg = deserialize(message_frame)
                except Exception as e:
                    logger.error("Job router: failed to deserialize message: %s", e)
                    continue

                if msg.msg_type == MessageType.REQUEST:
                    self._handle_job_request(identity, topic_frame, message_frame, msg)
                elif msg.msg_type == MessageType.RESPONSE:
                    self._handle_job_response(identity, topic_frame, message_frame, msg)
                else:
                    logger.warning(
                        "Job router: unexpected msg_type=%s from %s",
                        msg.msg_type, msg.sender,
                    )

        except Exception as e:
            logger.error("Job router worker failed: %s", e)
        finally:
            if self._job_router is not None:
                self._job_router.close()
                self._job_router = None

    def _publish_job_event(self, msg: Message) -> None:
        """Mirror a job message to the XPUB socket so TUI subscribers can see it."""
        if self._xpub_socket is None:
            return
        try:
            data = serialize(msg)
            with self._xpub_lock:
                self._xpub_socket.send_multipart([msg.event.encode(), data])
        except Exception:
            pass

    def _handle_job_request(
        self,
        identity: bytes,
        topic_frame: bytes,
        message_frame: bytes,
        msg: Message,
    ) -> None:
        """Route a job request to the appropriate handler via round-robin."""
        topic = msg.event
        now = time.time()

        # Extract timeouts from message payload (with defaults)
        wait_timeout = msg.payload.get("wait_timeout", 30.0) if msg.payload else 30.0
        run_timeout = msg.payload.get("run_timeout", 60.0) if msg.payload else 60.0

        handlers = self._job_handlers.get(topic, [])

        # Filter out unavailable handlers
        available_handlers = [
            h for h in handlers
            if self._is_handler_available(h, topic)
        ]

        if not available_handlers:
            if not handlers:
                # No handler registered at all — send error response immediately
                error_resp = Message(
                    msg_type=MessageType.RESPONSE,
                    sender="engine",
                    event=msg.event,
                    payload={"error": f"No handler registered for job '{topic}'"},
                    correlation_id=msg.correlation_id,
                )
                try:
                    assert self._job_router is not None
                    self._job_router.send_multipart(
                        [identity, b"", topic_frame, serialize(error_resp)]
                    )
                except Exception as e:
                    logger.error("Job router: failed to send error response: %s", e)
                logger.warning("Job router: no handler for topic '%s'", topic)
                return

            # Handlers exist but all unavailable — queue for wait_timeout
            tracking_info = {
                "requester_id": identity,
                "handler_id": None,
                "dispatch_time": None,
                "wait_start_time": now,
                "wait_timeout": wait_timeout,
                "run_timeout": run_timeout,
                "topic": topic,
                "topic_frame": topic_frame,
                "message_frame": message_frame,
            }
            with self._job_tracking_lock:
                self._job_tracking[msg.correlation_id] = tracking_info
            self._pending_jobs[msg.correlation_id] = identity
            logger.debug(
                "Job router: all handlers unavailable for '%s' (corr=%s), waiting",
                topic, msg.correlation_id,
            )
            return

        # Round-robin selection among available handlers
        idx = self._job_round_robin.get(topic, 0) % len(available_handlers)
        self._job_round_robin[topic] = idx + 1
        handler_module_id = available_handlers[idx]

        # Store pending job mapping: correlation_id -> requester identity
        self._pending_jobs[msg.correlation_id] = identity

        # Track the job with timeout info
        tracking_info = {
            "requester_id": identity,
            "handler_id": handler_module_id,
            "dispatch_time": now,
            "wait_start_time": now,
            "wait_timeout": wait_timeout,
            "run_timeout": run_timeout,
            "topic": topic,
            "topic_frame": topic_frame,
            "message_frame": message_frame,
        }
        with self._job_tracking_lock:
            self._job_tracking[msg.correlation_id] = tracking_info

        # Mirror request to XPUB so TUI can observe job traffic
        self._publish_job_event(msg)

        # Forward request to handler
        try:
            assert self._job_router is not None
            self._job_router.send_multipart(
                [handler_module_id.encode(), b"", topic_frame, message_frame]
            )
            logger.debug(
                "Job router: forwarded request '%s' (corr=%s) to handler '%s'",
                topic, msg.correlation_id, handler_module_id,
            )
        except Exception as e:
            logger.error(
                "Job router: failed to forward request to '%s': %s",
                handler_module_id, e,
            )
            # Clean up pending job on failure
            self._pending_jobs.pop(msg.correlation_id, None)
            with self._job_tracking_lock:
                self._job_tracking.pop(msg.correlation_id, None)

    def _handle_job_response(
        self,
        identity: bytes,
        topic_frame: bytes,
        message_frame: bytes,
        msg: Message,
    ) -> None:
        """Route a job response back to the original requester."""
        requester_identity = self._pending_jobs.get(msg.correlation_id)

        if requester_identity is None:
            logger.warning(
                "Job router: stale response for correlation_id=%s from %s",
                msg.correlation_id, msg.sender,
            )
            return

        # Remove from timeout tracking
        with self._job_tracking_lock:
            self._job_tracking.pop(msg.correlation_id, None)

        # Mirror response to XPUB so TUI can observe job traffic
        self._publish_job_event(msg)

        # Forward response to requester
        try:
            assert self._job_router is not None
            self._job_router.send_multipart(
                [requester_identity, b"", topic_frame, message_frame]
            )
            logger.debug(
                "Job router: forwarded response (corr=%s) back to requester",
                msg.correlation_id,
            )
        except Exception as e:
            logger.error(
                "Job router: failed to forward response (corr=%s): %s",
                msg.correlation_id, e,
            )
        finally:
            del self._pending_jobs[msg.correlation_id]

    def _job_timeout_worker(self) -> None:
        """Periodically check for timed-out jobs."""
        while self._running:
            now = time.time()
            timed_out: List[tuple] = []

            with self._job_tracking_lock:
                for corr_id, info in list(self._job_tracking.items()):
                    if info["handler_id"] is not None:
                        # Job is dispatched — check run_timeout
                        if now - info["dispatch_time"] > info["run_timeout"]:
                            timed_out.append((corr_id, "run_timeout"))
                    else:
                        # Job is waiting for handler — check wait_timeout
                        if now - info["wait_start_time"] > info["wait_timeout"]:
                            timed_out.append((corr_id, "wait_timeout"))

            for corr_id, reason in timed_out:
                self._handle_job_timeout(corr_id, reason)

            time.sleep(1.0)  # Check every second

    def _handle_job_timeout(self, correlation_id: str, reason: str) -> None:
        """Handle a job that has timed out."""
        with self._job_tracking_lock:
            info = self._job_tracking.pop(correlation_id, None)
        if info is None:
            return

        if reason == "run_timeout" and info["handler_id"]:
            # Mark handler as unavailable for this topic
            handler_id = info["handler_id"]
            if handler_id not in self._unavailable_handlers:
                self._unavailable_handlers[handler_id] = set()
            self._unavailable_handlers[handler_id].add(info["topic"])
            logger.warning(
                "Handler '%s' timed out for topic '%s', marked unavailable",
                handler_id, info["topic"],
            )

            # Try to retry on another handler
            if self._retry_job(correlation_id, info):
                return  # Successfully retried — do not send error

            # No other handler available — put back as waiting (subject to wait_timeout)
            info["handler_id"] = None
            info["dispatch_time"] = None
            with self._job_tracking_lock:
                self._job_tracking[correlation_id] = info
            logger.info(
                "Job %s: no alternative handler for '%s', waiting for recovery",
                correlation_id, info["topic"],
            )
            return

        if reason == "wait_timeout":
            # Dead-letter the job
            logger.warning(
                "Job %s wait_timeout for topic '%s'", correlation_id, info["topic"]
            )
            # Reconstruct message from stored frame for dead-lettering
            try:
                msg = deserialize(info["message_frame"])
                self._dead_letter_store.persist(
                    message=msg, topic=info["topic"], reason="wait_timeout"
                )
            except Exception as e:
                logger.error(
                    "Failed to dead-letter job %s: %s", correlation_id, e
                )

        # Remove from pending jobs and send error to requester
        self._pending_jobs.pop(correlation_id, None)

        error_msg = Message(
            msg_type=MessageType.RESPONSE,
            sender="engine",
            event=info["topic"],
            payload={"error": reason, "correlation_id": correlation_id},
            correlation_id=correlation_id,
        )
        requester_id = info["requester_id"]
        error_frames = [
            requester_id if isinstance(requester_id, bytes) else requester_id.encode(),
            b"",
            info["topic_frame"],
            serialize(error_msg),
        ]
        try:
            if self._job_router is not None:
                self._job_router.send_multipart(error_frames)
                logger.debug(
                    "Job router: sent timeout error (reason=%s, corr=%s) to requester",
                    reason, correlation_id,
                )
        except Exception as e:
            logger.error(
                "Job router: failed to send timeout error (corr=%s): %s",
                correlation_id, e,
            )

    def _retry_job(self, correlation_id: str, info: dict) -> bool:
        """Try to assign the job to another available handler.

        Returns True if successfully retried, False if no handler available.
        """
        topic = info["topic"]
        handlers = self._job_handlers.get(topic, [])

        # Filter out unavailable handlers
        available_handlers = [
            h for h in handlers
            if self._is_handler_available(h, topic)
        ]

        if not available_handlers:
            return False

        # Round-robin selection among available handlers
        idx = self._job_round_robin.get(topic, 0) % len(available_handlers)
        self._job_round_robin[topic] = idx + 1
        handler_module_id = available_handlers[idx]

        # Dispatch to the new handler
        try:
            assert self._job_router is not None
            self._job_router.send_multipart(
                [handler_module_id.encode(), b"", info["topic_frame"], info["message_frame"]]
            )
        except Exception as e:
            logger.error(
                "Job router: retry dispatch to '%s' failed: %s",
                handler_module_id, e,
            )
            return False

        # Update tracking with new handler
        info["handler_id"] = handler_module_id
        info["dispatch_time"] = time.time()
        with self._job_tracking_lock:
            self._job_tracking[correlation_id] = info

        logger.info(
            "Job %s retried: dispatched to handler '%s' for topic '%s'",
            correlation_id, handler_module_id, topic,
        )
        return True

    def _is_handler_available(self, module_id: str, topic: str) -> bool:
        """Check if a handler is available for routing."""
        # Check timeout-based unavailability
        if module_id in self._unavailable_handlers:
            if topic in self._unavailable_handlers[module_id]:
                return False
        # Check reported availability from heartbeat
        availability = self._module_availability.get(module_id, {})
        if topic in availability and not availability[topic]:
            return False
        return True

    def _recover_handler(self, module_id: str) -> None:
        """Restore a handler that was marked unavailable when it sends a heartbeat.

        If the handler had topics marked unavailable, clear them and attempt
        to dispatch any waiting jobs (handler_id=None) for those topics.
        """
        if module_id not in self._unavailable_handlers:
            return

        recovered_topics = self._unavailable_handlers.pop(module_id)
        if not recovered_topics:
            return

        logger.info(
            "Handler '%s' recovered, clearing unavailable status for topics: %s",
            module_id, recovered_topics,
        )

        # Check if any waiting jobs can now be dispatched
        with self._job_tracking_lock:
            waiting_jobs = [
                (corr_id, info)
                for corr_id, info in self._job_tracking.items()
                if info["handler_id"] is None and info["topic"] in recovered_topics
            ]

        for corr_id, info in waiting_jobs:
            # Remove from tracking (retry_job will re-add it)
            with self._job_tracking_lock:
                self._job_tracking.pop(corr_id, None)
            if not self._retry_job(corr_id, info):
                # Put back as waiting if still no handler
                with self._job_tracking_lock:
                    self._job_tracking[corr_id] = info

    def _admin_worker(self) -> None:
        """Admin ROUTER socket for querying engine state."""
        assert self.context is not None
        socket = self.context.socket(zmq.ROUTER)
        socket.setsockopt(zmq.LINGER, 0)
        try:
            socket.bind(str(self._admin_endpoint))
            socket.setsockopt(zmq.RCVTIMEO, 100)

            while self._running:
                try:
                    frames = socket.recv_multipart()
                    self._process_admin_query(socket, frames)
                except zmq.error.Again:
                    continue
                except Exception as e:
                    if self._running:
                        logger.error("Admin query error: %s", e)
        except Exception as e:
            logger.error("Admin worker failed to start: %s", e)
        finally:
            socket.close()

    def _process_admin_query(
        self, socket: zmq.Socket, frames: List[bytes]
    ) -> None:
        """Process an admin query request."""
        if len(frames) < 2:
            return

        identity = frames[0]
        # ROUTER adds identity frame; REQ adds empty delimiter
        msg_data = frames[2] if len(frames) >= 3 and frames[1] == b"" else frames[1]

        try:
            query = msgpack.unpackb(msg_data, raw=False)
            response: dict = {}

            if query == "STATUS":
                with self._lock:
                    uptime = time.time() - self._start_time
                    with self._topic_queues_lock:
                        topic_queue_sizes = {
                            topic: len(q)
                            for topic, q in self._topic_queues.items()
                        }
                    response = {
                        "status": "running",
                        "uptime": uptime,
                        "module_count": len(self.modules),
                        "event_count": self._event_count,
                        "register_count": self._register_count,
                        "topic_queue_count": len(self._topic_queues),
                        "topic_queue_sizes": topic_queue_sizes,
                        "topic_subscribers": {
                            t: len(s) for t, s in self._topic_subscribers.items()
                        },
                        "topic_producers": {
                            t: len(p) for t, p in self._topic_producers.items()
                        },
                        "other_queue_sizes": {
                            "register": self._message_queues[MessageType.REGISTER].qsize(),
                            "ack": self._message_queues[MessageType.ACK].qsize(),
                            "heartbeat": self._heartbeat_queue.qsize(),
                        },
                    }
            elif query == "MODULES":
                with self._lock:
                    modules_list = []
                    for module_id, module_info in self.modules.items():
                        liveness = self.heartbeat_manager.get_liveness(module_id)
                        last_seen = self.heartbeat_manager.get_last_seen(module_id)
                        modules_list.append({
                            "module_id": module_id,
                            "interfaces": [i.name for i in module_info.interfaces],
                            "liveness": liveness,
                            "last_seen": last_seen,
                            "admin_handlers": self._module_admin_handlers.get(module_id, []),
                            "availability": self._module_availability.get(module_id, {}),
                        })
                    response = {"modules": modules_list}
            elif query == "QUEUES":
                queues: List[dict] = []
                with self._topic_queues_lock:
                    for topic, q in self._topic_queues.items():
                        queues.append({
                            "name": topic,
                            "size": len(q),
                            "capacity": q.capacity,
                            "processed": q.processed,
                            "dropped": q.dropped,
                        })
                for mt, mq in self._message_queues.items():
                    queues.append({
                        "name": mt.name.lower(),
                        "size": mq.qsize(),
                        "capacity": mq.capacity,
                        "processed": mq.processed,
                        "dropped": mq.dropped,
                    })
                hbq = self._heartbeat_queue
                queues.append({
                    "name": "heartbeat",
                    "size": hbq.qsize(),
                    "capacity": hbq.capacity,
                    "processed": hbq.processed,
                    "dropped": hbq.dropped,
                })
                response = {"queues": queues}
            elif query == "JOBS":
                with self._job_tracking_lock:
                    jobs_list = []
                    for corr_id, info in self._job_tracking.items():
                        requester_id = info["requester_id"]
                        if isinstance(requester_id, bytes):
                            requester_id = requester_id.decode(errors="replace")
                        jobs_list.append({
                            "correlation_id": corr_id,
                            "topic": info["topic"],
                            "requester_id": requester_id,
                            "handler_id": info["handler_id"],
                            "dispatch_time": info["dispatch_time"],
                            "wait_timeout": info["wait_timeout"],
                            "run_timeout": info["run_timeout"],
                        })
                    response = {"jobs": jobs_list}
            elif query == "DEAD_LETTERS":
                records = self._dead_letter_store.replay()
                response = {"dead_letters": records[-100:]}
            elif query == "STATS":
                with self._lock:
                    response = {
                        "event_count": self._event_count,
                        "register_count": self._register_count,
                        "module_count": len(self.modules),
                    }
            else:
                response = {"error": f"Unknown query: {query}"}

            socket.send_multipart([identity, b"", msgpack.packb(response)])
        except Exception as e:
            logger.error("Failed to process admin query: %s", e)
