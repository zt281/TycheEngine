"""Tests for src.tyche.message module."""
from decimal import Decimal

import msgpack
import pytest

from src.tyche.message import (
    Envelope,
    Message,
    _decode_decimal,
    _encode_decimal,
    deserialize,
    deserialize_envelope,
    serialize,
    serialize_envelope,
)
from src.tyche.types import DurabilityLevel, MessageType


class TestEncodeDecimal:
    def test_decimal_encoding(self):
        result = _encode_decimal(Decimal("123.456"))
        assert result == {"__decimal__": "123.456"}

    def test_enum_encoding(self):
        result = _encode_decimal(MessageType.EVENT)
        assert result == "evt"

    def test_bytes_encoding(self):
        result = _encode_decimal(b"hello")
        assert result == "hello"

    def test_unsupported_type_raises(self):
        with pytest.raises(TypeError, match="Cannot serialize"):
            _encode_decimal(object())


class TestDecodeDecimal:
    def test_decimal_decoding(self):
        result = _decode_decimal({"__decimal__": "99.99"})
        assert isinstance(result, Decimal)
        assert result == Decimal("99.99")

    def test_plain_dict_passthrough(self):
        d = {"key": "value"}
        assert _decode_decimal(d) == d

    def test_non_dict_passthrough(self):
        assert _decode_decimal("string") == "string"
        assert _decode_decimal(42) == 42


class TestSerializeDeserialize:
    def test_roundtrip_basic(self):
        msg = Message(
            msg_type=MessageType.EVENT,
            sender="mod_1",
            event="test_event",
            payload={"data": "value"},
        )
        data = serialize(msg)
        restored = deserialize(data)
        assert restored.msg_type == MessageType.EVENT
        assert restored.sender == "mod_1"
        assert restored.event == "test_event"
        assert restored.payload == {"data": "value"}

    def test_roundtrip_with_all_fields(self):
        msg = Message(
            msg_type=MessageType.REQUEST,
            sender="mod_a",
            event="compute",
            payload={"key": "val"},
            recipient="mod_b",
            durability=DurabilityLevel.SYNC_FLUSH,
            timestamp=1234567890.5,
            correlation_id="corr-123",
            wait_timeout=5.0,
            run_timeout=30.0,
        )
        data = serialize(msg)
        restored = deserialize(data)
        assert restored.msg_type == MessageType.REQUEST
        assert restored.recipient == "mod_b"
        assert restored.durability == DurabilityLevel.SYNC_FLUSH
        assert restored.timestamp == 1234567890.5
        assert restored.correlation_id == "corr-123"
        assert restored.wait_timeout == 5.0
        assert restored.run_timeout == 30.0

    def test_roundtrip_decimal_payload(self):
        msg = Message(
            msg_type=MessageType.EVENT,
            sender="mod_1",
            event="price",
            payload={"price": Decimal("550.25")},
        )
        data = serialize(msg)
        restored = deserialize(data)
        assert isinstance(restored.payload["price"], Decimal)
        assert restored.payload["price"] == Decimal("550.25")

    def test_default_durability(self):
        """Missing durability field defaults to ASYNC_FLUSH (1)."""
        raw = msgpack.packb({
            "msg_type": "evt",
            "sender": "mod",
            "event": "test",
            "payload": {},
            "recipient": None,
            "durability": None,
        }, use_bin_type=True)
        restored = deserialize(raw)
        assert restored.durability == DurabilityLevel.ASYNC_FLUSH


class TestSerializeEnvelope:
    def test_without_routing_stack(self):
        msg = Message(
            msg_type=MessageType.EVENT,
            sender="mod_1",
            event="test",
            payload={},
        )
        envelope = Envelope(identity=b"client_1", message=msg)
        frames = serialize_envelope(envelope)
        assert len(frames) == 2
        assert frames[0] == b"client_1"
        assert isinstance(frames[1], bytes)

    def test_with_routing_stack(self):
        msg = Message(
            msg_type=MessageType.RESPONSE,
            sender="mod_1",
            event="test",
            payload={"result": "ok"},
        )
        envelope = Envelope(
            identity=b"client_1",
            message=msg,
            routing_stack=[b"proxy_1", b"proxy_2"],
        )
        frames = serialize_envelope(envelope)
        assert len(frames) == 5
        assert frames[0] == b"proxy_1"
        assert frames[1] == b"proxy_2"
        assert frames[2] == b""
        assert frames[3] == b"client_1"
        assert isinstance(frames[4], bytes)


class TestDeserializeEnvelope:
    def test_simple_format(self):
        msg = Message(
            msg_type=MessageType.EVENT,
            sender="mod_1",
            event="test",
            payload={"data": 1},
        )
        msg_bytes = serialize(msg)
        frames = [b"client_1", msg_bytes]
        envelope = deserialize_envelope(frames)
        assert envelope.identity == b"client_1"
        assert envelope.message.event == "test"
        assert envelope.routing_stack == []

    def test_with_routing_stack(self):
        msg = Message(
            msg_type=MessageType.REQUEST,
            sender="mod_a",
            event="compute",
            payload={},
        )
        msg_bytes = serialize(msg)
        frames = [b"proxy_1", b"proxy_2", b"", b"client_1", msg_bytes]
        envelope = deserialize_envelope(frames)
        assert envelope.identity == b"client_1"
        assert envelope.message.event == "compute"
        assert envelope.routing_stack == [b"proxy_1", b"proxy_2"]

    def test_empty_frames_raises_index_error(self):
        """Too few frames should raise IndexError during access."""
        with pytest.raises(IndexError):
            deserialize_envelope([])
