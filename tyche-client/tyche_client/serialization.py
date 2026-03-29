"""MessagePack serialization/deserialization."""

import msgpack
from typing import Any, Dict, Type

from .types import Tick, Quote, Trade, Bar, Order, OrderEvent, Ack, Position, Risk


TYPE_MAP: Dict[str, Type] = {
    "Tick": Tick,
    "Quote": Quote,
    "Trade": Trade,
    "Bar": Bar,
    "Order": Order,
    "OrderEvent": OrderEvent,
    "Ack": Ack,
    "Position": Position,
    "Risk": Risk,
}


def encode(obj: Any) -> bytes:
    """Encode a dataclass to MessagePack bytes.

    Args:
        obj: A dataclass instance.

    Returns:
        MessagePack-encoded bytes with _type discriminator.
    """
    from dataclasses import asdict
    d = asdict(obj)
    d["_type"] = type(obj).__name__
    return msgpack.packb(d, use_bin_type=True)


def decode(data: bytes) -> Any:
    """Decode MessagePack bytes to a dataclass.

    Args:
        data: MessagePack-encoded bytes.

    Returns:
        A dataclass instance.

    Raises:
        ValueError: If the type is unknown.
    """
    d = msgpack.unpackb(data, raw=False)
    type_name = d.pop("_type", None)
    if type_name is None:
        raise ValueError("Missing '_type' field in message")
    cls = TYPE_MAP.get(type_name)
    if cls is None:
        raise ValueError(f"Unknown type: {type_name}")
    return cls(**d)
