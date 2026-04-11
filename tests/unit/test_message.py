"""Tests for message serialization and deserialization."""

from decimal import Decimal

from tyche.message import (
    Envelope,
    Message,
    deserialize,
    deserialize_envelope,
    serialize,
    serialize_envelope,
)
from tyche.types import DurabilityLevel, MessageType


def test_message_creation():
    """Message stores all fields correctly."""
    msg = Message(
        msg_type=MessageType.EVENT,
        sender="zeus123456",
        event="on_data",
        payload={"value": 42},
    )
    assert msg.msg_type == MessageType.EVENT
    assert msg.sender == "zeus123456"
    assert msg.event == "on_data"
    assert msg.payload == {"value": 42}
    assert msg.recipient is None
    assert msg.timestamp is None
    assert msg.correlation_id is None


def test_message_serialization_roundtrip():
    """Message survives serialize -> deserialize roundtrip."""
    original = Message(
        msg_type=MessageType.COMMAND,
        sender="athena456",
        event="ack_order",
        payload={"order_id": "A123", "quantity": 100},
        recipient="hermes789",
        durability=DurabilityLevel.SYNC_FLUSH,
        timestamp=1234567890.123,
        correlation_id="corr-001",
    )

    data = serialize(original)
    restored = deserialize(data)

    assert restored.msg_type == original.msg_type
    assert restored.sender == original.sender
    assert restored.event == original.event
    assert restored.payload == original.payload
    assert restored.recipient == original.recipient
    assert restored.durability == original.durability
    assert restored.timestamp == original.timestamp
    assert restored.correlation_id == original.correlation_id


def test_roundtrip_with_none_optional_fields():
    """Roundtrip preserves None values for optional fields."""
    original = Message(
        msg_type=MessageType.EVENT,
        sender="test",
        event="evt",
        payload={},
        recipient=None,
        timestamp=None,
        correlation_id=None,
    )
    restored = deserialize(serialize(original))

    assert restored.recipient is None
    assert restored.timestamp is None
    assert restored.correlation_id is None


def test_decimal_precision_preserved():
    """Decimal precision is preserved through serialization."""
    msg = Message(
        msg_type=MessageType.EVENT,
        sender="test",
        event="price",
        payload={"price": Decimal("123.456789012345")},
    )

    data = serialize(msg)
    restored = deserialize(data)

    assert isinstance(restored.payload["price"], Decimal)
    assert restored.payload["price"] == Decimal("123.456789012345")


def test_serialize_returns_bytes():
    """serialize() returns non-empty bytes."""
    msg = Message(
        msg_type=MessageType.HEARTBEAT,
        sender="test",
        event="heartbeat",
        payload={},
    )
    data = serialize(msg)
    assert isinstance(data, bytes)
    assert len(data) > 0


# ── Envelope tests ────────────────────────────────────────────


def test_envelope_creation():
    """Envelope stores identity and message."""
    msg = Message(
        msg_type=MessageType.EVENT,
        sender="test",
        event="evt",
        payload={},
    )
    env = Envelope(identity=b"client1", message=msg)
    assert env.identity == b"client1"
    assert env.message is msg
    assert env.routing_stack == []


def test_envelope_serialize_roundtrip_simple():
    """Envelope without routing stack survives serialize/deserialize."""
    msg = Message(
        msg_type=MessageType.EVENT,
        sender="sender1",
        event="on_data",
        payload={"key": "value"},
    )
    env = Envelope(identity=b"mod_001", message=msg)

    frames = serialize_envelope(env)
    restored = deserialize_envelope(frames)

    assert restored.identity == b"mod_001"
    assert restored.message.sender == "sender1"
    assert restored.message.payload == {"key": "value"}
    assert restored.routing_stack == []


def test_envelope_serialize_roundtrip_with_routing():
    """Envelope with routing stack survives serialize/deserialize."""
    msg = Message(
        msg_type=MessageType.COMMAND,
        sender="a",
        event="ack_x",
        payload={"x": 1},
    )
    env = Envelope(
        identity=b"target",
        message=msg,
        routing_stack=[b"hop1", b"hop2"],
    )

    frames = serialize_envelope(env)
    restored = deserialize_envelope(frames)

    assert restored.routing_stack == [b"hop1", b"hop2"]
    assert restored.identity == b"target"
    assert restored.message.event == "ack_x"
