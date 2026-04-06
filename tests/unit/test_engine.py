"""Tests for TycheEngine."""
import pytest
import zmq
import asyncio
from unittest.mock import Mock, patch
from tyche.engine import TycheEngine
from tyche.types import Endpoint


def test_engine_init():
    """Engine initializes with endpoints."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 5555),
        event_endpoint=Endpoint("127.0.0.1", 5556),
        heartbeat_endpoint=Endpoint("127.0.0.1", 5557)
    )
    assert engine.registration_endpoint.port == 5555


def test_engine_module_registry():
    """Engine can register modules."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 5555),
        event_endpoint=Endpoint("127.0.0.1", 5556),
        heartbeat_endpoint=Endpoint("127.0.0.1", 5557),
    )

    module_info = Mock()
    module_info.module_id = "zeus3f7a9c"
    module_info.interfaces = []

    engine.register_module(module_info)

    assert "zeus3f7a9c" in engine.modules


def test_engine_unregister_module():
    """Engine can unregister modules."""
    engine = TycheEngine(
        registration_endpoint=Endpoint("127.0.0.1", 5555),
        event_endpoint=Endpoint("127.0.0.1", 5556),
        heartbeat_endpoint=Endpoint("127.0.0.1", 5557),
    )

    module_info = Mock()
    module_info.module_id = "zeus3f7a9c"
    module_info.interfaces = []

    engine.register_module(module_info)
    engine.unregister_module("zeus3f7a9c")

    assert "zeus3f7a9c" not in engine.modules
