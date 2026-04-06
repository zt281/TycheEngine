"""Tests for heartbeat protocol between module and engine.

Verifies that modules send heartbeats to engine and don't expire prematurely.
"""

import time
import threading

import pytest

from tyche.engine import TycheEngine
from tyche.module import TycheModule
from tyche.types import Endpoint
from tyche.heartbeat import HeartbeatManager


@pytest.mark.slow
@pytest.mark.timeout(10)
def test_module_does_not_expire_with_heartbeats():
    """Module stays alive when sending heartbeats to engine."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 5555),
        event_endpoint=Endpoint("127.0.0.1", 5556),
        heartbeat_endpoint=Endpoint("127.0.0.1", 5558),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 5559)
    )

    engine.start_nonblocking()
    time.sleep(0.2)

    try:
        module = TycheModule(
            engine_endpoint=Endpoint("127.0.0.1", 5555),
            heartbeat_receive_endpoint=Endpoint("127.0.0.1", 5559),
            module_id="test_heartbeat_module"
        )

        module.start_nonblocking()
        time.sleep(0.3)

        # Verify module registered
        assert "test_heartbeat_module" in engine.modules, "Module not registered"

        # Wait for 5 seconds - longer than 3 heartbeat intervals (1s each)
        time.sleep(5.0)

        # Module should still be registered (not expired)
        assert "test_heartbeat_module" in engine.modules, \
            "Module expired despite heartbeats"

        module.stop()

    finally:
        engine.stop()


@pytest.mark.slow
@pytest.mark.timeout(10)
def test_module_expires_without_heartbeats():
    """Module expires when heartbeats are not sent."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 5560),
        event_endpoint=Endpoint("127.0.0.1", 5561),
        heartbeat_endpoint=Endpoint("127.0.0.1", 5562),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 5563)
    )

    # Start the engine so the monitor worker runs
    engine.start_nonblocking()
    time.sleep(0.2)

    try:
        # Manually register a module (without actual module sending heartbeats)
        from unittest.mock import Mock
        module_info = Mock()
        module_info.module_id = "ghost_module"
        module_info.interfaces = []

        engine.register_module(module_info)

        # Verify module is registered
        assert "ghost_module" in engine.modules

        # Wait for expiration (6 heartbeats * 1 second = 6 seconds with grace period, plus margin)
        time.sleep(7.0)

        # Module should be expired
        assert "ghost_module" not in engine.modules, \
            "Module should have expired without heartbeats"
    finally:
        engine.stop()


def test_heartbeat_manager_expiration():
    """Unit test: HeartbeatManager properly expires peers (fast)."""
    manager = HeartbeatManager(interval=0.01, liveness=2)

    # Register a peer
    manager.register("test_peer")
    assert "test_peer" in manager.monitors

    # After 5 ticks without update, should be expired
    # (liveness=2 with initial grace * 2 = 4 ticks)
    for _ in range(5):
        manager.tick_all()

    expired = manager.get_expired()
    assert "test_peer" in expired


def test_heartbeat_manager_update_resets_liveness():
    """Unit test: Heartbeat update resets liveness counter (fast)."""
    manager = HeartbeatManager(interval=0.01, liveness=2)

    # Register and update
    manager.register("test_peer")
    manager.update("test_peer")

    # After 2 ticks, should still be alive (liveness reset to 2)
    manager.tick_all()
    manager.tick_all()

    expired = manager.get_expired()
    assert "test_peer" not in expired

    # After 3 more ticks, should be expired
    manager.tick_all()
    expired = manager.get_expired()
    assert "test_peer" in expired
