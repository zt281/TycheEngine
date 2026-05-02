"""Integration tests for handle_* request-response via ACK channel."""

import time

from tyche.engine import TycheEngine
from tyche.module import TycheModule
from tyche.types import Endpoint


def test_handle_response_round_trip():
    """Module A calls send_event_with_response; Module B handles and returns result."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 26000),
        event_endpoint=Endpoint("127.0.0.1", 26002),
        heartbeat_endpoint=Endpoint("127.0.0.1", 26004),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 26006),
    )
    engine.start_nonblocking()
    time.sleep(0.3)

    class ResponderModule(TycheModule):
        def handle_broadcasted_query(self, payload: dict) -> dict:
            return {"x": 1, "q": payload.get("q")}

    responder = ResponderModule(
        engine_endpoint=Endpoint("127.0.0.1", 26000),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 26006),
        module_id="responder_001",
    )

    caller = TycheModule(
        engine_endpoint=Endpoint("127.0.0.1", 26000),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 26006),
        module_id="caller_001",
    )

    try:
        responder.start()
        time.sleep(0.3)
        caller.start()
        time.sleep(0.3)

        result = caller.send_event_with_response(
            "handle_broadcasted_query",
            {"q": "ping"},
            timeout_ms=3000,
        )

        assert result is not None, "Request timed out"
        assert result["x"] == 1
        assert result["q"] == "ping"
    finally:
        caller.stop()
        responder.stop()
        engine.stop()
