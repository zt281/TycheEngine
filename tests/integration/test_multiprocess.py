"""Integration test for multi-process communication.

Tests that Engine and Module can run as separate processes and communicate
via ZeroMQ.
"""

import os
import subprocess
import sys
import time

import pytest
import zmq

from tyche.engine import TycheEngine
from tyche.module import TycheModule
from tyche.types import Endpoint

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "src")


def test_engine_and_module_in_same_process():
    """Engine and Module can communicate in same process (baseline)."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 25000),
        event_endpoint=Endpoint("127.0.0.1", 25002),
        heartbeat_endpoint=Endpoint("127.0.0.1", 25004),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25006),
    )

    engine.start_nonblocking()
    time.sleep(0.3)

    try:
        received = []

        module = TycheModule(
            engine_endpoint=Endpoint("127.0.0.1", 25000),
            heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25006),
            module_id="test_module_001",
        )

        def on_test(payload: dict) -> None:
            received.append(payload)

        module.add_interface("on_test", on_test)

        module.start_nonblocking()
        time.sleep(0.5)

        assert "test_module_001" in engine.modules

        module.stop()
    finally:
        engine.stop()


def test_engine_main_help():
    """Engine entry point can show help."""
    env = {**os.environ, "PYTHONPATH": SRC_DIR}
    result = subprocess.run(
        [sys.executable, "-m", "tyche.engine_main", "--help"],
        capture_output=True,
        text=True,
        timeout=5,
        env=env,
    )
    assert result.returncode == 0
    assert "Tyche Engine" in result.stdout


def test_module_main_help():
    """Module entry point can show help."""
    env = {**os.environ, "PYTHONPATH": SRC_DIR}
    result = subprocess.run(
        [sys.executable, "-m", "tyche.module_main", "--help"],
        capture_output=True,
        text=True,
        timeout=5,
        env=env,
    )
    assert result.returncode == 0
    assert "Tyche Module" in result.stdout


@pytest.mark.slow
def test_engine_process_starts_and_stops():
    """Engine process can start, listen for connections, and stop."""
    env = {**os.environ, "PYTHONPATH": SRC_DIR}
    proc = subprocess.Popen(
        [
            sys.executable, "-m", "tyche.engine_main",
            "--registration-port", "25100",
            "--event-port", "25102",
            "--heartbeat-port", "25104",
            "--heartbeat-receive-port", "25106",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    time.sleep(0.5)

    try:
        assert proc.poll() is None, "Engine process exited unexpectedly"

        context = zmq.Context()
        socket = context.socket(zmq.REQ)
        socket.connect("tcp://127.0.0.1:25100")
        socket.setsockopt(zmq.RCVTIMEO, 1000)

        # Send a raw test message (will fail but proves engine is listening)
        socket.send(b"test")
        try:
            socket.recv()
        except zmq.error.Again:
            pass  # Expected - invalid message format

        socket.close()
        context.term()
    finally:
        proc.terminate()
        proc.wait(timeout=5)


@pytest.mark.slow
def test_module_connects_to_engine_process():
    """Module process can connect to running engine process."""
    env = {**os.environ, "PYTHONPATH": SRC_DIR}
    engine_proc = subprocess.Popen(
        [
            sys.executable, "-m", "tyche.engine_main",
            "--registration-port", "25200",
            "--event-port", "25202",
            "--heartbeat-port", "25204",
            "--heartbeat-receive-port", "25206",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=env,
    )

    time.sleep(0.5)

    module_proc = None
    try:
        assert engine_proc.poll() is None

        module_proc = subprocess.Popen(
            [
                sys.executable, "-m", "tyche.module_main",
                "--engine-port", "25200",
                "--heartbeat-port", "25206",
                "--module-id", "test_athena_001",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )

        time.sleep(1.0)

        assert engine_proc.poll() is None, "Engine process died"
        assert module_proc.poll() is None, "Module process died"

        module_proc.terminate()
        module_proc.wait(timeout=5)
    finally:
        engine_proc.terminate()
        engine_proc.wait(timeout=5)
