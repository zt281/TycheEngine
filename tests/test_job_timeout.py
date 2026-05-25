"""Tests for job wait/run timeout scenarios."""
import time
import uuid
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from src.tyche.engine import TycheEngine
from src.tyche.message import Message, MessageType, serialize, deserialize
from src.tyche.types import (
    Endpoint,
    Interface,
    InterfacePattern,
    BackpressureStrategy,
    DurabilityLevel,
    ModuleInfo,
)


@pytest.fixture
def unstarted_engine(tmp_path):
    """TycheEngine instance WITHOUT started workers. NEVER call .start()."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 16550),
        event_endpoint=Endpoint("127.0.0.1", 16551),
        heartbeat_endpoint=Endpoint("127.0.0.1", 16553),
        data_dir=str(tmp_path / "data"),
    )
    # Mock the job router socket so we can verify sends
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
def handler_interface():
    """Create a HANDLE interface for testing."""
    return Interface(
        name="handle_compute",
        pattern=InterfacePattern.HANDLE,
        event_type="compute",
        durability=DurabilityLevel.ASYNC_FLUSH,
        backpressure=BackpressureStrategy.DROP_OLDEST,
        max_queue_depth=10000,
    )


@pytest.fixture
def handler_module(handler_interface):
    """Create a ModuleInfo with a HANDLE interface."""
    return ModuleInfo(
        module_id="handler_mod_1",
        interfaces=[handler_interface],
        metadata={},
    )


class TestWaitTimeout:
    """Tests for wait_timeout behavior when no handler is available."""

    def test_wait_timeout_triggers_when_no_handler_available(self, unstarted_engine, handler_module):
        """Job with wait_timeout=1.0s and no handler should trigger timeout."""
        # Register handler then mark it unavailable
        unstarted_engine.register_module(handler_module)
        unstarted_engine._unavailable_handlers["handler_mod_1"] = {"compute"}

        # Create a job request
        correlation_id = str(uuid.uuid4())
        msg = Message(
            msg_type=MessageType.REQUEST,
            sender="requester_mod",
            event="compute",
            payload={"wait_timeout": 1.0, "run_timeout": 60.0, "data": "test"},
            correlation_id=correlation_id,
        )
        identity = b"requester_identity"
        topic_frame = b"compute"
        message_frame = serialize(msg)

        # Dispatch request (will enter wait state)
        unstarted_engine._handle_job_request(identity, topic_frame, message_frame, msg)

        # Verify job is in tracking with wait state
        assert correlation_id in unstarted_engine._job_tracking
        info = unstarted_engine._job_tracking[correlation_id]
        assert info["handler_id"] is None
        assert info["wait_timeout"] == 1.0

        # Simulate time passing and trigger timeout
        info["wait_start_time"] = time.time() - 2.0  # 2s ago (exceeds 1s timeout)
        unstarted_engine._handle_job_timeout(correlation_id, "wait_timeout")

        # Job should be removed from tracking
        assert correlation_id not in unstarted_engine._job_tracking

    def test_wait_timeout_sends_error_response(self, unstarted_engine, handler_module):
        """Verify error response contains {"error": "wait_timeout"}."""
        unstarted_engine.register_module(handler_module)
        unstarted_engine._unavailable_handlers["handler_mod_1"] = {"compute"}

        correlation_id = str(uuid.uuid4())
        msg = Message(
            msg_type=MessageType.REQUEST,
            sender="requester_mod",
            event="compute",
            payload={"wait_timeout": 1.0, "run_timeout": 60.0},
            correlation_id=correlation_id,
        )
        identity = b"requester_identity"
        topic_frame = b"compute"
        message_frame = serialize(msg)

        unstarted_engine._handle_job_request(identity, topic_frame, message_frame, msg)

        # Set time to expired
        unstarted_engine._job_tracking[correlation_id]["wait_start_time"] = time.time() - 2.0
        unstarted_engine._handle_job_timeout(correlation_id, "wait_timeout")

        # Verify error message was sent
        unstarted_engine._job_router.send_multipart.assert_called()
        sent_frames = unstarted_engine._job_router.send_multipart.call_args[0][0]
        assert sent_frames[0] == identity
        # Deserialize the response message
        response_msg = deserialize(sent_frames[3])
        assert response_msg.payload["error"] == "wait_timeout"
        assert response_msg.correlation_id == correlation_id

    def test_default_timeouts_used_when_not_specified(self, unstarted_engine, handler_module):
        """Jobs without explicit timeouts use defaults (30s wait, 60s run)."""
        unstarted_engine.register_module(handler_module)

        correlation_id = str(uuid.uuid4())
        msg = Message(
            msg_type=MessageType.REQUEST,
            sender="requester_mod",
            event="compute",
            payload={},  # No explicit timeouts
            correlation_id=correlation_id,
        )
        identity = b"requester_identity"
        topic_frame = b"compute"
        message_frame = serialize(msg)

        unstarted_engine._handle_job_request(identity, topic_frame, message_frame, msg)

        # Verify defaults
        info = unstarted_engine._job_tracking[correlation_id]
        assert info["wait_timeout"] == 30.0
        assert info["run_timeout"] == 60.0


class TestRunTimeout:
    """Tests for run_timeout behavior when handler is unresponsive."""

    def test_run_timeout_triggers_when_handler_unresponsive(self, unstarted_engine, handler_module):
        """Job dispatched but handler doesn't respond within run_timeout."""
        unstarted_engine.register_module(handler_module)

        correlation_id = str(uuid.uuid4())
        msg = Message(
            msg_type=MessageType.REQUEST,
            sender="requester_mod",
            event="compute",
            payload={"wait_timeout": 30.0, "run_timeout": 2.0},
            correlation_id=correlation_id,
        )
        identity = b"requester_identity"
        topic_frame = b"compute"
        message_frame = serialize(msg)

        unstarted_engine._handle_job_request(identity, topic_frame, message_frame, msg)

        # Verify job was dispatched to handler
        info = unstarted_engine._job_tracking[correlation_id]
        assert info["handler_id"] == "handler_mod_1"

        # Simulate time passing (exceed run_timeout)
        info["dispatch_time"] = time.time() - 3.0
        unstarted_engine._handle_job_timeout(correlation_id, "run_timeout")

        # Handler should be marked unavailable
        assert "handler_mod_1" in unstarted_engine._unavailable_handlers
        assert "compute" in unstarted_engine._unavailable_handlers["handler_mod_1"]

    def test_run_timeout_marks_handler_unavailable(self, unstarted_engine, handler_module):
        """After run_timeout, handler should be in _unavailable_handlers."""
        unstarted_engine.register_module(handler_module)

        correlation_id = str(uuid.uuid4())
        msg = Message(
            msg_type=MessageType.REQUEST,
            sender="requester_mod",
            event="compute",
            payload={"wait_timeout": 30.0, "run_timeout": 1.0},
            correlation_id=correlation_id,
        )
        identity = b"requester_identity"
        topic_frame = b"compute"
        message_frame = serialize(msg)

        unstarted_engine._handle_job_request(identity, topic_frame, message_frame, msg)

        # Simulate run_timeout
        unstarted_engine._job_tracking[correlation_id]["dispatch_time"] = time.time() - 2.0
        unstarted_engine._handle_job_timeout(correlation_id, "run_timeout")

        # Verify unavailable status
        assert "handler_mod_1" in unstarted_engine._unavailable_handlers
        assert "compute" in unstarted_engine._unavailable_handlers["handler_mod_1"]

        # Verify _is_handler_available returns False
        assert not unstarted_engine._is_handler_available("handler_mod_1", "compute")
