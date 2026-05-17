"""Tests for handler failure retry logic."""
import time
import uuid
from unittest.mock import MagicMock, patch

import pytest

from tyche.engine import TycheEngine
from tyche.message import Message, MessageType, serialize, deserialize
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
        registration_endpoint=Endpoint("127.0.0.1", 18550),
        event_endpoint=Endpoint("127.0.0.1", 18551),
        heartbeat_endpoint=Endpoint("127.0.0.1", 18553),
        data_dir=str(tmp_path / "data"),
    )
    engine._job_router = MagicMock()
    engine._running = True
    yield engine
    # Cleanup
    engine._running = False
    if engine.context and not engine.context.closed:
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


class TestRetryDispatching:
    """Tests for retry logic after handler timeout."""

    def test_retry_dispatches_to_next_handler(
        self, engine, handler_module_a, handler_module_b
    ):
        """After run_timeout, job goes to another handler."""
        engine.register_module(handler_module_a)
        engine.register_module(handler_module_b)

        # Dispatch job to handler_a
        correlation_id = str(uuid.uuid4())
        msg = Message(
            msg_type=MessageType.REQUEST,
            sender="requester",
            event="compute",
            payload={"wait_timeout": 30.0, "run_timeout": 1.0},
            correlation_id=correlation_id,
        )
        identity = b"requester_id"
        topic_frame = b"compute"
        message_frame = serialize(msg)

        engine._handle_job_request(identity, topic_frame, message_frame, msg)

        # Ensure it was dispatched to one handler first
        info = engine._job_tracking[correlation_id]
        first_handler = info["handler_id"]
        assert first_handler in ("handler_a", "handler_b")

        # Simulate run_timeout on the first handler
        info["dispatch_time"] = time.time() - 2.0
        engine._handle_job_timeout(correlation_id, "run_timeout")

        # Job should be retried on the other handler
        assert correlation_id in engine._job_tracking
        new_info = engine._job_tracking[correlation_id]
        assert new_info["handler_id"] != first_handler
        assert new_info["handler_id"] in ("handler_a", "handler_b")

    def test_retry_skips_timed_out_handler(
        self, engine, handler_module_a, handler_module_b
    ):
        """The failed handler is not chosen again."""
        engine.register_module(handler_module_a)
        engine.register_module(handler_module_b)

        # Force dispatch to handler_a via round-robin index
        engine._job_round_robin["compute"] = 0

        correlation_id = str(uuid.uuid4())
        msg = Message(
            msg_type=MessageType.REQUEST,
            sender="requester",
            event="compute",
            payload={"wait_timeout": 30.0, "run_timeout": 1.0},
            correlation_id=correlation_id,
        )
        identity = b"requester_id"
        topic_frame = b"compute"
        message_frame = serialize(msg)

        engine._handle_job_request(identity, topic_frame, message_frame, msg)
        info = engine._job_tracking[correlation_id]
        first_handler = info["handler_id"]

        # Simulate run_timeout
        info["dispatch_time"] = time.time() - 2.0
        engine._handle_job_timeout(correlation_id, "run_timeout")

        # First handler should be marked unavailable
        assert first_handler in engine._unavailable_handlers
        assert "compute" in engine._unavailable_handlers[first_handler]

        # New handler should not be the timed-out one
        new_info = engine._job_tracking[correlation_id]
        assert new_info["handler_id"] != first_handler

    def test_all_handlers_failed_triggers_wait_timeout(self, engine, handler_module_a):
        """When all handlers fail, wait_timeout kicks in."""
        engine.register_module(handler_module_a)

        correlation_id = str(uuid.uuid4())
        msg = Message(
            msg_type=MessageType.REQUEST,
            sender="requester",
            event="compute",
            payload={"wait_timeout": 1.0, "run_timeout": 1.0},
            correlation_id=correlation_id,
        )
        identity = b"requester_id"
        topic_frame = b"compute"
        message_frame = serialize(msg)

        engine._handle_job_request(identity, topic_frame, message_frame, msg)

        # Simulate run_timeout (only handler available)
        engine._job_tracking[correlation_id]["dispatch_time"] = time.time() - 2.0
        engine._handle_job_timeout(correlation_id, "run_timeout")

        # Since there are no other handlers, job should be put back in wait state
        assert correlation_id in engine._job_tracking
        info = engine._job_tracking[correlation_id]
        assert info["handler_id"] is None  # Waiting for handler

        # Now simulate wait_timeout
        info["wait_start_time"] = time.time() - 2.0
        engine._handle_job_timeout(correlation_id, "wait_timeout")

        # Job should be dead-lettered and error response sent
        assert correlation_id not in engine._job_tracking
        engine._job_router.send_multipart.assert_called()

    def test_handler_recovery_via_heartbeat(
        self, engine, handler_module_a, handler_module_b
    ):
        """Heartbeat from failed handler clears unavailable status."""
        engine.register_module(handler_module_a)
        engine.register_module(handler_module_b)

        # Mark handler_a as unavailable
        engine._unavailable_handlers["handler_a"] = {"compute"}

        # Verify it's unavailable
        assert not engine._is_handler_available("handler_a", "compute")

        # Simulate heartbeat recovery
        engine._recover_handler("handler_a")

        # Handler should be available again
        assert "handler_a" not in engine._unavailable_handlers
        assert engine._is_handler_available("handler_a", "compute")

    def test_retry_preserves_original_message(
        self, engine, handler_module_a, handler_module_b
    ):
        """Retried job has same correlation_id and payload."""
        engine.register_module(handler_module_a)
        engine.register_module(handler_module_b)

        correlation_id = str(uuid.uuid4())
        original_payload = {"wait_timeout": 30.0, "run_timeout": 1.0, "data": "important"}
        msg = Message(
            msg_type=MessageType.REQUEST,
            sender="requester",
            event="compute",
            payload=original_payload,
            correlation_id=correlation_id,
        )
        identity = b"requester_id"
        topic_frame = b"compute"
        message_frame = serialize(msg)

        engine._handle_job_request(identity, topic_frame, message_frame, msg)

        # Simulate run_timeout
        engine._job_tracking[correlation_id]["dispatch_time"] = time.time() - 2.0
        engine._handle_job_timeout(correlation_id, "run_timeout")

        # Verify the retried job still has same message_frame (which contains correlation_id and payload)
        info = engine._job_tracking[correlation_id]
        assert info["message_frame"] == message_frame

        # Verify the send_multipart was called with the original message frame
        retry_call = engine._job_router.send_multipart.call_args_list[-1]
        sent_frames = retry_call[0][0]
        # Frame layout: [handler_id.encode(), b"", topic_frame, message_frame]
        sent_msg = deserialize(sent_frames[3])
        assert sent_msg.correlation_id == correlation_id
        assert sent_msg.payload == original_payload
