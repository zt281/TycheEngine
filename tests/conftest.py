"""Shared test fixtures for TycheEngine integration tests."""
import sys
import time
import threading
import uuid
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from tyche.message import Message, serialize, deserialize
from tyche.types import (
    MessageType,
    ModuleInfo,
    Interface,
    InterfacePattern,
    BackpressureStrategy,
    DurabilityLevel,
    Endpoint,
)
from tyche.dead_letter import DeadLetterStore


@pytest.fixture
def tmp_dead_letter_dir(tmp_path):
    """Provide a temporary directory for dead letter storage."""
    return tmp_path / "data"


@pytest.fixture
def dead_letter_store(tmp_dead_letter_dir):
    """Provide a DeadLetterStore using a temporary directory."""
    return DeadLetterStore(base_dir=tmp_dead_letter_dir)


@pytest.fixture
def make_message():
    """Factory fixture to create test Message objects."""
    def _make(
        msg_type=MessageType.EVENT,
        sender="test_module",
        event="test_event",
        payload=None,
        recipient=None,
        correlation_id=None,
        wait_timeout=None,
        run_timeout=None,
    ):
        return Message(
            msg_type=msg_type,
            sender=sender,
            event=event,
            payload=payload or {"data": "test"},
            recipient=recipient,
            correlation_id=correlation_id or str(uuid.uuid4()),
            wait_timeout=wait_timeout,
            run_timeout=run_timeout,
        )
    return _make


@pytest.fixture
def make_interface():
    """Factory fixture to create test Interface objects."""
    def _make(
        name="on_test",
        pattern=InterfacePattern.ON,
        event_type="test",
        durability=DurabilityLevel.ASYNC_FLUSH,
        backpressure=BackpressureStrategy.DROP_OLDEST,
        max_queue_depth=10000,
        wait_timeout=None,
    ):
        return Interface(
            name=name,
            pattern=pattern,
            event_type=event_type,
            durability=durability,
            backpressure=backpressure,
            max_queue_depth=max_queue_depth,
            wait_timeout=wait_timeout,
        )
    return _make


@pytest.fixture
def make_module_info(make_interface):
    """Factory fixture to create test ModuleInfo objects."""
    def _make(
        module_id="test_module",
        interfaces=None,
        metadata=None,
        family_name="",
    ):
        if interfaces is None:
            interfaces = [make_interface()]
        return ModuleInfo(
            module_id=module_id,
            interfaces=interfaces,
            metadata=metadata or {},
            family_name=family_name,
        )
    return _make


@pytest.fixture
def mock_zmq_context():
    """Provide a mocked ZMQ context."""
    with patch("zmq.Context") as mock_ctx:
        mock_socket = MagicMock()
        mock_ctx.return_value.socket.return_value = mock_socket
        yield mock_ctx.return_value, mock_socket


@pytest.fixture
def engine_endpoints():
    """Provide standard engine endpoint configuration for tests."""
    return {
        "registration": Endpoint("127.0.0.1", 15550),
        "event": Endpoint("127.0.0.1", 15551),
        "heartbeat": Endpoint("127.0.0.1", 15553),
    }
