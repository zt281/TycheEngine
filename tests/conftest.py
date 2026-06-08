"""Shared test fixtures for TycheEngine integration tests."""
import atexit
import os
import signal
import subprocess
import sys
import threading
import uuid
import weakref
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add repo root to path so 'src.tyche' imports resolve
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.tyche.dead_letter import DeadLetterStore
from src.tyche.message import Message
from src.tyche.types import (
    BackpressureStrategy,
    DurabilityLevel,
    Endpoint,
    Interface,
    InterfacePattern,
    MessageType,
    ModuleInfo,
)

# ── Global Resource Tracker ────────────────────────────────────────

class _ResourceTracker:
    """Track ZMQ contexts, sockets, engines, and modules created during tests.

    Ensures all resources are cleaned up even if tests crash or hang.
    """

    def __init__(self):
        self._engines = []          # weak refs to TycheEngine instances
        self._modules = []          # weak refs to TycheModule instances
        self._zmq_contexts = []     # weak refs to zmq.Context instances
        self._child_pids = []       # PIDs of spawned subprocesses
        self._lock = threading.Lock()

    def track_engine(self, engine):
        ref = weakref.ref(engine, lambda r: self._engines.remove(r) if r in self._engines else None)
        with self._lock:
            self._engines.append(ref)

    def track_module(self, module):
        ref = weakref.ref(module, lambda r: self._modules.remove(r) if r in self._modules else None)
        with self._lock:
            self._modules.append(ref)

    def track_zmq_context(self, ctx):
        ref = weakref.ref(ctx, lambda r: self._zmq_contexts.remove(r) if r in self._zmq_contexts else None)
        with self._lock:
            self._zmq_contexts.append(ref)

    def track_child_pid(self, pid):
        with self._lock:
            self._child_pids.append(pid)

    def cleanup_all(self):
        """Force-stop all tracked engines, modules, and ZMQ contexts."""
        # 1. Stop modules first (they hold ZMQ sockets)
        for ref in list(self._modules):
            module = ref()
            if module is not None and hasattr(module, 'stop'):
                try:
                    module.stop()
                except Exception:
                    pass

        # 2. Stop engines
        for ref in list(self._engines):
            engine = ref()
            if engine is not None and hasattr(engine, 'stop'):
                try:
                    engine.stop()
                except Exception:
                    pass

        # 3. Destroy any lingering ZMQ contexts
        for ref in list(self._zmq_contexts):
            ctx = ref()
            if ctx is not None and not ctx.closed:
                try:
                    ctx.destroy(linger=0)
                except Exception:
                    pass

        # 4. Kill any child processes we spawned
        for pid in list(self._child_pids):
            try:
                os.kill(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError, OSError):
                pass

        with self._lock:
            self._engines.clear()
            self._modules.clear()
            self._zmq_contexts.clear()
            self._child_pids.clear()


# Singleton tracker for the test session
_tracker = _ResourceTracker()

# Register atexit handler as a last-resort cleanup
atexit.register(_tracker.cleanup_all)


@pytest.fixture
def tmp_dead_letter_dir(tmp_path):
    """Provide a temporary directory for dead letter storage."""
    return tmp_path / "data"


@pytest.fixture
def dead_letter_store(tmp_dead_letter_dir):
    """Provide a DeadLetterStore using a temporary directory."""
    return DeadLetterStore(base_dir=tmp_dead_letter_dir)


@pytest.fixture
def make_message():
    """Factory fixture to create test Message objects."""
    def _make(
        msg_type=MessageType.EVENT,
        sender="test_module",
        event="test_event",
        payload=None,
        recipient=None,
        correlation_id=None,
        wait_timeout=None,
        run_timeout=None,
    ):
        return Message(
            msg_type=msg_type,
            sender=sender,
            event=event,
            payload=payload or {"data": "test"},
            recipient=recipient,
            correlation_id=correlation_id or str(uuid.uuid4()),
            wait_timeout=wait_timeout,
            run_timeout=run_timeout,
        )
    return _make


@pytest.fixture
def make_interface():
    """Factory fixture to create test Interface objects."""
    def _make(
        name="on_test",
        pattern=InterfacePattern.ON,
        event_type="test",
        durability=DurabilityLevel.ASYNC_FLUSH,
        backpressure=BackpressureStrategy.DROP_OLDEST,
        max_queue_depth=10000,
        wait_timeout=None,
    ):
        return Interface(
            name=name,
            pattern=pattern,
            event_type=event_type,
            durability=durability,
            backpressure=backpressure,
            max_queue_depth=max_queue_depth,
            wait_timeout=wait_timeout,
        )
    return _make


@pytest.fixture
def make_module_info(make_interface):
    """Factory fixture to create test ModuleInfo objects."""
    def _make(
        module_id="test_module",
        interfaces=None,
        metadata=None,
        family_name="",
    ):
        if interfaces is None:
            interfaces = [make_interface()]
        return ModuleInfo(
            module_id=module_id,
            interfaces=interfaces,
            metadata=metadata or {},
            family_name=family_name,
        )
    return _make


@pytest.fixture
def mock_zmq_context():
    """Provide a mocked ZMQ context."""
    with patch("zmq.Context") as mock_ctx:
        mock_socket = MagicMock()
        mock_ctx.return_value.socket.return_value = mock_socket
        yield mock_ctx.return_value, mock_socket


@pytest.fixture
def engine_endpoints():
    """Provide standard engine endpoint configuration for tests."""
    return {
        "registration": Endpoint("127.0.0.1", 15550),
        "event": Endpoint("127.0.0.1", 15551),
        "heartbeat": Endpoint("127.0.0.1", 15553),
    }


# ── Engine / Module Fixtures with Cleanup ─────────────────────────

@pytest.fixture
def make_engine(tmp_path):
    """Factory fixture to create a TycheEngine with automatic cleanup.

    The returned engine is tracked by the global resource tracker and
    will be stop()-ed during fixture teardown, even if the test fails.
    """
    engines = []

    def _make(
        registration_port=15550,
        event_port=15551,
        heartbeat_port=15553,
        **kwargs,
    ):
        from src.tyche.engine import TycheEngine
        engine = TycheEngine(
            registration_endpoint=Endpoint("127.0.0.1", registration_port),
            event_endpoint=Endpoint("127.0.0.1", event_port),
            heartbeat_endpoint=Endpoint("127.0.0.1", heartbeat_port),
            data_dir=str(tmp_path / "data"),
            **kwargs,
        )
        _tracker.track_engine(engine)
        engines.append(engine)
        return engine

    yield _make

    # Teardown: stop all engines created by this fixture invocation
    for engine in engines:
        if hasattr(engine, 'stop'):
            try:
                engine.stop()
            except Exception:
                pass
        # Ensure _running is reset even for unit-test engines
        engine._running = False


@pytest.fixture
def make_module():
    """Factory fixture to create a TycheModule with automatic cleanup.

    The returned module is tracked by the global resource tracker and
    will be stop()-ed during fixture teardown.
    """
    modules = []

    def _make(module_cls, **kwargs):
        module = module_cls(**kwargs)
        _tracker.track_module(module)
        modules.append(module)
        return module

    yield _make

    # Teardown: stop all modules created by this fixture
    for module in modules:
        if hasattr(module, 'stop'):
            try:
                module.stop()
            except Exception:
                pass


# ── Session-level Cleanup Hooks ───────────────────────────────────

def pytest_sessionfinish(session, exitstatus):
    """Called after whole test run finished, before exiting.

    Ensures all tracked ZMQ resources are cleaned up and any child
    processes spawned during tests are terminated.
    """
    _tracker.cleanup_all()


def pytest_unconfigure(config):
    """Called before test process exits — final safety net.

    Kills any Python child processes that may have been spawned by
    integration tests (e.g. multiprocessing-based module tests).
    """
    _tracker.cleanup_all()

    # Nuclear option: kill any lingering python child processes
    # that were spawned from this pytest process
    try:
        current_pid = os.getpid()
        result = subprocess.run(
            ["wmic", "process", "where",
             f"ParentProcessId={current_pid}",
             "get", "ProcessId"],
            capture_output=True, text=True, timeout=5,
        )
        for line in result.stdout.strip().splitlines():
            line = line.strip()
            if line.isdigit() and int(line) != current_pid:
                try:
                    os.kill(int(line), signal.SIGTERM)
                except (ProcessLookupError, PermissionError, OSError):
                    pass
    except Exception:
        pass  # Best-effort cleanup
