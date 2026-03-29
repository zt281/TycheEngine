"""Unit tests for tyche_launcher.launcher module."""

import pytest
from tyche_launcher.config import LauncherConfig, ModuleConfig
from tyche_launcher.launcher import Launcher


def test_launcher_creation():
    """Launcher creates monitors for each module."""
    config = LauncherConfig(
        nexus_endpoint="ipc:///tmp/tyche/nexus.sock",
        poll_interval_ms=1000,
        modules=[
            ModuleConfig(
                name="test.module",
                command=["python", "test.py"],
                restart_policy="never",
            )
        ],
    )

    launcher = Launcher(config)
    assert len(launcher._monitors) == 1
    assert "test.module" in launcher._monitors


def test_launcher_start_creates_processes():
    """Launcher.start() creates subprocess for each module."""
    config = LauncherConfig(
        nexus_endpoint="ipc:///tmp/tyche/nexus.sock",
        poll_interval_ms=1000,
        modules=[
            ModuleConfig(
                name="test.module",
                command=["python", "-c", "import time; time.sleep(10)"],
                restart_policy="never",
            )
        ],
    )

    launcher = Launcher(config)
    launcher.start()

    # Give process time to start
    import time
    time.sleep(0.2)

    assert launcher._running is True
    assert launcher._processes["test.module"] is not None

    launcher.stop()


def test_launcher_stop_terminates_processes():
    """Launcher.stop() terminates all processes."""
    config = LauncherConfig(
        nexus_endpoint="ipc:///tmp/tyche/nexus.sock",
        poll_interval_ms=1000,
        modules=[
            ModuleConfig(
                name="test.module",
                command=["python", "-c", "import time; time.sleep(60)"],
                restart_policy="never",
            )
        ],
    )

    launcher = Launcher(config)
    launcher.start()
    import time
    time.sleep(0.2)

    assert launcher._running is True

    launcher.stop()

    assert launcher._running is False


def test_launcher_get_status():
    """Launcher.get_status() returns status for all monitors."""
    config = LauncherConfig(
        nexus_endpoint="ipc:///tmp/tyche/nexus.sock",
        poll_interval_ms=1000,
        modules=[
            ModuleConfig(
                name="test.module",
                command=["python", "test.py"],
                restart_policy="never",
            )
        ],
    )

    launcher = Launcher(config)
    status = launcher.get_status()

    assert "test.module" in status
    assert status["test.module"]["name"] == "test.module"
