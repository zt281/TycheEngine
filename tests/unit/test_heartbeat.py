"""Tests for src.tyche.heartbeat module."""
import time
from unittest.mock import MagicMock

from src.tyche.heartbeat import (
    HeartbeatManager,
    HeartbeatMonitor,
    HeartbeatSender,
)
from src.tyche.types import HEARTBEAT_INTERVAL, HEARTBEAT_LIVENESS


class TestHeartbeatMonitor:
    def test_init_with_grace_period(self):
        monitor = HeartbeatMonitor(interval=1.0, liveness=3, initial_grace_period=True)
        assert monitor.interval == 1.0
        assert monitor.liveness == 6  # 3 * 2
        assert monitor.last_seen > 0

    def test_init_without_grace_period(self):
        monitor = HeartbeatMonitor(interval=1.0, liveness=3, initial_grace_period=False)
        assert monitor.liveness == 3

    def test_update_resets_liveness(self):
        monitor = HeartbeatMonitor(initial_grace_period=False)
        monitor.tick()
        monitor.tick()
        assert monitor.liveness == 1
        monitor.update()
        assert monitor.liveness == HEARTBEAT_LIVENESS
        assert monitor.last_seen > time.time() - 1.0

    def test_tick_decrements_liveness(self):
        monitor = HeartbeatMonitor(initial_grace_period=False)
        initial = monitor.liveness
        monitor.tick()
        assert monitor.liveness == initial - 1

    def test_is_expired_when_liveness_zero(self):
        monitor = HeartbeatMonitor(initial_grace_period=False)
        monitor.liveness = 1
        assert not monitor.is_expired()
        monitor.tick()
        assert monitor.is_expired()

    def test_is_expired_when_liveness_negative(self):
        monitor = HeartbeatMonitor(initial_grace_period=False)
        monitor.liveness = 0
        assert monitor.is_expired()
        monitor.liveness = -1
        assert monitor.is_expired()

    def test_time_since_last(self):
        monitor = HeartbeatMonitor()
        time.sleep(0.05)
        elapsed = monitor.time_since_last()
        assert elapsed >= 0.04
        assert elapsed < 1.0


class TestHeartbeatSender:
    def test_init(self):
        mock_socket = MagicMock()
        sender = HeartbeatSender(
            socket=mock_socket,
            module_id="test_mod",
            interval=2.0,
        )
        assert sender.socket == mock_socket
        assert sender.module_id == "test_mod"
        assert sender.interval == 2.0
        assert sender.next_heartbeat > time.time()

    def test_should_send_when_time_elapsed(self):
        mock_socket = MagicMock()
        sender = HeartbeatSender(socket=mock_socket, module_id="mod", interval=1.0)
        sender.next_heartbeat = time.time() - 1.0  # Already past
        assert sender.should_send() is True

    def test_should_send_when_not_yet(self):
        mock_socket = MagicMock()
        sender = HeartbeatSender(socket=mock_socket, module_id="mod", interval=10.0)
        sender.next_heartbeat = time.time() + 5.0  # Future
        assert sender.should_send() is False

    def test_send(self):
        mock_socket = MagicMock()
        sender = HeartbeatSender(
            socket=mock_socket,
            module_id="test_mod",
            interval=HEARTBEAT_INTERVAL,
        )
        before = sender.next_heartbeat
        sender.send()

        mock_socket.send_multipart.assert_called_once()
        frames = mock_socket.send_multipart.call_args[0][0]
        assert frames[0] == b"test_mod"
        assert isinstance(frames[1], bytes)
        assert sender.next_heartbeat >= before


class TestHeartbeatManager:
    def test_register(self):
        mgr = HeartbeatManager()
        mgr.register("peer_1")
        assert "peer_1" in mgr.monitors
        assert mgr.monitors["peer_1"].liveness == HEARTBEAT_LIVENESS * 2

    def test_unregister(self):
        mgr = HeartbeatManager()
        mgr.register("peer_1")
        mgr.unregister("peer_1")
        assert "peer_1" not in mgr.monitors

    def test_unregister_nonexistent_no_error(self):
        mgr = HeartbeatManager()
        mgr.unregister("nonexistent")  # Should not raise

    def test_update_existing_peer(self):
        mgr = HeartbeatManager()
        mgr.register("peer_1")
        initial = mgr.monitors["peer_1"].liveness
        mgr.monitors["peer_1"].tick()
        assert mgr.monitors["peer_1"].liveness == initial - 1
        mgr.update("peer_1")
        assert mgr.monitors["peer_1"].liveness == HEARTBEAT_LIVENESS

    def test_update_unknown_peer_creates_new(self):
        mgr = HeartbeatManager()
        mgr.update("new_peer")
        assert "new_peer" in mgr.monitors

    def test_tick_all_returns_expired(self):
        mgr = HeartbeatManager()
        mgr.register("peer_1")
        mgr.register("peer_2")
        # Expire peer_1
        for _ in range(HEARTBEAT_LIVENESS * 2 + 1):
            mgr.monitors["peer_1"].tick()
        expired = mgr.tick_all()
        assert "peer_1" in expired
        assert "peer_2" not in expired

    def test_tick_all_no_expired(self):
        mgr = HeartbeatManager()
        mgr.register("peer_1")
        expired = mgr.tick_all()
        assert expired == []

    def test_get_expired(self):
        mgr = HeartbeatManager()
        mgr.register("peer_1")
        mgr.register("peer_2")
        # Expire peer_1 without tick_all
        mgr.monitors["peer_1"].liveness = 0
        expired = mgr.get_expired()
        assert "peer_1" in expired
        assert "peer_2" not in expired

    def test_get_liveness_existing(self):
        mgr = HeartbeatManager()
        mgr.register("peer_1")
        assert mgr.get_liveness("peer_1") == HEARTBEAT_LIVENESS * 2

    def test_get_liveness_nonexistent(self):
        mgr = HeartbeatManager()
        assert mgr.get_liveness("nonexistent") == -1

    def test_get_last_seen_existing(self):
        mgr = HeartbeatManager()
        mgr.register("peer_1")
        ts = mgr.get_last_seen("peer_1")
        assert ts > 0.0
        assert ts <= time.time()

    def test_get_last_seen_nonexistent(self):
        mgr = HeartbeatManager()
        assert mgr.get_last_seen("nonexistent") == 0.0

    def test_thread_safety(self):
        """Basic thread safety check for concurrent updates."""
        import threading
        mgr = HeartbeatManager()
        errors = []

        def updater():
            try:
                for i in range(100):
                    mgr.register(f"peer_{i}")
                    mgr.update(f"peer_{i}")
                    mgr.tick_all()
            except Exception as e:
                errors.append(e)

        threads = [threading.Thread(target=updater) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
