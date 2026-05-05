"""TycheEngine - Central broker using threads for multi-process support."""

import logging
import queue
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

import msgpack
import zmq

from tyche.heartbeat import HeartbeatManager
from tyche.message import Message, deserialize, serialize
from tyche.types import (
    ADMIN_PORT_DEFAULT,
    HEARTBEAT_INTERVAL,
    DurabilityLevel,
    Endpoint,
    Interface,
    InterfacePattern,
    MessageType,
    ModuleInfo,
)

logger = logging.getLogger(__name__)


class TopicQueue:
    """Thread-safe queue with capacity, processed, and dropped stats."""

    def __init__(self, capacity: Optional[int] = None):
        self._items: List[List[bytes]] = []
        self.capacity = capacity
        self.processed = 0
        self.dropped = 0
        self._lock = threading.Lock()

    def put(self, item: List[bytes]) -> bool:
        with self._lock:
            if self.capacity is not None and len(self._items) >= self.capacity:
                self.dropped += 1
                return False
            self._items.append(item)
            return True

    def get(self) -> Optional[List[bytes]]:
        with self._lock:
            if not self._items:
                return None
            self.processed += 1
            return self._items.pop()

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
        ack_endpoint: Optional[Endpoint] = None,
        heartbeat_receive_endpoint: Optional[Endpoint] = None,
        admin_endpoint: str = f"tcp://*:{ADMIN_PORT_DEFAULT}",
        queue_capacity: Optional[int] = 10000,
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
        self._admin_endpoint = admin_endpoint

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

        # Typed message queues for non-event paths
        _maxsize = queue_capacity if queue_capacity else 0
        self._message_queues: Dict[MessageType, TrackedQueue] = {
            MessageType.REGISTER: TrackedQueue(maxsize=_maxsize),
            MessageType.RESPONSE: TrackedQueue(maxsize=_maxsize),
            MessageType.ACK: TrackedQueue(maxsize=_maxsize),
        }
        # Thread-safe queue for forwarding module heartbeats to PUB socket
        self._heartbeat_queue: TrackedQueue = TrackedQueue(maxsize=_maxsize)

        # Wakeup queue for the egress worker — enqueue a sentinel whenever
        # a message is added to a topic queue so the egress worker blocks
        # instead of spinning.
        self._egress_wakeup: queue.Queue[None] = queue.Queue()

        # Request-response correlation mapping: correlation_id -> ROUTER identity
        self._ack_correlations: Dict[str, bytes] = {}
        self._ack_lock = threading.Lock()

        # Event proxy sockets (shared between proxy ingress and egress workers)
        self._xpub_socket: Optional[zmq.Socket] = None
        self._xsub_socket: Optional[zmq.Socket] = None
        self._xpub_lock = threading.Lock()

        # Registration socket (shared between ingress and egress workers)
        self._registration_socket: Optional[zmq.Socket] = None
        self._registration_lock = threading.Lock()

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
                target=self._registration_egress_worker,
                name="registration_egress",
                daemon=True,
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
            threading.Thread(
                target=self._event_egress_worker,
                name="event_egress",
                daemon=True,
            ),
            threading.Thread(
                target=self._admin_worker, name="admin", daemon=True
            ),
            threading.Thread(
                target=self._ack_worker, name="ack", daemon=True
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
                        "ack_port": self.ack_endpoint.port,
                    },
                )
                if self._registration_socket is not None:
                    with self._registration_lock:
                        self._registration_socket.send_multipart(
                            [identity, b"", serialize(ack)]
                        )
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
        """Register a module and its interfaces (thread-safe).

        Creates a dedicated queue for every interface/topic declared by the
        module, enabling per-topic routing and backpressure in the future.
        """
        with self._lock:
            self.modules[module_info.module_id] = module_info

            for interface in module_info.interfaces:
                topic = interface.name
                if topic not in self.interfaces:
                    self.interfaces[topic] = []
                self.interfaces[topic].append(
                    (module_info.module_id, interface)
                )
                queue_key = f"{interface.event_type}:{interface.pattern.value}"
                self._topic_event_map[topic] = queue_key
                with self._topic_queues_lock:
                    if queue_key not in self._topic_queues:
                        self._topic_queues[queue_key] = TopicQueue(
                            capacity=self._queue_capacity
                        )
                        logger.info("Created topic queue: %s", queue_key)

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

    def _ack_worker(self) -> None:
        """Handle request-response correlation via ROUTER socket.

        Modules send requests via DEALER; we record correlation_id -> identity,
        enqueue the request for the event egress worker to broadcast, and
        route responses back to the original caller.
        """
        assert self.context is not None
        router = self.context.socket(zmq.ROUTER)
        router.setsockopt(zmq.LINGER, 0)
        try:
            router.bind(str(self.ack_endpoint))
            router.setsockopt(zmq.RCVTIMEO, 100)

            while self._running:
                try:
                    frames = router.recv_multipart()
                    if len(frames) < 2:
                        continue

                    identity = frames[0]
                    msg_data = (
                        frames[2]
                        if len(frames) >= 3 and frames[1] == b""
                        else frames[1]
                    )
                    msg = deserialize(msg_data)

                    if msg.msg_type == MessageType.COMMAND:
                        correlation_id = msg.payload.get("_correlation_id")
                        if correlation_id:
                            with self._ack_lock:
                                self._ack_correlations[correlation_id] = identity
                        # Enqueue to the dedicated topic queue
                        topic = msg.event
                        queue_key = self._topic_event_map.get(topic, topic)
                        with self._topic_queues_lock:
                            q = self._topic_queues.get(queue_key)
                            if q is None:
                                q = TopicQueue(capacity=self._queue_capacity)
                                self._topic_queues[queue_key] = q
                            q.put([msg.event.encode(), serialize(msg)])
                        self._egress_wakeup.put(None)
                    elif msg.msg_type == MessageType.RESPONSE:
                        correlation_id = msg.payload.get("_correlation_id")
                        if correlation_id is not None:
                            with self._ack_lock:
                                caller_identity = self._ack_correlations.pop(
                                    str(correlation_id), None
                                )
                            if caller_identity is not None:
                                router.send_multipart(
                                    [caller_identity, b"", serialize(msg)]
                                )
                except zmq.error.Again:
                    continue
                except Exception as e:
                    if self._running:
                        logger.error("ACK worker error: %s", e)
        except Exception as e:
            logger.error("ACK worker failed to start: %s", e)
        finally:
            router.close()

    def _event_proxy_worker(self) -> None:
        """XSUB/XPUB proxy for event distribution.

        Modules publish events to the XSUB socket.
        Modules subscribe to events via the XPUB socket.
        The proxy forwards between them directly for minimum latency.

        Per-topic queues are maintained for ACK messages (routed by
        _ack_worker) and future backpressure / persistence features,
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
                    # Batch drain — amortise poll() overhead over many messages
                    batch_count = 0
                    while self._running:
                        try:
                            frames = self._xsub_socket.recv_multipart(zmq.NOBLOCK)
                            topic = frames[0].decode()
                            queue_key = self._topic_event_map.get(topic, topic)
                            with self._topic_queues_lock:
                                q = self._topic_queues.get(queue_key)
                                if q is None:
                                    q = TopicQueue(capacity=self._queue_capacity)
                                    self._topic_queues[queue_key] = q
                                q.put(frames)
                            self._egress_wakeup.put(None)
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

    def _enqueue_from_xsub(self, frames: List[bytes]) -> None:
        """Route XSUB data to the dedicated topic queue.

        Topic is taken from frame[0]; queue is created on-demand if a module
        has not yet registered for this topic (dynamic subscription).
        Fast path avoids the dict lock when the queue already exists.
        """
        if len(frames) < 2:
            return
        topic = frames[0].decode()
        queue_key = self._topic_event_map.get(topic, topic)
        # Fast path: lock-free lookup for existing queues (hot path)
        q = self._topic_queues.get(queue_key)
        if q is not None:
            q.put(frames)
            return
        # Slow path: create queue under lock
        with self._topic_queues_lock:
            q = self._topic_queues.get(queue_key)
            if q is None:
                q = TopicQueue(capacity=self._queue_capacity)
                self._topic_queues[queue_key] = q
                logger.debug("Created dynamic topic queue: %s", queue_key)
            q.put(frames)
        self._egress_wakeup.put(None)

    def _event_egress_worker(self) -> None:
        """Background drainer for ACK messages and catch-up under backpressure.

        Blocks on a wakeup queue so it does not spin.  The proxy worker
        handles the bulk of event forwarding inline; this worker only
        activates when ACK messages (enqueued by _ack_worker) need delivery.
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
                    frames = q.get()
                    if frames is None:
                        break

                    if self._xpub_socket is not None:
                        try:
                            with self._xpub_lock:
                                self._xpub_socket.send_multipart(frames)
                            with self._lock:
                                self._event_count += 1
                        except Exception as e:
                            if self._running:
                                logger.error("Event egress error: %s", e)
                            break

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
                                # Forward module heartbeat to PUB socket via queue
                                self._heartbeat_queue.put(msg)
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

    def _admin_worker(self) -> None:
        """Admin ROUTER socket for querying engine state."""
        assert self.context is not None
        socket = self.context.socket(zmq.ROUTER)
        socket.setsockopt(zmq.LINGER, 0)
        try:
            socket.bind(self._admin_endpoint)
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
                        "heartbeat_queue_size": self._heartbeat_queue.qsize(),
                        "other_queue_sizes": {
                            "register": self._message_queues[MessageType.REGISTER].qsize(),
                            "response": self._message_queues[MessageType.RESPONSE].qsize(),
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
