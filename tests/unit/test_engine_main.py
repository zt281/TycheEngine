"""Tests for engine_main entry point."""

import os
import subprocess
import sys

import pytest


# Get src directory for PYTHONPATH in subprocess tests
SRC_DIR = os.path.join(os.path.dirname(__file__), '..', '..', 'src')


def test_engine_main_module_exists():
    """Test that engine_main module can be imported."""
    from tyche import engine_main

    assert hasattr(engine_main, "main")


def test_engine_main_argparse():
    """Test that engine_main accepts CLI arguments."""
    from tyche import engine_main

    # Test that argparse is set up correctly
    assert hasattr(engine_main, "main")


def test_engine_main_help():
    """Test that engine_main --help works."""
    env = os.environ.copy()
    env["PYTHONPATH"] = SRC_DIR

    result = subprocess.run(
        [sys.executable, "-m", "tyche.engine_main", "--help"],
        capture_output=True,
        text=True,
        timeout=5,
        env=env,
    )
    assert result.returncode == 0
    assert "Tyche Engine" in result.stdout
    assert "--registration-port" in result.stdout
    assert "--event-port" in result.stdout
    assert "--heartbeat-port" in result.stdout
