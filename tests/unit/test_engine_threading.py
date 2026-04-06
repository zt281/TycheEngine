"""Tests for TycheEngine threading implementation."""

import threading
import time

import pytest
import zmq

from tyche.engine import TycheEngine
from tyche.types import Endpoint, MessageType
from tyche.message import Message, serialize


def test_engine_has_run_method():
    """Engine has a blocking run() method."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 15555),
        event_endpoint=Endpoint("127.0.0.1", 15556),
        heartbeat_endpoint=Endpoint("127.0.0.1", 15558)
    )

    assert hasattr(engine, "run")
    assert hasattr(engine, "stop")


def test_engine_registration():
    """Engine can accept module registration via ZMQ."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 15565),
        event_endpoint=Endpoint("127.0.0.1", 15566),
        heartbeat_endpoint=Endpoint("127.0.0.1", 15568)
    )

    # Start engine without blocking
    engine.start_nonblocking()
    time.sleep(0.3)

    try:
        # Create a client socket to register
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect("tcp://127.0.0.1:15565")
        socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second timeout

        # Send registration
        msg = Message(
            msg_type=MessageType.REGISTER,
            sender="test_module",
            event="register",
            payload={
                "module_id": "test_module_001",
                "interfaces": [
                    {"name": "on_data", "pattern": "on_", "event_type": "on_data", "durability": 1}
                ],
                "metadata": {}
            }
        )

        socket.send(serialize(msg))
        reply_data = socket.recv()

        from tyche.message import deserialize
        reply = deserialize(reply_data)

        assert reply.msg_type == MessageType.ACK
        assert reply.payload["status"] == "ok"
        assert reply.payload["module_id"] == "test_module_001"

        # Verify module is registered
        assert "test_module_001" in engine.modules

        socket.close()
        context.term()

    finally:
        engine.stop()


def test_engine_has_stop_event():
    """Engine has stop event for thread coordination."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 15575),
        event_endpoint=Endpoint("127.0.0.1", 15576),
        heartbeat_endpoint=Endpoint("127.0.0.1", 15578)
    )

    assert hasattr(engine, "_stop_event")
