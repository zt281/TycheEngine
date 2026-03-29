"""Unit tests for tyche_client.module module."""

import pytest
import json
import tempfile
import os


def test_module_creation():
    from tyche_client.module import Module

    class TestModule(Module):
        service_name = "test.module"

        def on_init(self):
            pass

        def on_start(self):
            pass

        def on_stop(self):
            pass

    module = TestModule(
        nexus_endpoint="inproc://test_nexus",
        bus_xsub_endpoint="inproc://test_xsub",
        bus_xpub_endpoint="inproc://test_xpub",
    )
    assert module.service_name == "test.module"


def test_module_loads_config():
    from tyche_client.module import Module

    config = {"strategy": {"name": "test"}}

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump(config, f)
        f.flush()
        config_path = f.name

    try:
        class TestModule(Module):
            service_name = "test.module"

            def on_init(self):
                pass

            def on_start(self):
                pass

            def on_stop(self):
                pass

        module = TestModule(
            nexus_endpoint="inproc://test_nexus",
            bus_xsub_endpoint="inproc://test_xsub",
            bus_xpub_endpoint="inproc://test_xpub",
            config_path=config_path,
        )
        module._load_config()
        assert module._config["strategy"]["name"] == "test"
    finally:
        os.unlink(config_path)


def test_module_encode_decode():
    from tyche_client.module import Module
    from tyche_client.types import Tick

    class TestModule(Module):
        service_name = "test.module"

        def on_init(self):
            pass

        def on_start(self):
            pass

        def on_stop(self):
            pass

    module = TestModule(
        nexus_endpoint="inproc://test_nexus",
        bus_xsub_endpoint="inproc://test_xsub",
        bus_xpub_endpoint="inproc://test_xpub",
    )

    tick = Tick(
        instrument_id=12345,
        price=150.25,
        size=100.0,
        side="buy",
        timestamp_ns=1711632000000000000
    )

    data = module._encode(tick)
    decoded = module._decode(data)
    assert decoded == tick


def test_module_has_default_handlers():
    from tyche_client.module import Module

    class TestModule(Module):
        service_name = "test.module"

        def on_init(self):
            pass

        def on_start(self):
            pass

        def on_stop(self):
            pass

    module = TestModule(
        nexus_endpoint="inproc://test_nexus",
        bus_xsub_endpoint="inproc://test_xsub",
        bus_xpub_endpoint="inproc://test_xpub",
    )

    assert "Tick" in module._handlers
    assert "Quote" in module._handlers
    assert "Trade" in module._handlers
    assert "Bar" in module._handlers
    assert "OrderEvent" in module._handlers
