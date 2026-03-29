"""Integration test for Nexus module registration.

NOTE: These tests require actual ZMQ communication and may not pass
in all environments. Run with: pytest tests/integration/ -v
"""

import pytest
import zmq
import threading
import time
import json

from tyche_core.nexus import Nexus
from tyche_core.bus import Bus
from tyche_client.module import Module


class TestModule(Module):
    """Test module for integration tests."""

    service_name = "test.integration"
    service_version = "1.0.0"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.init_called = False
        self.start_called = False
        self.stop_called = False

    def on_init(self):
        self.init_called = True

    def on_start(self):
        self.start_called = True

    def on_stop(self):
        self.stop_called = True


@pytest.fixture
def endpoints():
    """Generate unique endpoints for each test."""
    import uuid
    uid = uuid.uuid4().hex[:8]
    return {
        "nexus": f"inproc://test_nexus_{uid}",
        "xsub": f"inproc://test_xsub_{uid}",
        "xpub": f"inproc://test_xpub_{uid}",
    }


@pytest.fixture
def core_services(endpoints):
    """Start Nexus and Bus services."""
    nexus = Nexus(endpoint=endpoints["nexus"])
    bus = Bus(
        xsub_endpoint=endpoints["xsub"],
        xpub_endpoint=endpoints["xpub"],
    )

    bus.start()
    nexus.start()
    time.sleep(0.1)

    yield nexus, bus

    nexus.stop()
    bus.stop()


def test_module_registers_with_nexus(endpoints, core_services):
    """Test that a module can register with Nexus."""
    nexus, bus = core_services

    module = TestModule(
        nexus_endpoint=endpoints["nexus"],
        bus_xsub_endpoint=endpoints["xsub"],
        bus_xpub_endpoint=endpoints["xpub"],
    )

    # Run module in background thread
    thread = threading.Thread(target=module.run, daemon=True)
    thread.start()

    # Wait for registration
    time.sleep(0.3)

    # Check that module is registered
    modules = nexus.get_modules()
    assert len(modules) == 1

    module_key = list(modules.keys())[0]
    assert modules[module_key].service_name == "test.integration"


def test_module_receives_start_command(endpoints, core_services):
    """Test that module receives START command."""
    nexus, bus = core_services

    module = TestModule(
        nexus_endpoint=endpoints["nexus"],
        bus_xsub_endpoint=endpoints["xsub"],
        bus_xpub_endpoint=endpoints["xpub"],
    )

    thread = threading.Thread(target=module.run, daemon=True)
    thread.start()

    time.sleep(0.3)

    # Get assigned ID and send START
    modules = nexus.get_modules()
    assigned_id = list(modules.values())[0].assigned_id

    from tyche_core.protocol import CMD_START
    nexus.send_command(assigned_id, CMD_START)

    time.sleep(0.2)

    assert module.start_called


def test_module_receives_stop_command(endpoints, core_services):
    """Test that module receives STOP command and shuts down."""
    nexus, bus = core_services

    module = TestModule(
        nexus_endpoint=endpoints["nexus"],
        bus_xsub_endpoint=endpoints["xsub"],
        bus_xpub_endpoint=endpoints["xpub"],
    )

    thread = threading.Thread(target=module.run, daemon=True)
    thread.start()

    time.sleep(0.3)

    modules = nexus.get_modules()
    assigned_id = list(modules.values())[0].assigned_id

    from tyche_core.protocol import CMD_STOP
    nexus.send_command(assigned_id, CMD_STOP)

    time.sleep(0.3)

    assert module.stop_called
