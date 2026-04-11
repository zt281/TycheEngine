"""Tests for heartbeat protocol between module and engine.

Verifies that modules send heartbeats to engine and don't expire prematurely.
"""

import time

import pytest

from tyche.engine import TycheEngine
from tyche.heartbeat import HeartbeatManager
from tyche.module import TycheModule
from tyche.types import Endpoint


@pytest.mark.slow
@pytest.mark.timeout(10)
def test_module_does_not_expire_with_heartbeats():
    """Module stays alive when sending heartbeats to engine."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 23000),
        event_endpoint=Endpoint("127.0.0.1", 23002),
        heartbeat_endpoint=Endpoint("127.0.0.1", 23004),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 23006),
    )

    engine.start_nonblocking()
    time.sleep(0.2)

    try:
        module = TycheModule(
            engine_endpoint=Endpoint("127.0.0.1", 23000),
            heartbeat_receive_endpoint=Endpoint("127.0.0.1", 23006),
            module_id="test_heartbeat_module",
        )

        module.start_nonblocking()
        time.sleep(0.3)

        assert "test_heartbeat_module" in engine.modules, "Module not registered"

        # Wait longer than 3 heartbeat intervals (1s each)
        time.sleep(5.0)

        assert "test_heartbeat_module" in engine.modules, (
            "Module expired despite heartbeats"
        )

        module.stop()
    finally:
        engine.stop()


@pytest.mark.slow
@pytest.mark.timeout(10)
def test_module_expires_without_heartbeats():
    """Module expires when heartbeats are not sent."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 23100),
        event_endpoint=Endpoint("127.0.0.1", 23102),
        heartbeat_endpoint=Endpoint("127.0.0.1", 23104),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 23106),
    )

    engine.start_nonblocking()
    time.sleep(0.2)

    try:
        from unittest.mock import Mock

        module_info = Mock()
        module_info.module_id = "ghost_module"
        module_info.interfaces = []

        engine.register_module(module_info)
        assert "ghost_module" in engine.modules

        # Wait for expiration (grace period * liveness + margin)
        time.sleep(7.0)

        assert "ghost_module" not in engine.modules, (
            "Module should have expired without heartbeats"
        )
    finally:
        engine.stop()


def test_heartbeat_manager_expiration():
    """HeartbeatManager properly expires peers."""
    manager = HeartbeatManager(interval=0.01, liveness=2)

    manager.register("test_peer")
    assert "test_peer" in manager.monitors

    # liveness=2 with initial grace * 2 = 4, so 5 ticks should expire
    for _ in range(5):
        manager.tick_all()

    expired = manager.get_expired()
    assert "test_peer" in expired


def test_heartbeat_manager_update_resets_liveness():
    """Heartbeat update resets liveness counter."""
    manager = HeartbeatManager(interval=0.01, liveness=2)

    manager.register("test_peer")
    manager.update("test_peer")

    # After 2 ticks, still alive (liveness reset to 2 by update)
    manager.tick_all()
    manager.tick_all()

    assert "test_peer" not in manager.get_expired()

    # One more tick pushes it to expired
    manager.tick_all()
    assert "test_peer" in manager.get_expired()
