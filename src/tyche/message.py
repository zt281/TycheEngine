"""Message serialization using MessagePack."""

import enum
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Dict, List, Optional

import msgpack

from tyche.types import DurabilityLevel, MessageType


@dataclass
class Message:
    """Application message structure.

    Attributes:
        msg_type: Type of message (event, command, heartbeat, etc.)
        sender: Module ID of sender
        event: Event name/interface being invoked
        payload: Message data payload
        recipient: Optional target module ID
        durability: Persistence level for this message
        timestamp: Optional creation timestamp
        correlation_id: Optional ID for request/response correlation
    """
    msg_type: MessageType
    sender: str
    event: str
    payload: Dict[str, Any]
    recipient: Optional[str] = None
    durability: DurabilityLevel = DurabilityLevel.ASYNC_FLUSH
    timestamp: Optional[float] = None
    correlation_id: Optional[str] = None


@dataclass
class Envelope:
    """ZeroMQ routing envelope for messages.

    Attributes:
        identity: Client identity frame from ROUTER socket
        message: The actual message
        routing_stack: Stack of routing identities for reply path
    """
    identity: bytes
    message: Message
    routing_stack: List[bytes] = field(default_factory=list)


def _encode_decimal(obj: Any) -> Any:
    """Custom encoder for MessagePack to handle Decimal."""
    if isinstance(obj, Decimal):
        return {"__decimal__": str(obj)}
    if isinstance(obj, enum.Enum):
        return obj.value
    if isinstance(obj, bytes):
        return obj.decode('utf-8')
    raise TypeError(f"Cannot serialize {type(obj)}")


def _decode_decimal(obj: Any) -> Any:
    """Custom decoder for MessagePack to restore Decimal."""
    if isinstance(obj, dict) and "__decimal__" in obj:
        return Decimal(obj["__decimal__"])
    return obj


def serialize(message: Message) -> bytes:
    """Serialize a Message to MessagePack bytes.

    Args:
        message: Message to serialize

    Returns:
        MessagePack-encoded bytes
    """
    data = {
        "msg_type": message.msg_type,
        "sender": message.sender,
        "event": message.event,
        "payload": message.payload,
        "recipient": message.recipient,
        "durability": message.durability,
        "timestamp": message.timestamp,
        "correlation_id": message.correlation_id,
    }
    return msgpack.packb(data, default=_encode_decimal, use_bin_type=True)


def deserialize(data: bytes) -> Message:
    """Deserialize MessagePack bytes to a Message.

    Args:
        data: MessagePack-encoded bytes

    Returns:
        Restored Message object
    """
    obj = msgpack.unpackb(data, object_hook=_decode_decimal, raw=False)

    return Message(
        msg_type=MessageType(obj["msg_type"]),
        sender=obj["sender"],
        event=obj["event"],
        payload=obj["payload"],
        recipient=obj.get("recipient"),
        durability=DurabilityLevel(obj.get("durability", 1)),
        timestamp=obj.get("timestamp"),
        correlation_id=obj.get("correlation_id"),
    )


def serialize_envelope(envelope: Envelope) -> List[bytes]:
    """Serialize envelope to ZeroMQ multipart message.

    Args:
        envelope: Envelope to serialize

    Returns:
        List of byte frames for ZeroMQ
    """
    frames = []

    # Add routing stack (if any)
    for frame in envelope.routing_stack:
        frames.append(frame)

    # Add empty delimiter if we have routing stack
    if envelope.routing_stack:
        frames.append(b"")

    # Add identity and message
    frames.append(envelope.identity)
    frames.append(serialize(envelope.message))

    return frames


def deserialize_envelope(frames: List[bytes]) -> Envelope:
    """Deserialize ZeroMQ multipart message to Envelope.

    Args:
        frames: ZeroMQ multipart frames

    Returns:
        Restored Envelope
    """
    # Find empty delimiter
    try:
        delim_idx = frames.index(b"")
        routing_stack = frames[:delim_idx]
        identity = frames[delim_idx + 1]
        msg_data = frames[delim_idx + 2]
    except (ValueError, IndexError):
        # No delimiter - simple format
        routing_stack = []
        identity = frames[0]
        msg_data = frames[1]

    message = deserialize(msg_data)

    return Envelope(
        identity=identity,
        message=message,
        routing_stack=routing_stack
    )
