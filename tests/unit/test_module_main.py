"""Tests for module_main entry point."""

import subprocess
import sys

import pytest


def test_module_main_module_exists():
    """Test that module_main module can be imported."""
    from tyche import module_main

    assert hasattr(module_main, "main")


def test_module_main_argparse():
    """Test that module_main accepts CLI arguments."""
    from tyche import module_main

    assert hasattr(module_main, "main")


def test_module_main_help():
    """Test that module_main --help works."""
    result = subprocess.run(
        [sys.executable, "-m", "tyche.module_main", "--help"],
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert result.returncode == 0
    assert "Tyche Module" in result.stdout
    assert "--engine-host" in result.stdout
    assert "--engine-port" in result.stdout
    assert "--module-id" in result.stdout
