# tests/integration/test_nexus_lifecycle.py
import threading
import time
import zmq
import msgpack

# Use different ports per test to avoid port reuse race on Windows
NEXUS_ADDR_REG = "tcp://127.0.0.1:25555"
NEXUS_ADDR_HB = "tcp://127.0.0.1:25556"
NEXUS_ADDR_CMD = "tcp://127.0.0.1:25557"


def test_nexus_registration():
    """Module sends READY, Nexus replies READY_ACK with matching correlation_id."""
    from tyche.core.nexus import Nexus

    nexus = Nexus(address=NEXUS_ADDR_REG, cpu_core=None)
    nexus_thread = threading.Thread(target=nexus.run, daemon=True)
    nexus_thread.start()
    time.sleep(0.1)

    ctx = zmq.Context()
    dealer = ctx.socket(zmq.DEALER)
    dealer.setsockopt_string(zmq.IDENTITY, "test.mod")
    dealer.connect(NEXUS_ADDR_REG)
    time.sleep(0.05)

    try:
        # Send READY with correlation_id=1
        dealer.send_multipart([
            b"TYCHE", b"READY", b"1", b"test.mod", b"0"
        ])

        # Expect READY_ACK with correlation_id=1
        dealer.setsockopt(zmq.RCVTIMEO, 1000)
        frames = dealer.recv_multipart()
        assert frames[0] == b"TYCHE"
        assert frames[1] == b"READY_ACK"
        assert frames[2] == b"1"  # correlation_id matches

        # Check registry
        assert "test.mod" in nexus.registry
    finally:
        nexus.stop()
        dealer.close()
        ctx.term()
        time.sleep(0.05)


def test_nexus_heartbeat():
    """Nexus sends HB frames to registered modules."""
    from tyche.core.nexus import Nexus

    nexus = Nexus(address=NEXUS_ADDR_HB, cpu_core=None)
    nexus_thread = threading.Thread(target=nexus.run, daemon=True)
    nexus_thread.start()
    time.sleep(0.1)

    ctx = zmq.Context()
    dealer = ctx.socket(zmq.DEALER)
    dealer.setsockopt_string(zmq.IDENTITY, "test.hb")
    dealer.connect(NEXUS_ADDR_HB)
    time.sleep(0.05)

    # Register first
    dealer.send_multipart([b"TYCHE", b"READY", b"1", b"test.hb", b"0"])
    dealer.recv_multipart()  # READY_ACK

    try:
        # Wait up to 3 seconds for HB (HB_INTERVAL_S is 1.0s)
        dealer.setsockopt(zmq.RCVTIMEO, 3000)
        frames = dealer.recv_multipart()  # Wait for HB
        assert frames[0] == b"TYCHE"
        assert frames[1] == b"HB"
    finally:
        nexus.stop()
        dealer.close()
        ctx.term()
        time.sleep(0.05)


def test_nexus_stop_command():
    """Nexus handles STATUS command and replies with REPLY frame."""
    from tyche.core.nexus import Nexus

    nexus = Nexus(address=NEXUS_ADDR_CMD, cpu_core=None)
    nexus_thread = threading.Thread(target=nexus.run, daemon=True)
    nexus_thread.start()
    time.sleep(0.1)

    ctx = zmq.Context()
    dealer = ctx.socket(zmq.DEALER)
    dealer.setsockopt_string(zmq.IDENTITY, "test.cmd")
    dealer.connect(NEXUS_ADDR_CMD)
    time.sleep(0.05)

    # Register
    dealer.send_multipart([b"TYCHE", b"READY", b"1", b"test.cmd", b"0"])
    dealer.recv_multipart()  # READY_ACK

    try:
        # Send STATUS command
        dealer.send_multipart([
            b"TYCHE", b"CMD", b"STATUS", msgpack.packb({}, use_bin_type=True)
        ])

        dealer.setsockopt(zmq.RCVTIMEO, 1000)
        frames = dealer.recv_multipart()
        assert frames[0] == b"TYCHE"
        assert frames[1] == b"REPLY"
        # status = b"OK"
    finally:
        nexus.stop()
        dealer.close()
        ctx.term()
        time.sleep(0.05)
