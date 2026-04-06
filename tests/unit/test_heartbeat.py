"""Tests for Paranoid Pirate heartbeat protocol."""
import time
from unittest.mock import Mock

from tyche.heartbeat import HeartbeatMonitor, HeartbeatSender
from tyche.types import HEARTBEAT_INTERVAL, HEARTBEAT_LIVENESS


def test_heartbeat_monitor_init():
    """Monitor initializes with correct liveness (with grace period)."""
    monitor = HeartbeatMonitor()
    # With default initial_grace_period=True, liveness is doubled
    assert monitor.liveness == HEARTBEAT_LIVENESS * 2
    assert monitor.interval == HEARTBEAT_INTERVAL


def test_heartbeat_monitor_init_no_grace():
    """Monitor initializes with correct liveness (no grace period)."""
    monitor = HeartbeatMonitor(initial_grace_period=False)
    assert monitor.liveness == HEARTBEAT_LIVENESS
    assert monitor.interval == HEARTBEAT_INTERVAL


def test_heartbeat_monitor_update():
    """Update resets liveness counter."""
    monitor = HeartbeatMonitor()
    monitor.liveness = 1  # Simulate one missed heartbeat

    monitor.update()
    assert monitor.liveness == HEARTBEAT_LIVENESS


def test_heartbeat_monitor_expired():
    """Monitor detects expired heartbeat."""
    monitor = HeartbeatMonitor()
    monitor.liveness = 0

    assert monitor.is_expired() is True


def test_heartbeat_monitor_not_expired():
    """Monitor shows not expired when liveness > 0."""
    monitor = HeartbeatMonitor()
    assert monitor.is_expired() is False


def test_heartbeat_sender_init():
    """Sender initializes with correct interval."""
    socket = Mock()
    sender = HeartbeatSender(socket, "zeus3f7a9c")
    assert sender.module_id == "zeus3f7a9c"
    assert sender.interval == HEARTBEAT_INTERVAL


def test_heartbeat_sender_should_send():
    """Sender knows when to send heartbeat."""
    socket = Mock()
    sender = HeartbeatSender(socket, "zeus3f7a9c")

    # Force next heartbeat time to past
    sender.next_heartbeat = time.time() - 1

    assert sender.should_send() is True


def test_heartbeat_sender_send():
    """Sender sends correct heartbeat message."""
    socket = Mock()
    sender = HeartbeatSender(socket, "zeus3f7a9c")

    sender.send()

    assert socket.send_multipart.called
    frames = socket.send_multipart.call_args[0][0]
    assert len(frames) == 2
    assert frames[0] == b"zeus3f7a9c"
    # Second frame is MessagePack data


def test_heartbeat_sender_updates_next_time():
    """Sending updates next heartbeat time."""
    socket = Mock()
    sender = HeartbeatSender(socket, "zeus3f7a9c")

    # Set next_heartbeat to past to ensure update
    sender.next_heartbeat = time.time() - 0.1
    old_next = sender.next_heartbeat
    sender.send()

    assert sender.next_heartbeat > old_next
