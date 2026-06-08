"""Tests for backpressure strategy."""

import pytest

from src.tyche.engine import TopicQueue, TycheEngine
from src.tyche.types import (
    BackpressureStrategy,
    Endpoint,
    Interface,
    InterfacePattern,
    ModuleInfo,
)


@pytest.fixture
def unstarted_engine(tmp_path):
    """TycheEngine instance WITHOUT started workers. NEVER call .start()."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 19550),
        event_endpoint=Endpoint("127.0.0.1", 19551),
        heartbeat_endpoint=Endpoint("127.0.0.1", 19553),
        data_dir=str(tmp_path / "data"),
    )
    engine._running = True
    yield engine
    # Robust cleanup: stop() joins daemon threads even if start() was never called
    try:
        engine.stop()
    except Exception:
        pass
    engine._running = False
    if engine.context is not None and not engine.context.closed:
        engine.context.destroy(linger=0)


class TestDropOldest:
    """Tests for DROP_OLDEST backpressure strategy."""

    def test_drop_oldest_removes_first_message(self, unstarted_engine):
        """Queue at capacity drops oldest on new message."""
        topic = "test_topic"
        q = TopicQueue(capacity=3)
        unstarted_engine._topic_queues[topic] = q
        unstarted_engine._topic_backpressure[topic] = BackpressureStrategy.DROP_OLDEST
        unstarted_engine._topic_max_depth[topic] = 3

        # Fill the queue
        for i in range(3):
            frames = [topic.encode(), f"msg_{i}".encode()]
            unstarted_engine._apply_backpressure(q, topic, frames)

        assert len(q) == 3

        # Add one more — oldest should be dropped
        new_frames = [topic.encode(), b"msg_new"]
        result = unstarted_engine._apply_backpressure(q, topic, new_frames)

        assert result is True  # Message was enqueued
        assert len(q) == 3  # Still at capacity

        # Verify oldest was removed: first item should be msg_1, not msg_0
        item = q.get()
        assert item is not None
        _, frames = item
        assert frames[1] == b"msg_1"

    def test_drop_oldest_increments_dropped_count(self, unstarted_engine):
        """DROP_OLDEST increments the dropped counter."""
        topic = "test_topic"
        q = TopicQueue(capacity=2)
        unstarted_engine._topic_queues[topic] = q
        unstarted_engine._topic_backpressure[topic] = BackpressureStrategy.DROP_OLDEST
        unstarted_engine._topic_max_depth[topic] = 2

        # Fill queue
        for i in range(2):
            unstarted_engine._apply_backpressure(q, topic, [topic.encode(), f"msg_{i}".encode()])

        assert q.dropped == 0

        # Trigger backpressure
        unstarted_engine._apply_backpressure(q, topic, [topic.encode(), b"overflow"])

        assert q.dropped == 1


class TestDropNewest:
    """Tests for DROP_NEWEST backpressure strategy."""

    def test_drop_newest_discards_new_message(self, unstarted_engine):
        """Queue at capacity discards incoming message."""
        topic = "test_topic"
        q = TopicQueue(capacity=3)
        unstarted_engine._topic_queues[topic] = q
        unstarted_engine._topic_backpressure[topic] = BackpressureStrategy.DROP_NEWEST
        unstarted_engine._topic_max_depth[topic] = 3

        # Fill the queue
        for i in range(3):
            frames = [topic.encode(), f"msg_{i}".encode()]
            unstarted_engine._apply_backpressure(q, topic, frames)

        assert len(q) == 3

        # Try to add one more — should be discarded
        new_frames = [topic.encode(), b"msg_new"]
        result = unstarted_engine._apply_backpressure(q, topic, new_frames)

        assert result is False  # Message was NOT enqueued
        assert len(q) == 3  # Still at capacity

        # Verify the queue contents are unchanged (first item is msg_0)
        item = q.get()
        assert item is not None
        _, frames = item
        assert frames[1] == b"msg_0"


class TestBlockProducer:
    """Tests for BLOCK_PRODUCER backpressure strategy."""

    def test_block_producer_drops_newest_with_warning(self, unstarted_engine):
        """BLOCK_PRODUCER gracefully degrades to drop newest."""
        topic = "test_topic"
        q = TopicQueue(capacity=2)
        unstarted_engine._topic_queues[topic] = q
        unstarted_engine._topic_backpressure[topic] = BackpressureStrategy.BLOCK_PRODUCER
        unstarted_engine._topic_max_depth[topic] = 2

        # Fill the queue
        for i in range(2):
            unstarted_engine._apply_backpressure(q, topic, [topic.encode(), f"msg_{i}".encode()])

        # Try to add one more — should be dropped (graceful degradation)
        result = unstarted_engine._apply_backpressure(q, topic, [topic.encode(), b"overflow"])

        assert result is False  # Dropped (like DROP_NEWEST)
        assert len(q) == 2
        assert q.dropped == 1


class TestPerTopicConfiguration:
    """Tests for per-topic backpressure configuration."""

    def test_per_topic_strategy_configuration(self, unstarted_engine):
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
        unstarted_engine.register_module(module_a)

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
        unstarted_engine.register_module(module_b)

        # Verify per-topic strategies
        assert unstarted_engine._topic_backpressure["fast_topic"] == BackpressureStrategy.DROP_OLDEST
        assert unstarted_engine._topic_backpressure["slow_topic"] == BackpressureStrategy.DROP_NEWEST

    def test_per_topic_max_depth(self, unstarted_engine):
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
        unstarted_engine.register_module(module)

        assert unstarted_engine._topic_max_depth["high_vol"] == 50000
        assert unstarted_engine._topic_max_depth["low_vol"] == 100

        # Verify queues were created with correct capacities
        assert unstarted_engine._topic_queues["high_vol"].capacity == 50000
        assert unstarted_engine._topic_queues["low_vol"].capacity == 100
