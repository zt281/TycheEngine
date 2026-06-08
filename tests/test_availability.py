"""Tests for availability reporting and routing."""
import uuid
from unittest.mock import MagicMock, patch

import pytest

from src.tyche.engine import TycheEngine
from src.tyche.message import Message, MessageType, serialize
from src.tyche.types import (
    Endpoint,
    Interface,
    InterfacePattern,
    ModuleInfo,
)


@pytest.fixture
def unstarted_engine(tmp_path):
    """TycheEngine instance WITHOUT started workers. NEVER call .start()."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 17550),
        event_endpoint=Endpoint("127.0.0.1", 17551),
        heartbeat_endpoint=Endpoint("127.0.0.1", 17553),
        data_dir=str(tmp_path / "data"),
    )
    engine._job_router = MagicMock()
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


@pytest.fixture
def handler_module_a():
    """Handler module A."""
    return ModuleInfo(
        module_id="handler_a",
        interfaces=[
            Interface(
                name="handle_compute",
                pattern=InterfacePattern.HANDLE,
                event_type="compute",
            )
        ],
        metadata={},
    )


@pytest.fixture
def handler_module_b():
    """Handler module B."""
    return ModuleInfo(
        module_id="handler_b",
        interfaces=[
            Interface(
                name="handle_compute",
                pattern=InterfacePattern.HANDLE,
                event_type="compute",
            )
        ],
        metadata={},
    )


class TestHeartbeatAvailability:
    """Tests for heartbeat-based availability reporting."""

    def test_heartbeat_includes_availability_dict(self):
        """Heartbeat payload has 'availability' key."""
        from src.tyche.module import TycheModule

        class TestHandler(TycheModule):
            def handle_compute(self, payload):
                return {"result": "ok"}

        with patch("zmq.Context"):
            module = TestHandler(
                engine_endpoint=Endpoint("127.0.0.1", 17550),
                family_name="test_handler",
            )

        # Verify handler_buffers is populated
        assert "compute" in module._handler_buffers

        # Get availability dict
        availability = module._get_handler_availability()
        assert "compute" in availability
        assert availability["compute"] is True  # Not at capacity

    def test_handler_buffer_tracks_usage(self):
        """Buffer current increments/decrements correctly."""
        from src.tyche.module import TycheModule

        class TestHandler(TycheModule):
            def handle_compute(self, payload):
                return {"result": "ok"}

        with patch("zmq.Context"):
            module = TestHandler(
                engine_endpoint=Endpoint("127.0.0.1", 17550),
                family_name="test_handler",
            )

        # Initially current is 0
        assert module._handler_buffers["compute"]["current"] == 0

        # Simulate incrementing (as done in _handle_job_request)
        module._handler_buffers["compute"]["current"] += 1
        assert module._handler_buffers["compute"]["current"] == 1

        # Still has capacity (max_depth=10)
        availability = module._get_handler_availability()
        assert availability["compute"] is True

        # Fill to capacity
        module._handler_buffers["compute"]["current"] = module._handler_buffers["compute"]["max_depth"]
        availability = module._get_handler_availability()
        assert availability["compute"] is False

        # Decrement back
        module._handler_buffers["compute"]["current"] -= 1
        availability = module._get_handler_availability()
        assert availability["compute"] is True


class TestAvailabilityRouting:
    """Tests for availability-based job routing in the unstarted_engine."""

    def test_unavailable_handler_skipped_in_routing(
        self, unstarted_engine, handler_module_a, handler_module_b
    ):
        """Engine skips handlers reporting False availability."""
        unstarted_engine.register_module(handler_module_a)
        unstarted_engine.register_module(handler_module_b)

        # Mark handler_a as unavailable via module_availability
        unstarted_engine._module_availability["handler_a"] = {"compute": False}

        correlation_id = str(uuid.uuid4())
        msg = Message(
            msg_type=MessageType.REQUEST,
            sender="requester",
            event="compute",
            payload={"data": "test"},
            correlation_id=correlation_id,
        )
        identity = b"requester_id"
        topic_frame = b"compute"
        message_frame = serialize(msg)

        unstarted_engine._handle_job_request(identity, topic_frame, message_frame, msg)

        # Job should be routed to handler_b (the only available one)
        info = unstarted_engine._job_tracking[correlation_id]
        assert info["handler_id"] == "handler_b"

    def test_all_handlers_unavailable_waits(
        self, unstarted_engine, handler_module_a, handler_module_b
    ):
        """If all handlers report unavailable, job enters wait state."""
        unstarted_engine.register_module(handler_module_a)
        unstarted_engine.register_module(handler_module_b)

        # Mark both handlers as unavailable
        unstarted_engine._unavailable_handlers["handler_a"] = {"compute"}
        unstarted_engine._unavailable_handlers["handler_b"] = {"compute"}

        correlation_id = str(uuid.uuid4())
        msg = Message(
            msg_type=MessageType.REQUEST,
            sender="requester",
            event="compute",
            payload={"wait_timeout": 5.0, "run_timeout": 60.0},
            correlation_id=correlation_id,
        )
        identity = b"requester_id"
        topic_frame = b"compute"
        message_frame = serialize(msg)

        unstarted_engine._handle_job_request(identity, topic_frame, message_frame, msg)

        # Job should be in wait state (handler_id=None)
        info = unstarted_engine._job_tracking[correlation_id]
        assert info["handler_id"] is None
        assert info["wait_start_time"] is not None

    def test_recovered_handler_receives_jobs(
        self, unstarted_engine, handler_module_a, handler_module_b
    ):
        """After handler becomes available again, jobs are dispatched to it."""
        unstarted_engine.register_module(handler_module_a)
        unstarted_engine.register_module(handler_module_b)

        # Mark both unavailable
        unstarted_engine._unavailable_handlers["handler_a"] = {"compute"}
        unstarted_engine._unavailable_handlers["handler_b"] = {"compute"}

        # Submit a job (will enter wait state)
        correlation_id = str(uuid.uuid4())
        msg = Message(
            msg_type=MessageType.REQUEST,
            sender="requester",
            event="compute",
            payload={"wait_timeout": 30.0, "run_timeout": 60.0},
            correlation_id=correlation_id,
        )
        identity = b"requester_id"
        topic_frame = b"compute"
        message_frame = serialize(msg)

        unstarted_engine._handle_job_request(identity, topic_frame, message_frame, msg)

        # Verify it's waiting
        assert unstarted_engine._job_tracking[correlation_id]["handler_id"] is None

        # Simulate handler_a recovery via heartbeat
        unstarted_engine._recover_handler("handler_a")

        # The waiting job should now be dispatched to handler_a
        assert correlation_id in unstarted_engine._job_tracking
        info = unstarted_engine._job_tracking[correlation_id]
        assert info["handler_id"] == "handler_a"
