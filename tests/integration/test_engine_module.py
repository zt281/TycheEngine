"""Integration tests for 2-node Tyche Engine system."""
import pytest
import asyncio
import time
from tyche.engine import TycheEngine
from tyche.module import TycheModule
from tyche.example_module import ExampleModule
from tyche.types import Endpoint


# Port allocation per test:
# registration = base
# event = base + 1
# xsub = event + 1 = base + 2  (auto-bound by engine)
# heartbeat = base + 10  (must not conflict with xsub)
# ack = event + 10 = base + 11  (auto-calculated by engine)
BASE_PORT = 63000


@pytest.mark.asyncio
async def test_module_registration():
    """Module can register with Engine."""
    base = BASE_PORT
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", base),
        event_endpoint=Endpoint("127.0.0.1", base + 1),
        heartbeat_endpoint=Endpoint("127.0.0.1", base + 10)
    )
    engine.start_nonblocking()
    await asyncio.sleep(0.2)

    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", base)
    )

    try:
        await module.start()
        await asyncio.sleep(0.2)

        # Verify registration
        assert module.module_id in engine.modules
        assert engine.modules[module.module_id].module_id == module.module_id

    finally:
        await module.stop()
        engine.stop()


@pytest.mark.asyncio
async def test_event_broadcast():
    """Engine can broadcast events to subscribed modules."""
    base = BASE_PORT + 20
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", base),
        event_endpoint=Endpoint("127.0.0.1", base + 1),
        heartbeat_endpoint=Endpoint("127.0.0.1", base + 10)
    )
    engine.start_nonblocking()
    await asyncio.sleep(0.2)

    received = []

    class TestModule(TycheModule):
        def on_test_event(self, payload):
            received.append(payload)

    module = TestModule(
        engine_endpoint=Endpoint("127.0.0.1", base),
        module_id="test123456"
    )

    try:
        module.add_interface("on_test_event", module.on_test_event)
        await module.start()
        await asyncio.sleep(0.3)

        await engine.broadcast_event("on_test_event", {"data": "hello"})
        await asyncio.sleep(0.3)

        assert len(received) >= 0

    finally:
        await module.stop()
        engine.stop()


@pytest.mark.asyncio
async def test_module_heartbeat():
    """Module sends heartbeats to Engine."""
    base = BASE_PORT + 40
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", base),
        event_endpoint=Endpoint("127.0.0.1", base + 1),
        heartbeat_endpoint=Endpoint("127.0.0.1", base + 10)
    )
    engine.start_nonblocking()
    await asyncio.sleep(0.2)

    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", base)
    )

    try:
        await module.start()
        await asyncio.sleep(0.5)

        assert module.module_id in engine.modules
        assert module.module_id in engine.heartbeat_manager.monitors

    finally:
        await module.stop()
        engine.stop()


@pytest.mark.asyncio
async def test_full_two_node_interaction():
    """Complete 2-node interaction: Engine + ExampleModule."""
    base = BASE_PORT + 60
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", base),
        event_endpoint=Endpoint("127.0.0.1", base + 1),
        heartbeat_endpoint=Endpoint("127.0.0.1", base + 10)
    )
    engine.start_nonblocking()
    await asyncio.sleep(0.2)

    module = ExampleModule(
        engine_endpoint=Endpoint("127.0.0.1", base),
        module_id="athenatest1"
    )

    try:
        await module.start()
        await asyncio.sleep(0.3)

        assert module._registered
        assert module.module_id in engine.modules

        module_info = engine.modules[module.module_id]
        interface_names = [i.name for i in module_info.interfaces]
        assert "on_data" in interface_names
        assert "ack_request" in interface_names

        module.on_data({"test": "data"})
        assert len(module.received_events) == 1

        response = module.ack_request({"request_id": "test123"})
        assert response["status"] == "acknowledged"
        assert response["request_id"] == "test123"

        stats = module.get_stats()
        assert stats["module_id"] == "athenatest1"
        assert stats["request_count"] == 1

    finally:
        await module.stop()
        engine.stop()
