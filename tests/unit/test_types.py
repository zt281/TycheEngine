"""Tests for src.tyche.types module."""
from unittest.mock import patch

from src.tyche.types import (
    ADMIN_PORT_DEFAULT,
    HEARTBEAT_INTERVAL,
    HEARTBEAT_LIVENESS,
    BackpressureStrategy,
    DurabilityLevel,
    Endpoint,
    EventType,
    Interface,
    InterfacePattern,
    MessageType,
    ModuleId,
    ModuleInfo,
)


class TestModuleId:
    def test_generate_format(self):
        """Module ID has format family_6hexchars."""
        mid = ModuleId.generate("testfamily")
        parts = mid.split("_")
        assert len(parts) == 2
        assert parts[0] == "testfamily"
        assert len(parts[1]) == 6
        assert all(c in "0123456789abcdef" for c in parts[1])

    def test_generate_default_family(self):
        """Default family is 'unknown'."""
        mid = ModuleId.generate()
        assert mid.startswith("unknown_")

    def test_generate_unique(self):
        """Multiple calls produce different IDs."""
        ids = {ModuleId.generate("fam") for _ in range(100)}
        assert len(ids) == 100

    @patch("src.tyche.types.secrets.token_hex")
    def test_generate_uses_token_hex(self, mock_token_hex):
        """Verify token_hex is called with 3 for 6 hex chars."""
        mock_token_hex.return_value = "aabbcc"
        mid = ModuleId.generate("fam")
        mock_token_hex.assert_called_once_with(3)
        assert mid == "fam_aabbcc"


class TestEventType:
    def test_event_type_values(self):
        assert EventType.REQUEST.value == "request"
        assert EventType.RESPONSE.value == "response"
        assert EventType.EVENT.value == "event"
        assert EventType.HEARTBEAT.value == "heartbeat"
        assert EventType.REGISTER.value == "register"
        assert EventType.ACK.value == "ack"


class TestInterfacePattern:
    def test_pattern_values(self):
        assert InterfacePattern.ON.value == "on"
        assert InterfacePattern.SEND.value == "send"
        assert InterfacePattern.HANDLE.value == "handle"
        assert InterfacePattern.REQUEST.value == "request"


class TestBackpressureStrategy:
    def test_strategy_values(self):
        assert BackpressureStrategy.DROP_OLDEST.value == "drop_oldest"
        assert BackpressureStrategy.DROP_NEWEST.value == "drop_newest"
        assert BackpressureStrategy.BLOCK_PRODUCER.value == "block_producer"


class TestDurabilityLevel:
    def test_level_values(self):
        assert DurabilityLevel.BEST_EFFORT.value == 0
        assert DurabilityLevel.ASYNC_FLUSH.value == 1
        assert DurabilityLevel.SYNC_FLUSH.value == 2


class TestMessageType:
    def test_message_type_values(self):
        assert MessageType.COMMAND.value == "cmd"
        assert MessageType.EVENT.value == "evt"
        assert MessageType.HEARTBEAT.value == "hbt"
        assert MessageType.REGISTER.value == "reg"
        assert MessageType.ACK.value == "ack"
        assert MessageType.RESPONSE.value == "resp"
        assert MessageType.REQUEST.value == "req"


class TestEndpoint:
    def test_str_format(self):
        ep = Endpoint("127.0.0.1", 5555)
        assert str(ep) == "tcp://127.0.0.1:5555"

    def test_str_different_port(self):
        ep = Endpoint("0.0.0.0", 8080)
        assert str(ep) == "tcp://0.0.0.0:8080"


class TestInterface:
    def test_defaults(self):
        iface = Interface(name="on_test", pattern=InterfacePattern.ON, event_type="test")
        assert iface.durability == DurabilityLevel.ASYNC_FLUSH
        assert iface.backpressure == BackpressureStrategy.DROP_OLDEST
        assert iface.max_queue_depth == 10000
        assert iface.wait_timeout is None

    def test_custom_values(self):
        iface = Interface(
            name="handle_compute",
            pattern=InterfacePattern.HANDLE,
            event_type="compute",
            durability=DurabilityLevel.SYNC_FLUSH,
            backpressure=BackpressureStrategy.DROP_NEWEST,
            max_queue_depth=500,
            wait_timeout=10.0,
        )
        assert iface.durability == DurabilityLevel.SYNC_FLUSH
        assert iface.backpressure == BackpressureStrategy.DROP_NEWEST
        assert iface.max_queue_depth == 500
        assert iface.wait_timeout == 10.0


class TestModuleInfo:
    def test_defaults(self):
        info = ModuleInfo(module_id="mod_1", interfaces=[], metadata={})
        assert info.family_name == ""
        assert info.admin_handlers == {}

    def test_with_admin_handlers(self):
        def handler():
            return {}

        info = ModuleInfo(
            module_id="mod_1",
            interfaces=[],
            metadata={"key": "value"},
            family_name="test_family",
            admin_handlers={"health": handler},
        )
        assert info.family_name == "test_family"
        assert info.admin_handlers["health"] == handler


class TestConstants:
    def test_heartbeat_interval(self):
        assert HEARTBEAT_INTERVAL == 1.0

    def test_heartbeat_liveness(self):
        assert HEARTBEAT_LIVENESS == 3

    def test_admin_port_default(self):
        # Admin port is base_port + 3 (registration=5555 → admin=5558),
        # matching the C++ engine port layout documented in
        # src/tyche/cpp/engine/main.cpp.
        assert ADMIN_PORT_DEFAULT == 5558
