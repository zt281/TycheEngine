"""Tests for core type definitions."""

from tyche.types import (
    HEARTBEAT_INTERVAL,
    HEARTBEAT_LIVENESS,
    DurabilityLevel,
    Endpoint,
    EventType,
    Interface,
    InterfacePattern,
    MessageType,
    ModuleId,
    ModuleInfo,
)


def test_module_id_format_with_deity():
    """ModuleId.generate with explicit deity produces {deity}{6-hex-chars}."""
    mid = ModuleId.generate("zeus")
    assert mid.startswith("zeus")
    suffix = mid[len("zeus"):]
    assert len(suffix) == 6
    # Suffix must be valid hex
    int(suffix, 16)


def test_module_id_format_random_deity():
    """ModuleId.generate with no deity picks from the deity list."""
    mid = ModuleId.generate()
    # Must start with one of the known deities
    assert any(mid.startswith(d) for d in ModuleId.DEITIES)
    # Must end with exactly 6 hex chars
    for deity in ModuleId.DEITIES:
        if mid.startswith(deity):
            suffix = mid[len(deity):]
            assert len(suffix) == 6
            int(suffix, 16)
            break


def test_module_id_uniqueness():
    """Two generated IDs should not be identical (probabilistic)."""
    ids = {ModuleId.generate() for _ in range(100)}
    assert len(ids) == 100


def test_endpoint_str():
    """Endpoint.__str__ produces a tcp:// ZMQ address."""
    ep = Endpoint("127.0.0.1", 5555)
    assert str(ep) == "tcp://127.0.0.1:5555"


def test_event_type_values():
    """EventType enum has expected members."""
    assert EventType.REQUEST.value == "request"
    assert EventType.HEARTBEAT.value == "heartbeat"


def test_interface_pattern_values():
    """InterfacePattern enum has expected prefixes."""
    assert InterfacePattern.ON.value == "on_"
    assert InterfacePattern.ACK.value == "ack_"
    assert InterfacePattern.WHISPER.value == "whisper_"
    assert InterfacePattern.ON_COMMON.value == "on_common_"
    assert InterfacePattern.BROADCAST.value == "broadcast_"


def test_durability_levels():
    """DurabilityLevel enum uses integer values 0-2."""
    assert DurabilityLevel.BEST_EFFORT.value == 0
    assert DurabilityLevel.ASYNC_FLUSH.value == 1
    assert DurabilityLevel.SYNC_FLUSH.value == 2


def test_message_type_values():
    """MessageType enum has expected short codes."""
    assert MessageType.COMMAND.value == "cmd"
    assert MessageType.EVENT.value == "evt"
    assert MessageType.HEARTBEAT.value == "hbt"


def test_heartbeat_constants():
    """Heartbeat constants have expected defaults."""
    assert HEARTBEAT_INTERVAL == 1.0
    assert HEARTBEAT_LIVENESS == 3


def test_interface_dataclass_defaults():
    """Interface dataclass has correct default durability."""
    iface = Interface(
        name="on_data",
        pattern=InterfacePattern.ON,
        event_type="on_data",
    )
    assert iface.durability == DurabilityLevel.ASYNC_FLUSH


def test_module_info_dataclass():
    """ModuleInfo stores module registration data."""
    info = ModuleInfo(
        module_id="zeus123456",
        endpoint=Endpoint("127.0.0.1", 5555),
        interfaces=[],
        metadata={"version": "1.0"},
    )
    assert info.module_id == "zeus123456"
    assert info.metadata["version"] == "1.0"
