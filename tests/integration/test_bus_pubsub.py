# tests/integration/test_bus_pubsub.py
import threading
import time
import zmq

# Use ephemeral ports to avoid conflicts with real services
BUS_XSUB = "tcp://127.0.0.1:25556"
BUS_XPUB = "tcp://127.0.0.1:25557"

def test_bus_forwards_published_message():
    """Bus must forward a published message to all subscribers."""
    from tyche.core.bus import Bus

    bus = Bus(xsub_address=BUS_XSUB, xpub_address=BUS_XPUB, cpu_core=None, sndhwm=1000)
    bus_thread = threading.Thread(target=bus.run, daemon=True)
    bus_thread.start()
    time.sleep(0.1)  # Let proxy start

    ctx = zmq.Context()

    # Subscriber connects to XPUB
    sub = ctx.socket(zmq.SUB)
    sub.setsockopt_string(zmq.SUBSCRIBE, "")
    sub.connect(BUS_XPUB)
    time.sleep(0.05)

    # Publisher connects to XSUB
    pub = ctx.socket(zmq.PUB)
    pub.connect(BUS_XSUB)
    time.sleep(0.05)

    # Send message
    pub.send_multipart([b"TEST.TOPIC", b"payload"])

    # Receive with timeout
    sub.setsockopt(zmq.RCVTIMEO, 500)
    try:
        frames = sub.recv_multipart()
        assert frames[0] == b"TEST.TOPIC"
        assert frames[1] == b"payload"
    finally:
        bus.stop()
        sub.close()
        pub.close()
        ctx.term()

def test_bus_topic_filtering():
    """Subscribers must only receive matching topics."""
    from tyche.core.bus import Bus

    bus = Bus(xsub_address=BUS_XSUB, xpub_address=BUS_XPUB, cpu_core=None, sndhwm=1000)
    bus_thread = threading.Thread(target=bus.run, daemon=True)
    bus_thread.start()
    time.sleep(0.1)

    ctx = zmq.Context()

    sub = ctx.socket(zmq.SUB)
    sub.setsockopt_string(zmq.SUBSCRIBE, "MATCH.")
    sub.connect(BUS_XPUB)
    time.sleep(0.05)

    pub = ctx.socket(zmq.PUB)
    pub.connect(BUS_XSUB)
    time.sleep(0.05)

    # Send two messages - only one matches
    pub.send_multipart([b"MATCH.topic", b"yes"])
    pub.send_multipart([b"NOMATCH.topic", b"no"])

    sub.setsockopt(zmq.RCVTIMEO, 500)
    try:
        frames = sub.recv_multipart()
        assert frames[0] == b"MATCH.topic"
        assert frames[1] == b"yes"
        # Should not receive NOMATCH.topic
    finally:
        bus.stop()
        sub.close()
        pub.close()
        ctx.term()
