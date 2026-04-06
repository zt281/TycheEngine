"""Tests for message serialization."""
from decimal import Decimal

from tyche.message import Envelope, Message, deserialize, serialize
from tyche.types import DurabilityLevel, MessageType


def test_message_creation():
    """Message can be created with required fields."""
    msg = Message(
        msg_type=MessageType.EVENT,
        sender="zeus3f7a9c",
        event="on_data",
        payload={"key": "value"}
    )
    assert msg.msg_type == MessageType.EVENT
    assert msg.sender == "zeus3f7a9c"
    assert msg.event == "on_data"
    assert msg.payload == {"key": "value"}


def test_message_serialization_roundtrip():
    """Message survives serialize/deserialize roundtrip."""
    original = Message(
        msg_type=MessageType.EVENT,
        sender="zeus3f7a9c",
        recipient="hera2b8d4e",
        event="on_data",
        payload={"count": 42, "name": "test"},
        durability=DurabilityLevel.ASYNC_FLUSH
    )

    serialized = serialize(original)
    restored = deserialize(serialized)

    assert restored.msg_type == original.msg_type
    assert restored.sender == original.sender
    assert restored.recipient == original.recipient
    assert restored.event == original.event
    assert restored.payload == original.payload
    assert restored.durability == original.durability


def test_decimal_precision_preserved():
    """Decimal values maintain precision through serialization."""
    original = Message(
        msg_type=MessageType.EVENT,
        sender="zeus3f7a9c",
        event="on_price",
        payload={"price": Decimal("123.456789")}
    )

    serialized = serialize(original)
    restored = deserialize(serialized)

    assert restored.payload["price"] == Decimal("123.456789")


def test_envelope_creation():
    """Envelope wraps message with routing info."""
    msg = Message(
        msg_type=MessageType.EVENT,
        sender="zeus3f7a9c",
        event="on_data",
        payload={}
    )

    envelope = Envelope(
        identity=b"worker001",
        message=msg,
        routing_stack=[]
    )

    assert envelope.identity == b"worker001"
    assert envelope.message.sender == "zeus3f7a9c"


def test_serialize_to_bytes():
    """serialize() returns bytes."""
    msg = Message(
        msg_type=MessageType.HEARTBEAT,
        sender="zeus3f7a9c",
        event="heartbeat",
        payload={}
    )

    result = serialize(msg)
    assert isinstance(result, bytes)
    assert len(result) > 0
