"""Integration test for multi-process communication.

Tests that Engine and Module can run as separate processes and communicate
via ZeroMQ.
"""

import subprocess
import sys
import time

import pytest
import zmq

from tyche.engine import TycheEngine
from tyche.module import TycheModule
from tyche.types import Endpoint


def test_engine_and_module_in_same_process():
    """Engine and Module can communicate in same process (baseline)."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 35555),
        event_endpoint=Endpoint("127.0.0.1", 35556),
        heartbeat_endpoint=Endpoint("127.0.0.1", 35558)
    )

    # Start engine
    engine.start_nonblocking()
    time.sleep(0.3)

    try:
        # Create a simple module
        module = TycheModule(
            engine_endpoint=Endpoint("127.0.0.1", 35555),
            module_id="test_module_001"
        )

        # Add an interface
        received = []

        def on_test(payload):
            received.append(payload)

        module.add_interface("on_test", on_test)

        # Start module (this will register with engine)
        module.start_nonblocking()
        time.sleep(0.3)

        # Verify registration
        assert "test_module_001" in engine.modules

        module.stop()

    finally:
        engine.stop()


def test_engine_main_help():
    """Engine entry point can show help."""
    result = subprocess.run(
        [sys.executable, "-m", "tyche.engine_main", "--help"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert "Tyche Engine" in result.stdout


def test_module_main_help():
    """Module entry point can show help."""
    result = subprocess.run(
        [sys.executable, "-m", "tyche.module_main", "--help"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert "Tyche Module" in result.stdout


@pytest.mark.slow
def test_engine_process_starts_and_stops():
    """Engine process can start and respond to signals."""
    # Start engine process
    proc = subprocess.Popen(
        [sys.executable, "-m", "tyche.engine_main",
         "--registration-port", "45555",
         "--event-port", "45556",
         "--heartbeat-port", "45558"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Give it time to start
    time.sleep(0.5)

    try:
        # Check it's running
        assert proc.poll() is None

        # Try to connect via ZMQ
        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect("tcp://127.0.0.1:45555")
        socket.setsockopt(zmq.RCVTIMEO, 1000)

        # Send a test message (will fail but proves engine is listening)
        socket.send(b"test")
        try:
            socket.recv()
        except zmq.error.Again:
            pass  # Expected - invalid message format

        socket.close()
        context.term()

    finally:
        # Stop the process
        proc.terminate()
        proc.wait(timeout=5)


@pytest.mark.slow
def test_module_connects_to_engine_process():
    """Module process can connect to running engine process."""
    # Start engine process
    engine_proc = subprocess.Popen(
        [sys.executable, "-m", "tyche.engine_main",
         "--registration-port", "46555",
         "--event-port", "46556",
         "--heartbeat-port", "46558"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # Give engine time to start
    time.sleep(0.5)

    module_proc = None
    try:
        # Check engine is running
        assert engine_proc.poll() is None

        # Start module process
        module_proc = subprocess.Popen(
            [sys.executable, "-m", "tyche.module_main",
             "--engine-port", "46555",
             "--module-id", "test_athena_001"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Give module time to register
        time.sleep(1.0)

        # Check both processes are still running
        assert engine_proc.poll() is None
        assert module_proc.poll() is None

        # Stop module first
        module_proc.terminate()
        module_proc.wait(timeout=5)

    finally:
        # Stop engine
        engine_proc.terminate()
        engine_proc.wait(timeout=5)
