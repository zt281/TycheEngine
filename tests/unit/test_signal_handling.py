"""Tests for signal handling (Ctrl+C) in engine and module."""

import threading
import time

from tyche.engine import TycheEngine
from tyche.module import TycheModule
from tyche.types import Endpoint


def test_engine_stops_via_stop_event():
    """Engine stops when stop() is called from another thread."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 21000),
        event_endpoint=Endpoint("127.0.0.1", 21002),
        heartbeat_endpoint=Endpoint("127.0.0.1", 21004),
    )

    engine_thread = threading.Thread(target=engine.run)
    engine_thread.start()

    time.sleep(0.3)

    engine.stop()

    engine_thread.join(timeout=3.0)
    assert not engine_thread.is_alive(), "Engine did not stop within timeout"


def test_module_stops_via_stop_event():
    """Module stops when stop() is called from another thread."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 21100),
        event_endpoint=Endpoint("127.0.0.1", 21102),
        heartbeat_endpoint=Endpoint("127.0.0.1", 21104),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 21106),
    )

    engine.start_nonblocking()
    time.sleep(0.2)

    try:
        module = TycheModule(
            engine_endpoint=Endpoint("127.0.0.1", 21100),
            heartbeat_receive_endpoint=Endpoint("127.0.0.1", 21106),
            module_id="test_module",
        )

        module_thread = threading.Thread(target=module.run)
        module_thread.start()

        time.sleep(0.5)

        module.stop()

        module_thread.join(timeout=3.0)
        assert not module_thread.is_alive(), "Module did not stop within timeout"
    finally:
        engine.stop()
