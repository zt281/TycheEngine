"""Tests for core type definitions."""
from tyche.types import (
    HEARTBEAT_INTERVAL,
    HEARTBEAT_LIVENESS,
    DurabilityLevel,
    EventType,
    InterfacePattern,
    MessageType,
    ModuleId,
)


def test_module_id_format():
    """Module IDs follow {deity}{6-char MD5} format."""
    module_id = ModuleId.generate("zeus")
    assert module_id.startswith("zeus")
    assert len(module_id) == 10  # 4 deity + 6 MD5
    assert module_id[4:].isalnum()


def test_event_type_values():
    """EventType enum has required variants."""
    assert EventType.REQUEST.value == "request"
    assert EventType.RESPONSE.value == "response"
    assert EventType.EVENT.value == "event"
    assert EventType.HEARTBEAT.value == "heartbeat"
    assert EventType.REGISTER.value == "register"
    assert EventType.ACK.value == "ack"


def test_interface_pattern_values():
    """InterfacePattern enum has all required patterns."""
    assert InterfacePattern.ON.value == "on_"
    assert InterfacePattern.ACK.value == "ack_"
    assert InterfacePattern.WHISPER.value == "whisper_"
    assert InterfacePattern.ON_COMMON.value == "on_common_"
    assert InterfacePattern.BROADCAST.value == "broadcast_"


def test_durability_levels():
    """DurabilityLevel enum has required levels."""
    assert DurabilityLevel.BEST_EFFORT.value == 0
    assert DurabilityLevel.ASYNC_FLUSH.value == 1
    assert DurabilityLevel.SYNC_FLUSH.value == 2


def test_message_type_values():
    """MessageType enum has required types."""
    assert MessageType.COMMAND.value == "cmd"
    assert MessageType.EVENT.value == "evt"
    assert MessageType.HEARTBEAT.value == "hbt"
    assert MessageType.REGISTER.value == "reg"
    assert MessageType.ACK.value == "ack"


def test_heartbeat_constants():
    """Heartbeat constants are defined."""
    assert HEARTBEAT_INTERVAL == 1.0
    assert HEARTBEAT_LIVENESS == 3
