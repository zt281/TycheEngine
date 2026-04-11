"""Tests for module_main entry point."""

import os
import subprocess
import sys

from tyche import module_main

SRC_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "src")


def test_module_main_has_main_function():
    """module_main module exposes a main() function."""
    assert callable(getattr(module_main, "main", None))


def test_module_main_help_output():
    """module_main --help shows expected CLI flags."""
    env = {**os.environ, "PYTHONPATH": SRC_DIR}
    result = subprocess.run(
        [sys.executable, "-m", "tyche.module_main", "--help"],
        capture_output=True,
        text=True,
        timeout=5,
        env=env,
    )
    assert result.returncode == 0
    assert "--engine-host" in result.stdout
    assert "--engine-port" in result.stdout
    assert "--module-id" in result.stdout
