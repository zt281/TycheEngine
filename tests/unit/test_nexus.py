"""Unit tests for tyche_core.nexus module."""

import pytest
import zmq
import threading
import time
import json


def test_nexus_creation():
    from tyche_core.nexus import Nexus

    nexus = Nexus(endpoint="inproc://test_nexus")
    assert nexus.endpoint == "inproc://test_nexus"


def test_nexus_default_timeouts():
    from tyche_core.nexus import Nexus

    nexus = Nexus(endpoint="inproc://test_nexus2")
    assert nexus.heartbeat_interval_ms == 1000
    assert nexus.heartbeat_timeout_ms == 3000


def test_nexus_custom_timeouts():
    from tyche_core.nexus import Nexus

    nexus = Nexus(
        endpoint="inproc://test_nexus3",
        heartbeat_interval_ms=500,
        heartbeat_timeout_ms=1500
    )
    assert nexus.heartbeat_interval_ms == 500
    assert nexus.heartbeat_timeout_ms == 1500


def test_nexus_registers_module():
    from tyche_core.nexus import Nexus

    endpoint = "inproc://test_nexus_reg"
    nexus = Nexus(endpoint=endpoint)
    nexus.start()
    time.sleep(0.1)

    # Create module client
    ctx = zmq.Context()
    dealer = ctx.socket(zmq.DEALER)
    dealer.connect(endpoint)

    # Send READY
    dealer.send_multipart([
        b"READY",
        (1).to_bytes(4, "big"),  # protocol version
        json.dumps({
            "service_name": "test.module",
            "protocol_version": 1,
            "subscriptions": [],
            "heartbeat_interval_ms": 1000,
        }).encode()
    ])

    # Receive ACK
    frames = dealer.recv_multipart()
    assert frames[0] == b"ACK"
    assert len(frames) == 4  # ACK, correlation_id, assigned_id, heartbeat_interval

    dealer.close()
    ctx.term()
    nexus.stop()


def test_nexus_tracks_registered_modules():
    from tyche_core.nexus import Nexus

    endpoint = "inproc://test_nexus_track"
    nexus = Nexus(endpoint=endpoint)
    nexus.start()
    time.sleep(0.1)

    ctx = zmq.Context()
    dealer = ctx.socket(zmq.DEALER)
    dealer.connect(endpoint)

    # Register
    dealer.send_multipart([
        b"READY",
        (1).to_bytes(4, "big"),
        json.dumps({
            "service_name": "test.module.track",
            "protocol_version": 1,
            "subscriptions": [],
            "heartbeat_interval_ms": 100,
        }).encode()
    ])
    dealer.recv_multipart()  # ACK

    time.sleep(0.1)
    modules = nexus.get_modules()
    assert len(modules) == 1

    dealer.close()
    ctx.term()
    nexus.stop()


def test_calculate_backoff():
    from tyche_core.nexus import Nexus

    nexus = Nexus(endpoint="inproc://test_nexus_backoff")

    # First retry: small delay with jitter
    delay1 = nexus.calculate_backoff(1, base_ms=100, max_ms=5000)
    assert 80 <= delay1 <= 120  # ~100ms with ±20% jitter

    # Second retry: larger delay
    delay2 = nexus.calculate_backoff(2, base_ms=100, max_ms=5000)
    assert 160 <= delay2 <= 240  # ~200ms with ±20% jitter

    # Capped at max
    delay_large = nexus.calculate_backoff(100, base_ms=100, max_ms=5000)
    assert delay_large <= 5000


def test_nexus_heartbeat_tracking():
    from tyche_core.nexus import Nexus

    endpoint = "inproc://test_nexus_hb"
    nexus = Nexus(endpoint=endpoint, heartbeat_timeout_ms=500)
    nexus.start()
    time.sleep(0.1)

    ctx = zmq.Context()
    dealer = ctx.socket(zmq.DEALER)
    dealer.connect(endpoint)

    # Register
    dealer.send_multipart([
        b"READY",
        (1).to_bytes(4, "big"),
        json.dumps({
            "service_name": "test.module.hb",
            "protocol_version": 1,
            "subscriptions": [],
            "heartbeat_interval_ms": 100,
        }).encode()
    ])
    frames = dealer.recv_multipart()
    correlation_id = int.from_bytes(frames[1], "big")

    time.sleep(0.1)
    assert len(nexus.get_modules()) == 1

    dealer.close()
    ctx.term()
    nexus.stop()
