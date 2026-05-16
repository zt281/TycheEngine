"""Tests for backpressure strategy."""
import time
from unittest.mock import MagicMock

import pytest

from tyche.engine import TycheEngine, TopicQueue
from tyche.message import Message, MessageType, serialize
from tyche.types import (
    Endpoint,
    Interface,
    InterfacePattern,
    BackpressureStrategy,
    DurabilityLevel,
    ModuleInfo,
)


@pytest.fixture
def engine(tmp_path):
    """Create a TycheEngine instance for testing."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 19550),
        event_endpoint=Endpoint("127.0.0.1", 19551),
        heartbeat_endpoint=Endpoint("127.0.0.1", 19553),
        data_dir=str(tmp_path / "data"),
    )
    engine._running = True
    return engine


class TestDropOldest:
    """Tests for DROP_OLDEST backpressure strategy."""

    def test_drop_oldest_removes_first_message(self, engine):
        """Queue at capacity drops oldest on new message."""
        topic = "test_topic"
        q = TopicQueue(capacity=3)
        engine._topic_queues[topic] = q
        engine._topic_backpressure[topic] = BackpressureStrategy.DROP_OLDEST
        engine._topic_max_depth[topic] = 3

        # Fill the queue
        for i in range(3):
            frames = [topic.encode(), f"msg_{i}".encode()]
            engine._apply_backpressure(q, topic, frames)

        assert len(q) == 3

        # Add one more — oldest should be dropped
        new_frames = [topic.encode(), b"msg_new"]
        result = engine._apply_backpressure(q, topic, new_frames)

        assert result is True  # Message was enqueued
        assert len(q) == 3  # Still at capacity

        # Verify oldest was removed: first item should be msg_1, not msg_0
        item = q.get()
        assert item is not None
        _, frames = item
        assert frames[1] == b"msg_1"

    def test_drop_oldest_increments_dropped_count(self, engine):
        """DROP_OLDEST increments the dropped counter."""
        topic = "test_topic"
        q = TopicQueue(capacity=2)
        engine._topic_queues[topic] = q
        engine._topic_backpressure[topic] = BackpressureStrategy.DROP_OLDEST
        engine._topic_max_depth[topic] = 2

        # Fill queue
        for i in range(2):
            engine._apply_backpressure(q, topic, [topic.encode(), f"msg_{i}".encode()])

        assert q.dropped == 0

        # Trigger backpressure
        engine._apply_backpressure(q, topic, [topic.encode(), b"overflow"])

        assert q.dropped == 1


class TestDropNewest:
    """Tests for DROP_NEWEST backpressure strategy."""

    def test_drop_newest_discards_new_message(self, engine):
        """Queue at capacity discards incoming message."""
        topic = "test_topic"
        q = TopicQueue(capacity=3)
        engine._topic_queues[topic] = q
        engine._topic_backpressure[topic] = BackpressureStrategy.DROP_NEWEST
        engine._topic_max_depth[topic] = 3

        # Fill the queue
        for i in range(3):
            frames = [topic.encode(), f"msg_{i}".encode()]
            engine._apply_backpressure(q, topic, frames)

        assert len(q) == 3

        # Try to add one more — should be discarded
        new_frames = [topic.encode(), b"msg_new"]
        result = engine._apply_backpressure(q, topic, new_frames)

        assert result is False  # Message was NOT enqueued
        assert len(q) == 3  # Still at capacity

        # Verify the queue contents are unchanged (first item is msg_0)
        item = q.get()
        assert item is not None
        _, frames = item
        assert frames[1] == b"msg_0"


class TestBlockProducer:
    """Tests for BLOCK_PRODUCER backpressure strategy."""

    def test_block_producer_drops_newest_with_warning(self, engine):
        """BLOCK_PRODUCER gracefully degrades to drop newest."""
        topic = "test_topic"
        q = TopicQueue(capacity=2)
        engine._topic_queues[topic] = q
        engine._topic_backpressure[topic] = BackpressureStrategy.BLOCK_PRODUCER
        engine._topic_max_depth[topic] = 2

        # Fill the queue
        for i in range(2):
            engine._apply_backpressure(q, topic, [topic.encode(), f"msg_{i}".encode()])

        # Try to add one more — should be dropped (graceful degradation)
        result = engine._apply_backpressure(q, topic, [topic.encode(), b"overflow"])

        assert result is False  # Dropped (like DROP_NEWEST)
        assert len(q) == 2
        assert q.dropped == 1


class TestPerTopicConfiguration:
    """Tests for per-topic backpressure configuration."""

    def test_per_topic_strategy_configuration(self, engine):
        """Different topics can have different strategies."""
        # Register module with DROP_OLDEST interface
        module_a = ModuleInfo(
            module_id="mod_a",
            interfaces=[
                Interface(
                    name="on_fast",
                    pattern=InterfacePattern.ON,
                    event_type="fast_topic",
                    backpressure=BackpressureStrategy.DROP_OLDEST,
                    max_queue_depth=100,
                )
            ],
            metadata={},
        )
        engine.register_module(module_a)

        # Register module with DROP_NEWEST interface
        module_b = ModuleInfo(
            module_id="mod_b",
            interfaces=[
                Interface(
                    name="on_slow",
                    pattern=InterfacePattern.ON,
                    event_type="slow_topic",
                    backpressure=BackpressureStrategy.DROP_NEWEST,
                    max_queue_depth=50,
                )
            ],
            metadata={},
        )
        engine.register_module(module_b)

        # Verify per-topic strategies
        assert engine._topic_backpressure["fast_topic"] == BackpressureStrategy.DROP_OLDEST
        assert engine._topic_backpressure["slow_topic"] == BackpressureStrategy.DROP_NEWEST

    def test_per_topic_max_depth(self, engine):
        """Different topics can have different max queue depths."""
        module = ModuleInfo(
            module_id="mod_multi",
            interfaces=[
                Interface(
                    name="on_high_vol",
                    pattern=InterfacePattern.ON,
                    event_type="high_vol",
                    max_queue_depth=50000,
                ),
                Interface(
                    name="on_low_vol",
                    pattern=InterfacePattern.ON,
                    event_type="low_vol",
                    max_queue_depth=100,
                ),
            ],
            metadata={},
        )
        engine.register_module(module)

        assert engine._topic_max_depth["high_vol"] == 50000
        assert engine._topic_max_depth["low_vol"] == 100

        # Verify queues were created with correct capacities
        assert engine._topic_queues["high_vol"].capacity == 50000
        assert engine._topic_queues["low_vol"].capacity == 100
