"""Integration test for Bus pub/sub.

NOTE: These tests require actual ZMQ communication and may not pass
in all environments. Run with: pytest tests/integration/ -v
"""

import pytest
import zmq
import threading
import time

from tyche_core.bus import Bus
from tyche_client.types import Tick
from tyche_client.serialization import encode


@pytest.fixture
def endpoints():
    """Generate unique endpoints for each test."""
    import uuid
    uid = uuid.uuid4().hex[:8]
    return {
        "xsub": f"inproc://test_xsub_{uid}",
        "xpub": f"inproc://test_xpub_{uid}",
    }


@pytest.fixture
def bus_service(endpoints):
    """Start Bus service."""
    bus = Bus(
        xsub_endpoint=endpoints["xsub"],
        xpub_endpoint=endpoints["xpub"],
    )
    bus.start()
    time.sleep(0.1)

    yield bus

    bus.stop()


def test_pub_sub_message_flow(endpoints, bus_service):
    """Test that messages flow from pub to sub through Bus."""
    ctx = zmq.Context()

    # Create publisher
    pub = ctx.socket(zmq.PUB)
    pub.connect(endpoints["xsub"])

    # Create subscriber
    sub = ctx.socket(zmq.SUB)
    sub.connect(endpoints["xpub"])
    sub.setsockopt(zmq.SUBSCRIBE, b"TEST")

    time.sleep(0.2)

    # Publish message
    tick = Tick(
        instrument_id=12345,
        price=150.25,
        size=100.0,
        side="buy",
        timestamp_ns=1711632000000000000,
    )

    pub.send_multipart([b"TEST.TOPIC", encode(tick)])

    # Receive message
    topic, payload = sub.recv_multipart()
    assert topic == b"TEST.TOPIC"

    from tyche_client.serialization import decode
    decoded = decode(payload)
    assert decoded.instrument_id == 12345
    assert decoded.price == 150.25

    pub.close()
    sub.close()
    ctx.term()


def test_topic_filtering(endpoints, bus_service):
    """Test that subscribers only receive matching topics."""
    ctx = zmq.Context()

    pub = ctx.socket(zmq.PUB)
    pub.connect(endpoints["xsub"])

    # Subscriber for AAPL only
    sub = ctx.socket(zmq.SUB)
    sub.connect(endpoints["xpub"])
    sub.setsockopt(zmq.SUBSCRIBE, b"EQUITY.NYSE.AAPL")

    time.sleep(0.2)

    # Publish AAPL tick
    pub.send_multipart([b"EQUITY.NYSE.AAPL.Tick", b"aapl_data"])

    # Publish MSFT tick
    pub.send_multipart([b"EQUITY.NYSE.MSFT.Tick", b"msft_data"])

    # Only AAPL should be received
    topic, payload = sub.recv_multipart()
    assert topic == b"EQUITY.NYSE.AAPL.Tick"
    assert payload == b"aapl_data"

    # Check no more messages (with timeout)
    sub.setsockopt(zmq.RCVTIMEO, 100)
    with pytest.raises(zmq.Again):
        sub.recv_multipart()

    pub.close()
    sub.close()
    ctx.term()
