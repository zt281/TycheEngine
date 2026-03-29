"""Unit tests for tyche_launcher.monitor module."""

import pytest
import time


def test_circuit_breaker_allows_execution_initially():
    """Circuit breaker allows execution initially."""
    from tyche_launcher.monitor import CircuitBreaker

    cb = CircuitBreaker(max_failures=3, window_seconds=60)
    assert cb.can_execute() is True


def test_circuit_breaker_blocks_after_max_failures():
    """Circuit breaker blocks after max failures."""
    from tyche_launcher.monitor import CircuitBreaker

    cb = CircuitBreaker(max_failures=3, window_seconds=60)

    # Record 3 failures
    cb.record_failure()
    cb.record_failure()
    cb.record_failure()

    assert cb.can_execute() is False


def test_circuit_breaker_resets_after_window():
    """Circuit breaker resets after window expires."""
    from tyche_launcher.monitor import CircuitBreaker

    cb = CircuitBreaker(max_failures=3, window_seconds=1)  # 1 second window

    cb.record_failure()
    cb.record_failure()
    cb.record_failure()

    assert cb.can_execute() is False

    # Wait for window to expire
    time.sleep(1.1)

    assert cb.can_execute() is True


def test_circuit_breaker_success_clears_failures():
    """Success clears failure history."""
    from tyche_launcher.monitor import CircuitBreaker

    cb = CircuitBreaker(max_failures=3, window_seconds=60)

    cb.record_failure()
    cb.record_failure()
    cb.record_success()

    assert cb.can_execute() is True


def test_process_monitor_creation():
    """ProcessMonitor tracks name and initial state."""
    from tyche_launcher.monitor import ProcessMonitor

    monitor = ProcessMonitor(name="test.module", restart_policy="on-failure")
    assert monitor.name == "test.module"
    assert monitor.restart_policy == "on-failure"


def test_process_monitor_record_start():
    """ProcessMonitor tracks start count."""
    from tyche_launcher.monitor import ProcessMonitor

    monitor = ProcessMonitor(name="test.module", restart_policy="always")
    monitor.record_start(12345)

    assert monitor.start_count == 1
    assert monitor.pid == 12345


def test_process_monitor_record_exit_non_zero():
    """ProcessMonitor records non-zero exit."""
    from tyche_launcher.monitor import ProcessMonitor

    monitor = ProcessMonitor(name="test.module", restart_policy="on-failure")
    monitor.record_start(12345)
    monitor.record_exit(1)

    assert monitor.last_exit_code == 1
    assert monitor.restart_count == 1


def test_process_monitor_record_exit_zero():
    """ProcessMonitor records zero exit."""
    from tyche_launcher.monitor import ProcessMonitor

    monitor = ProcessMonitor(name="test.module", restart_policy="always")
    monitor.record_start(12345)
    monitor.record_exit(0)

    assert monitor.last_exit_code == 0


def test_process_monitor_should_restart_on_failure():
    """Should restart on-failure policy after non-zero exit."""
    from tyche_launcher.monitor import ProcessMonitor

    monitor = ProcessMonitor(name="test.module", restart_policy="on-failure", max_restarts=3)
    monitor.record_start(12345)
    monitor.record_exit(1)
    monitor.record_start(12345)
    monitor.record_exit(1)

    assert monitor.should_restart() is True


def test_process_monitor_should_not_restart_never():
    """Should not restart never policy."""
    from tyche_launcher.monitor import ProcessMonitor

    monitor = ProcessMonitor(name="test.module", restart_policy="never")
    monitor.record_start(12345)
    monitor.record_exit(1)

    assert monitor.should_restart() is False


def test_process_monitor_should_not_restart_max_restarts():
    """Should not restart when max restarts exceeded."""
    from tyche_launcher.monitor import ProcessMonitor

    monitor = ProcessMonitor(name="test.module", restart_policy="on-failure", max_restarts=2)
    for _ in range(2):
        monitor.record_start(12345)
        monitor.record_exit(1)

    # Now at max restarts
    assert monitor.should_restart() is False
