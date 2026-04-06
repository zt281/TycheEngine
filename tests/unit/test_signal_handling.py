"""Tests for signal handling (Ctrl+C) in engine and module."""

import threading
import time

from tyche.engine import TycheEngine
from tyche.module import TycheModule
from tyche.types import Endpoint


def test_engine_stops_via_stop_event():
    """Engine stops when stop() is called from another thread.

    This verifies that the engine's main loop properly checks the stop_event,
    which enables Ctrl+C signal handling to work.
    """
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 5555),
        event_endpoint=Endpoint("127.0.0.1", 5556),
        heartbeat_endpoint=Endpoint("127.0.0.1", 5558)
    )

    # Start engine in a thread
    engine_thread = threading.Thread(target=engine.run)
    engine_thread.start()

    # Give it time to start
    time.sleep(0.2)

    # Stop from another thread (simulates signal handler)
    engine.stop()

    # Should stop within reasonable time (not hang forever)
    engine_thread.join(timeout=2.0)
    assert not engine_thread.is_alive(), "Engine did not stop within timeout"


def test_module_stops_via_stop_event():
    """Module stops when stop() is called from another thread.

    This verifies that the module's main loop properly checks the stop_event,
    which enables Ctrl+C signal handling to work.
    """
    # Start an engine so module can register properly
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 5560),
        event_endpoint=Endpoint("127.0.0.1", 5561),
        heartbeat_endpoint=Endpoint("127.0.0.1", 5562),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 5563)
    )

    engine.start_nonblocking()
    time.sleep(0.1)

    try:
        module = TycheModule(
            engine_endpoint=Endpoint("127.0.0.1", 5560),
            heartbeat_receive_endpoint=Endpoint("127.0.0.1", 5563),
            module_id="test_module"
        )

        # Start module in a thread
        module_thread = threading.Thread(target=module.run)
        module_thread.start()

        # Give it time to start and register
        time.sleep(0.3)

        # Stop from another thread (simulates signal handler)
        module.stop()

        # Should stop within reasonable time (not hang forever)
        module_thread.join(timeout=2.0)
        assert not module_thread.is_alive(), "Module did not stop within timeout"
    finally:
        engine.stop()
