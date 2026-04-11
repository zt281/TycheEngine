"""Integration tests for 2-node Tyche Engine system.

Tests actual Engine + Module interaction using real ZMQ sockets.
"""

import time

from tyche.engine import TycheEngine
from tyche.example_module import ExampleModule
from tyche.module import TycheModule
from tyche.types import Endpoint


def test_module_registration():
    """Module registers with Engine and appears in the module registry."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 24000),
        event_endpoint=Endpoint("127.0.0.1", 24002),
        heartbeat_endpoint=Endpoint("127.0.0.1", 24004),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 24006),
    )
    engine.start_nonblocking()
    time.sleep(0.3)

    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 24000),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 24006),
        module_id="reg_test_mod",
    )

    try:
        module.start_nonblocking()
        time.sleep(0.5)

        assert module._registered
        assert "reg_test_mod" in engine.modules
        assert engine.modules["reg_test_mod"].module_id == "reg_test_mod"
    finally:
        module.stop()
        engine.stop()


def test_event_pubsub():
    """Module publishes an event and another module receives it via XPUB/XSUB proxy."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 24100),
        event_endpoint=Endpoint("127.0.0.1", 24102),
        heartbeat_endpoint=Endpoint("127.0.0.1", 24104),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 24106),
    )
    engine.start_nonblocking()
    time.sleep(0.3)

    received = []

    class ReceiverModule(TycheModule):
        def on_test_event(self, payload: dict) -> None:
            received.append(payload)

    receiver = ReceiverModule(
        engine_endpoint=Endpoint("127.0.0.1", 24100),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 24106),
        module_id="receiver_001",
    )
    receiver.add_interface("on_test_event", receiver.on_test_event)

    sender = TycheModule(
        engine_endpoint=Endpoint("127.0.0.1", 24100),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 24106),
        module_id="sender_001",
    )

    try:
        receiver.start_nonblocking()
        time.sleep(0.3)
        sender.start_nonblocking()
        time.sleep(0.5)

        # Send event through the proxy
        sender.send_event("on_test_event", {"data": "hello"})
        time.sleep(0.5)

        assert len(received) >= 1, f"Expected at least 1 event, got {len(received)}"
        assert received[0]["data"] == "hello"
    finally:
        sender.stop()
        receiver.stop()
        engine.stop()


def test_module_heartbeat_keeps_alive():
    """Module sends heartbeats to Engine and stays registered."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 24200),
        event_endpoint=Endpoint("127.0.0.1", 24202),
        heartbeat_endpoint=Endpoint("127.0.0.1", 24204),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 24206),
    )
    engine.start_nonblocking()
    time.sleep(0.3)

    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 24200),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 24206),
        module_id="hb_test_mod",
    )

    try:
        module.start_nonblocking()
        time.sleep(0.5)

        assert "hb_test_mod" in engine.modules
        assert "hb_test_mod" in engine.heartbeat_manager.monitors
    finally:
        module.stop()
        engine.stop()


def test_full_two_node_interaction():
    """Complete 2-node interaction: Engine + ExampleModule with handler dispatch."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 24300),
        event_endpoint=Endpoint("127.0.0.1", 24302),
        heartbeat_endpoint=Endpoint("127.0.0.1", 24304),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 24306),
    )
    engine.start_nonblocking()
    time.sleep(0.3)

    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", 24300),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 24306),
        module_id="athenatest1",
    )

    try:
        module.start_nonblocking()
        time.sleep(0.5)

        # Registration succeeded
        assert module._registered
        assert "athenatest1" in engine.modules

        # Interfaces are discovered
        module_info = engine.modules["athenatest1"]
        interface_names = [i.name for i in module_info.interfaces]
        assert "on_data" in interface_names
        assert "ack_request" in interface_names

        # Direct handler invocation works
        module.on_data({"test": "data"})
        assert len(module.received_events) == 1
        assert module.received_events[0]["payload"]["test"] == "data"

        response = module.ack_request({"request_id": "test123"})
        assert response["status"] == "acknowledged"
        assert response["request_id"] == "test123"

        stats = module.get_stats()
        assert stats["module_id"] == "athenatest1"
        assert stats["request_count"] == 1
        assert stats["events_received"] == 1
    finally:
        module.stop()
        engine.stop()
