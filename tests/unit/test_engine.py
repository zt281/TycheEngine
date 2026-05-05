"""Tests for TycheEngine."""
from unittest.mock import Mock

import msgpack

from tyche.engine import TopicQueue, TrackedQueue, TycheEngine
from tyche.types import (
    DurabilityLevel,
    Endpoint,
    Interface,
    InterfacePattern,
    ModuleInfo,
)


def _build_engine() -> TycheEngine:
    return TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 5555),
        event_endpoint=Endpoint("127.0.0.1", 5556),
        heartbeat_endpoint=Endpoint("127.0.0.1", 5557),
    )


def _admin_query(engine: TycheEngine, query: str) -> dict:
    socket = Mock()
    frames = [b"client", b"", msgpack.packb(query)]
    engine._process_admin_query(socket, frames)
    assert socket.send_multipart.called
    sent = socket.send_multipart.call_args[0][0]
    assert sent[0] == b"client"
    return msgpack.unpackb(sent[2], raw=False)


def test_engine_init():
    """Engine initializes with endpoints."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 5555),
        event_endpoint=Endpoint("127.0.0.1", 5556),
        heartbeat_endpoint=Endpoint("127.0.0.1", 5557)
    )
    assert engine.registration_endpoint.port == 5555


def test_engine_module_registry():
    """Engine can register modules."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 5555),
        event_endpoint=Endpoint("127.0.0.1", 5556),
        heartbeat_endpoint=Endpoint("127.0.0.1", 5557),
    )

    module_info = Mock()
    module_info.module_id = "zeus3f7a9c"
    module_info.interfaces = []

    engine.register_module(module_info)

    assert "zeus3f7a9c" in engine.modules


def test_engine_unregister_module():
    """Engine can unregister modules."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 5555),
        event_endpoint=Endpoint("127.0.0.1", 5556),
        heartbeat_endpoint=Endpoint("127.0.0.1", 5557),
    )

    module_info = Mock()
    module_info.module_id = "zeus3f7a9c"
    module_info.interfaces = []

    engine.register_module(module_info)
    engine.unregister_module("zeus3f7a9c")

    assert "zeus3f7a9c" not in engine.modules


def test_admin_status_includes_heartbeat_queue_size():
    """STATUS response exposes heartbeat queue size under other_queue_sizes."""
    engine = _build_engine()
    response = _admin_query(engine, "STATUS")
    assert "other_queue_sizes" in response
    assert response["other_queue_sizes"]["heartbeat"] == 0


def test_admin_modules_includes_last_seen():
    """MODULES response exposes last_seen for each module."""
    engine = _build_engine()
    module_info = ModuleInfo(
        module_id="zeus3f7a9c",
        endpoint=Endpoint("127.0.0.1", 0),
        interfaces=[
            Interface(
                name="ping",
                pattern=InterfacePattern.ON,
                event_type="ping",
                durability=DurabilityLevel.BEST_EFFORT,
            )
        ],
        metadata={},
    )
    engine.register_module(module_info)

    response = _admin_query(engine, "MODULES")
    assert response["modules"], "expected at least one module"
    entry = response["modules"][0]
    assert entry["module_id"] == "zeus3f7a9c"
    assert "last_seen" in entry
    assert entry["last_seen"] > 0.0


def test_topic_queue_tracks_processed_and_dropped():
    """TopicQueue increments processed on get and dropped on overflow."""
    q = TopicQueue(capacity=2)
    assert q.put([b"a"]) is True
    assert q.put([b"b"]) is True
    assert q.put([b"c"]) is False  # dropped
    assert q.dropped == 1
    assert len(q) == 2

    item = q.get()
    assert item == [b"b"]  # LIFO
    assert q.processed == 1
    assert q.get() == [b"a"]
    assert q.processed == 2
    assert q.get() is None


def test_tracked_queue_tracks_processed_and_dropped():
    """TrackedQueue increments processed on get and dropped on overflow."""
    q = TrackedQueue(maxsize=2)
    q.put([b"a"])
    q.put([b"b"])
    q.put([b"c"])  # should be dropped
    assert q.dropped == 1
    assert q.qsize() == 2

    item = q.get()
    assert item == [b"a"]
    assert q.processed == 1
    assert q.get() == [b"b"]
    assert q.processed == 2


def test_admin_queues_reflects_realtime_stats():
    """QUEUES response reflects processed and dropped counts after operations."""
    engine = _build_engine()
    engine._topic_queues["orders"] = TopicQueue(capacity=1)
    engine._topic_queues["orders"].put([b"orders", b"msg1"])
    engine._topic_queues["orders"].put([b"orders", b"msg2"])  # dropped
    engine._topic_queues["orders"].get()  # processed

    response = _admin_query(engine, "QUEUES")
    queues = {q["name"]: q for q in response["queues"]}

    orders_q = queues["orders"]
    assert orders_q["size"] == 0
    assert orders_q["capacity"] == 1
    assert orders_q["processed"] == 1
    assert orders_q["dropped"] == 1


def test_admin_queues_returns_array():
    """QUEUES response returns list with topic, typed, and heartbeat queues."""
    engine = _build_engine()
    # Seed a topic queue
    engine._topic_queues["test.topic"] = TopicQueue(capacity=500)
    engine._topic_queues["test.topic"].put([b"test.topic", b"frame"])

    response = _admin_query(engine, "QUEUES")
    assert "queues" in response
    queues = response["queues"]
    assert isinstance(queues, list)

    names = {q["name"] for q in queues}
    assert "test.topic" in names
    assert "register" in names
    assert "ack" in names
    assert "heartbeat" in names

    topic_entry = next(q for q in queues if q["name"] == "test.topic")
    assert topic_entry["size"] == 1
    assert topic_entry["capacity"] == 500
    assert topic_entry["processed"] == 0
    assert topic_entry["dropped"] == 0
