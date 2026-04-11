"""Tests for TycheEngine threading implementation."""

import time

import zmq

from tyche.engine import TycheEngine
from tyche.message import Message, deserialize, serialize
from tyche.types import Endpoint, MessageType


def test_engine_has_run_and_stop():
    """Engine has blocking run() and stop() methods."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 22000),
        event_endpoint=Endpoint("127.0.0.1", 22002),
        heartbeat_endpoint=Endpoint("127.0.0.1", 22004),
    )
    assert callable(getattr(engine, "run", None))
    assert callable(getattr(engine, "stop", None))
    assert callable(getattr(engine, "start_nonblocking", None))


def test_engine_registration():
    """Engine can accept module registration via ZMQ."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 22100),
        event_endpoint=Endpoint("127.0.0.1", 22102),
        heartbeat_endpoint=Endpoint("127.0.0.1", 22104),
    )

    engine.start_nonblocking()
    time.sleep(0.3)

    try:
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect("tcp://127.0.0.1:22100")
        socket.setsockopt(zmq.RCVTIMEO, 5000)

        msg = Message(
            msg_type=MessageType.REGISTER,
            sender="test_module",
            event="register",
            payload={
                "module_id": "test_module_001",
                "interfaces": [
                    {
                        "name": "on_data",
                        "pattern": "on_",
                        "event_type": "on_data",
                        "durability": 1,
                    }
                ],
                "metadata": {},
            },
        )

        socket.send(serialize(msg))
        reply_data = socket.recv()
        reply = deserialize(reply_data)

        assert reply.msg_type == MessageType.ACK
        assert reply.payload["status"] == "ok"
        assert reply.payload["module_id"] == "test_module_001"
        # ACK now includes event proxy ports
        assert "event_pub_port" in reply.payload
        assert "event_sub_port" in reply.payload

        assert "test_module_001" in engine.modules

        socket.close()
        context.term()
    finally:
        engine.stop()


def test_engine_registration_registers_interfaces():
    """Registered module interfaces are tracked in the engine registry."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 22200),
        event_endpoint=Endpoint("127.0.0.1", 22202),
        heartbeat_endpoint=Endpoint("127.0.0.1", 22204),
    )

    engine.start_nonblocking()
    time.sleep(0.3)

    try:
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect("tcp://127.0.0.1:22200")
        socket.setsockopt(zmq.RCVTIMEO, 5000)

        msg = Message(
            msg_type=MessageType.REGISTER,
            sender="iface_test",
            event="register",
            payload={
                "module_id": "iface_test",
                "interfaces": [
                    {"name": "on_data", "pattern": "on_", "event_type": "on_data", "durability": 1},
                    {"name": "ack_order", "pattern": "ack_", "event_type": "ack_order", "durability": 2},
                ],
                "metadata": {},
            },
        )

        socket.send(serialize(msg))
        socket.recv()

        assert "on_data" in engine.interfaces
        assert "ack_order" in engine.interfaces
        assert engine.interfaces["on_data"][0][0] == "iface_test"

        socket.close()
        context.term()
    finally:
        engine.stop()
