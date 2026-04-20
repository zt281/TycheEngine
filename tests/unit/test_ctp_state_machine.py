"""Unit tests for CTP gateway connection state machine."""
import pytest
from modules.trading.gateway.ctp.state_machine import (
    ConnectionState, ConnectionStateMachine, ReconnectConfig,
)


class TestConnectionState:
    def test_state_values(self):
        assert ConnectionState.IDLE.value == "IDLE"
        assert ConnectionState.CONNECTING.value == "CONNECTING"
        assert ConnectionState.CONNECTED.value == "CONNECTED"
        assert ConnectionState.RECONNECTING.value == "RECONNECTING"
        assert ConnectionState.DISCONNECTED.value == "DISCONNECTED"


class TestReconnectConfig:
    def test_defaults(self):
        cfg = ReconnectConfig()
        assert cfg.enabled is True
        assert cfg.max_retries == 10
        assert cfg.base_delay_ms == 1000
        assert cfg.max_delay_ms == 30000

    def test_custom_values(self):
        cfg = ReconnectConfig(enabled=False, max_retries=3, base_delay_ms=500, max_delay_ms=5000)
        assert cfg.enabled is False
        assert cfg.max_retries == 3


class TestConnectionStateMachineInit:
    def test_initial_state_is_idle(self):
        sm = ConnectionStateMachine()
        assert sm.state == ConnectionState.IDLE
        assert sm.retry_count == 0


class TestValidTransitions:
    def test_idle_to_connecting(self):
        sm = ConnectionStateMachine()
        assert sm.transition(ConnectionState.CONNECTING) is True
        assert sm.state == ConnectionState.CONNECTING

    def test_connecting_to_connected(self):
        sm = ConnectionStateMachine()
        sm.transition(ConnectionState.CONNECTING)
        assert sm.transition(ConnectionState.CONNECTED) is True

    def test_connecting_to_disconnected(self):
        sm = ConnectionStateMachine()
        sm.transition(ConnectionState.CONNECTING)
        assert sm.transition(ConnectionState.DISCONNECTED) is True

    def test_connected_to_reconnecting(self):
        sm = ConnectionStateMachine()
        sm.transition(ConnectionState.CONNECTING)
        sm.transition(ConnectionState.CONNECTED)
        assert sm.transition(ConnectionState.RECONNECTING) is True

    def test_reconnecting_to_connecting(self):
        sm = ConnectionStateMachine()
        sm.transition(ConnectionState.CONNECTING)
        sm.transition(ConnectionState.CONNECTED)
        sm.transition(ConnectionState.RECONNECTING)
        assert sm.transition(ConnectionState.CONNECTING) is True

    def test_reconnecting_to_disconnected(self):
        sm = ConnectionStateMachine()
        sm.transition(ConnectionState.CONNECTING)
        sm.transition(ConnectionState.CONNECTED)
        sm.transition(ConnectionState.RECONNECTING)
        assert sm.transition(ConnectionState.DISCONNECTED) is True

    def test_disconnected_to_connecting(self):
        sm = ConnectionStateMachine()
        sm.transition(ConnectionState.DISCONNECTED)
        assert sm.transition(ConnectionState.CONNECTING) is True


class TestInvalidTransitions:
    def test_idle_to_connected(self):
        sm = ConnectionStateMachine()
        assert sm.transition(ConnectionState.CONNECTED) is False
        assert sm.state == ConnectionState.IDLE

    def test_idle_to_reconnecting(self):
        sm = ConnectionStateMachine()
        assert sm.transition(ConnectionState.RECONNECTING) is False

    def test_connected_to_idle(self):
        sm = ConnectionStateMachine()
        sm.transition(ConnectionState.CONNECTING)
        sm.transition(ConnectionState.CONNECTED)
        assert sm.transition(ConnectionState.IDLE) is False

    def test_connected_to_connected(self):
        sm = ConnectionStateMachine()
        sm.transition(ConnectionState.CONNECTING)
        sm.transition(ConnectionState.CONNECTED)
        assert sm.transition(ConnectionState.CONNECTED) is False


class TestStatePayload:
    def test_payload_contains_required_fields(self):
        sm = ConnectionStateMachine()
        sm.transition(ConnectionState.CONNECTING)
        sm.transition(ConnectionState.CONNECTED)
        payload = sm.to_payload(reason="login success")
        assert payload["previous_state"] == "CONNECTING"
        assert payload["state"] == "CONNECTED"
        assert payload["reason"] == "login success"
        assert payload["venue"] == "openctp"
        assert "retry_count" in payload
        assert "next_retry_ms" in payload


class TestBackoffCalculation:
    def test_first_retry(self):
        cfg = ReconnectConfig(base_delay_ms=1000, max_delay_ms=30000)
        sm = ConnectionStateMachine(reconnect_config=cfg)
        sm.transition(ConnectionState.CONNECTING)
        sm.transition(ConnectionState.CONNECTED)
        sm.transition(ConnectionState.RECONNECTING)
        delay = sm.next_backoff_ms()
        assert delay == 1000

    def test_second_retry(self):
        cfg = ReconnectConfig(base_delay_ms=1000, max_delay_ms=30000)
        sm = ConnectionStateMachine(reconnect_config=cfg)
        sm.transition(ConnectionState.CONNECTING)
        sm.transition(ConnectionState.CONNECTED)
        sm.transition(ConnectionState.RECONNECTING)
        sm.transition(ConnectionState.CONNECTING)
        sm.transition(ConnectionState.CONNECTED)
        sm.transition(ConnectionState.RECONNECTING)
        delay = sm.next_backoff_ms()
        assert delay == 2000

    def test_max_backoff(self):
        cfg = ReconnectConfig(base_delay_ms=1000, max_delay_ms=30000)
        sm = ConnectionStateMachine(reconnect_config=cfg)
        sm.transition(ConnectionState.CONNECTING)
        sm.transition(ConnectionState.CONNECTED)
        for _ in range(5):
            sm.transition(ConnectionState.RECONNECTING)
            sm.transition(ConnectionState.CONNECTING)
            sm.transition(ConnectionState.CONNECTED)
        sm.transition(ConnectionState.RECONNECTING)
        delay = sm.next_backoff_ms()
        assert delay == 30000

    def test_backoff_with_jitter_range(self):
        cfg = ReconnectConfig(base_delay_ms=1000, max_delay_ms=30000)
        sm = ConnectionStateMachine(reconnect_config=cfg)
        sm.transition(ConnectionState.CONNECTING)
        sm.transition(ConnectionState.CONNECTED)
        sm.transition(ConnectionState.RECONNECTING)
        delay = sm.next_backoff_ms()
        assert 1000 <= delay <= 1200

    def test_retry_count_increments(self):
        sm = ConnectionStateMachine()
        sm.transition(ConnectionState.CONNECTING)
        sm.transition(ConnectionState.CONNECTED)
        assert sm.retry_count == 0
        sm.transition(ConnectionState.RECONNECTING)
        assert sm.retry_count == 1

    def test_retry_count_does_not_reset_on_connected(self):
        sm = ConnectionStateMachine()
        sm.transition(ConnectionState.CONNECTING)
        sm.transition(ConnectionState.CONNECTED)
        sm.transition(ConnectionState.RECONNECTING)
        assert sm.retry_count == 1
        sm.transition(ConnectionState.CONNECTING)
        sm.transition(ConnectionState.CONNECTED)
        assert sm.retry_count == 1

    def test_max_retries_exceeded(self):
        cfg = ReconnectConfig(max_retries=2)
        sm = ConnectionStateMachine(reconnect_config=cfg)
        sm.transition(ConnectionState.CONNECTING)
        sm.transition(ConnectionState.CONNECTED)
        sm.transition(ConnectionState.RECONNECTING)  # retry 1
        sm.transition(ConnectionState.CONNECTING)
        sm.transition(ConnectionState.CONNECTED)
        sm.transition(ConnectionState.RECONNECTING)  # retry 2
        sm.transition(ConnectionState.CONNECTING)
        sm.transition(ConnectionState.CONNECTED)
        sm.transition(ConnectionState.RECONNECTING)  # retry 3 > max
        assert sm.retry_count == 3
        assert sm.max_retries_exceeded() is True

    def test_exceeds_max_retries(self):
        cfg = ReconnectConfig(max_retries=1)
        sm = ConnectionStateMachine(reconnect_config=cfg)
        sm.transition(ConnectionState.CONNECTING)
        sm.transition(ConnectionState.CONNECTED)
        sm.transition(ConnectionState.RECONNECTING)
        assert sm.max_retries_exceeded() is False
        sm.transition(ConnectionState.CONNECTING)
        sm.transition(ConnectionState.CONNECTED)
        sm.transition(ConnectionState.RECONNECTING)
        assert sm.max_retries_exceeded() is True
