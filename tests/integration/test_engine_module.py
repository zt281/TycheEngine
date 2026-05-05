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
        module.start()
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
        def on_streaming_test_event(self, payload: dict) -> None:
            received.append(payload)

    receiver = ReceiverModule(
        engine_endpoint=Endpoint("127.0.0.1", 24100),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 24106),
        module_id="receiver_001",
    )

    sender = TycheModule(
        engine_endpoint=Endpoint("127.0.0.1", 24100),
        heartbeat_receive_endpoint=Endpoint("127.0.0.1", 24106),
        module_id="sender_001",
    )

    try:
        receiver.start()
        time.sleep(0.3)
        sender.start()
        time.sleep(0.5)

        # Send event through the proxy using handler_name
        sender.send_event("streaming_test_event", {"data": "hello"})
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
        module.start()
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
        module.start()
        time.sleep(0.5)

        # Registration succeeded
        assert module._registered
        assert "athenatest1" in engine.modules

        # Interfaces are discovered
        module_info = engine.modules["athenatest1"]
        interface_names = [i.name for i in module_info.interfaces]
        assert "broadcasted_ping" in interface_names

        # Direct handler invocation works
        module.on_broadcasted_ping({"sender": "other", "value": 42})
        assert module.ping_count == 1

        stats = module.get_stats()
        assert stats["module_id"] == "athenatest1"
        assert stats["ping_count"] == 1
    finally:
        module.stop()
        engine.stop()
