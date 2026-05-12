"""Integration tests for the job (request/response) communication pattern."""

import time

import pytest

from tyche.engine import TycheEngine
from tyche.module import TycheModule
from tyche.types import Endpoint


# ── Helper Modules ────────────────────────────────────────────────────


class ComputeHandlerModule(TycheModule):
    """Module that handles 'compute' job requests."""

    def handle_compute(self, payload: dict) -> dict:
        """Process a compute job and return a result."""
        a = payload.get("a", 0)
        b = payload.get("b", 0)
        return {"sum": a + b}


class ComputeRequesterModule(TycheModule):
    """Module that declares it produces 'compute' job requests."""

    def request_compute(self):
        """Producer declaration for compute job requests."""
        pass


class RoundRobinHandlerA(TycheModule):
    """Handler A for round-robin testing."""

    def __init__(self, *args, results: list, **kwargs):
        self._results = results
        super().__init__(*args, **kwargs)

    def handle_work(self, payload: dict) -> dict:
        self._results.append("A")
        return {"handler": "A", "task": payload.get("task")}


class RoundRobinHandlerB(TycheModule):
    """Handler B for round-robin testing."""

    def __init__(self, *args, results: list, **kwargs):
        self._results = results
        super().__init__(*args, **kwargs)

    def handle_work(self, payload: dict) -> dict:
        self._results.append("B")
        return {"handler": "B", "task": payload.get("task")}


class WorkRequesterModule(TycheModule):
    """Module that declares it produces 'work' job requests."""

    def request_work(self):
        """Producer declaration for work job requests."""
        pass


# ── Port allocation helper ────────────────────────────────────────────

# Each test uses a unique port range to avoid conflicts with parallel test runs
# Port ranges: 25000-25099 (test1), 25100-25199 (test2), etc.


# ── Tests ─────────────────────────────────────────────────────────────


def test_job_request_response_roundtrip():
    """Full job round-trip: requester sends request, handler processes, requester gets response."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 25000),
        event_endpoint=Endpoint("127.0.0.1", 25002),
        heartbeat_endpoint=Endpoint("127.0.0.1", 25004),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25006),
        job_endpoint=Endpoint("127.0.0.1", 25008),
    )
    engine.start_nonblocking()
    time.sleep(0.3)

    handler = ComputeHandlerModule(
        engine_endpoint=Endpoint("127.0.0.1", 25000),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25006),
        module_id="compute_handler",
    )

    requester = ComputeRequesterModule(
        engine_endpoint=Endpoint("127.0.0.1", 25000),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25006),
        module_id="compute_requester",
    )

    try:
        handler.start()
        time.sleep(0.3)
        requester.start()
        time.sleep(0.3)

        # Both modules registered
        assert handler._registered
        assert requester._registered

        # Verify engine knows about the handler
        assert "compute" in engine._job_handlers
        assert "compute_handler" in engine._job_handlers["compute"]

        # Send a job request
        result = requester.request_event("compute", {"a": 3, "b": 7}, timeout=2.0)

        assert "result" in result
        assert result["result"]["sum"] == 10
    finally:
        requester.stop()
        handler.stop()
        engine.stop()


def test_job_no_handler_returns_error():
    """Job request for a topic with no registered handler gets error response."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 25100),
        event_endpoint=Endpoint("127.0.0.1", 25102),
        heartbeat_endpoint=Endpoint("127.0.0.1", 25104),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25106),
        job_endpoint=Endpoint("127.0.0.1", 25108),
    )
    engine.start_nonblocking()
    time.sleep(0.3)

    # This module has request_compute declaration but we won't register any handler
    requester = ComputeRequesterModule(
        engine_endpoint=Endpoint("127.0.0.1", 25100),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25106),
        module_id="lonely_requester",
    )

    try:
        requester.start()
        time.sleep(0.3)
        assert requester._registered

        # Send a job request for topic with no handler — engine returns error
        result = requester.request_event("compute", {"a": 1, "b": 2}, timeout=2.0)

        assert "error" in result
        assert "No handler" in result["error"]
    finally:
        requester.stop()
        engine.stop()


def test_job_timeout():
    """Job request with very short timeout raises TimeoutError when no handler responds."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 25200),
        event_endpoint=Endpoint("127.0.0.1", 25202),
        heartbeat_endpoint=Endpoint("127.0.0.1", 25204),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25206),
        job_endpoint=Endpoint("127.0.0.1", 25208),
    )
    engine.start_nonblocking()
    time.sleep(0.3)

    class SlowHandlerModule(TycheModule):
        """Handler that takes too long to respond."""

        def handle_slow_task(self, payload: dict) -> dict:
            time.sleep(5.0)  # Much longer than timeout
            return {"done": True}

    class SlowRequesterModule(TycheModule):
        def request_slow_task(self):
            pass

    handler = SlowHandlerModule(
        engine_endpoint=Endpoint("127.0.0.1", 25200),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25206),
        module_id="slow_handler",
    )

    requester = SlowRequesterModule(
        engine_endpoint=Endpoint("127.0.0.1", 25200),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25206),
        module_id="impatient_requester",
    )

    try:
        handler.start()
        time.sleep(0.3)
        requester.start()
        time.sleep(0.3)

        # Very short timeout — handler won't respond in time
        with pytest.raises(TimeoutError, match="timed out"):
            requester.request_event("slow_task", {"data": "x"}, timeout=0.3)
    finally:
        requester.stop()
        handler.stop()
        engine.stop()


def test_job_round_robin_distribution():
    """Multiple handlers for the same topic receive jobs in round-robin order."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 25300),
        event_endpoint=Endpoint("127.0.0.1", 25302),
        heartbeat_endpoint=Endpoint("127.0.0.1", 25304),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25306),
        job_endpoint=Endpoint("127.0.0.1", 25308),
    )
    engine.start_nonblocking()
    time.sleep(0.3)

    results = []

    handler_a = RoundRobinHandlerA(
        engine_endpoint=Endpoint("127.0.0.1", 25300),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25306),
        module_id="rr_handler_a",
        results=results,
    )

    handler_b = RoundRobinHandlerB(
        engine_endpoint=Endpoint("127.0.0.1", 25300),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25306),
        module_id="rr_handler_b",
        results=results,
    )

    requester = WorkRequesterModule(
        engine_endpoint=Endpoint("127.0.0.1", 25300),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25306),
        module_id="rr_requester",
    )

    try:
        handler_a.start()
        time.sleep(0.3)
        handler_b.start()
        time.sleep(0.3)
        requester.start()
        time.sleep(0.3)

        # Verify both handlers registered
        assert handler_a._registered
        assert handler_b._registered
        assert requester._registered
        assert "work" in engine._job_handlers
        assert len(engine._job_handlers["work"]) == 2

        # Send multiple jobs and collect responses
        responses = []
        for i in range(4):
            resp = requester.request_event("work", {"task": i}, timeout=2.0)
            responses.append(resp)

        # All requests got responses
        assert len(responses) == 4
        for resp in responses:
            assert "result" in resp
            assert "handler" in resp["result"]

        # Verify round-robin: both handlers got work
        handlers_used = [r["result"]["handler"] for r in responses]
        assert "A" in handlers_used
        assert "B" in handlers_used

        # With round-robin, 4 jobs across 2 handlers should give 2 each
        assert handlers_used.count("A") == 2
        assert handlers_used.count("B") == 2
    finally:
        requester.stop()
        handler_b.stop()
        handler_a.stop()
        engine.stop()
