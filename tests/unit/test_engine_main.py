"""Tests for engine_main entry point."""

import os
import subprocess
import sys

from tyche import engine_main

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "src")


def test_engine_main_has_main_function():
    """engine_main module exposes a main() function."""
    assert callable(getattr(engine_main, "main", None))


def test_engine_main_help_output():
    """engine_main --help shows expected CLI flags."""
    env = {**os.environ, "PYTHONPATH": SRC_DIR}
    result = subprocess.run(
        [sys.executable, "-m", "tyche.engine_main", "--help"],
        capture_output=True,
        text=True,
        timeout=5,
        env=env,
    )
    assert result.returncode == 0
    assert "--registration-port" in result.stdout
    assert "--event-port" in result.stdout
    assert "--heartbeat-port" in result.stdout
