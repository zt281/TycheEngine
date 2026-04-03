"""Tests for TycheModule threading implementation."""

import threading
import time

import pytest
import zmq

from tyche.module import TycheModule
from tyche.types import Endpoint, InterfacePattern, DurabilityLevel


def test_module_has_run_method():
    """Module has a blocking run() method."""
    module = TycheModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="test_module"
    )

    assert hasattr(module, "run")
    assert hasattr(module, "stop")


def test_module_auto_generates_id():
    """Module auto-generates ID if not provided."""
    module = TycheModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555)
    )

    assert module.module_id is not None
    assert len(module.module_id) > 0


def test_module_adds_interface():
    """Module can add interfaces."""
    module = TycheModule(
        engine_endpoint=Endpoint("127.0.0.1", 5555),
        module_id="test_module"
    )

    def handler(payload):
        pass

    module.add_interface("on_data", handler, InterfacePattern.ON)

    assert len(module.interfaces) == 1
    assert module.interfaces[0].name == "on_data"
    assert module.interfaces[0].pattern == InterfacePattern.ON
