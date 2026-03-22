"""
Integration tests for RecordingModule and ReplayBus.

Bus port assignments (distinct from all other test fixtures):
  Recording phase: NEXUS=35555, BUS1_XSUB=35556, BUS1_XPUB=35557
  Replay phase:    BUS2_XSUB=35558, BUS2_XPUB=35559
"""
import os
import time
import threading

import msgpack
import pytest
import zmq
import tyche_core

NEXUS     = "tcp://127.0.0.1:35555"
BUS1_XSUB = "tcp://127.0.0.1:35556"
BUS1_XPUB = "tcp://127.0.0.1:35557"
BUS2_XSUB = "tcp://127.0.0.1:35558"
BUS2_XPUB = "tcp://127.0.0.1:35559"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_payload() -> bytes:
    q = tyche_core.PyQuote(42, 99.5, 10.0, 100.0, 5.0, 12345)
    return bytes(tyche_core.serialize_quote(q))


def _publish_n(pub_sock: zmq.Socket, topic: str, payload: bytes, n: int, gap_s: float = 0.02):
    for _ in range(n):
        pub_sock.send_multipart([
            topic.encode(),
            time.time_ns().to_bytes(8, "big"),
            payload,
        ])
        if gap_s > 0:
            time.sleep(gap_s)


# ---------------------------------------------------------------------------
# Test 1: RecordingModule writes a valid .tyche file
# ---------------------------------------------------------------------------

def test_recording_module_writes_tyche_file(tmp_path):
    from tyche.core.nexus import Nexus
    from tyche.core.bus import Bus
    from tyche.backtest.recording import RecordingModule

    file_path = str(tmp_path / "test.tyche")
    n_msgs = 3
    topic = "EQUITY.NYSE.AAPL.QUOTE"
    payload = _make_payload()

    # Start engine
    nexus = Nexus(address=NEXUS, cpu_core=None)
    bus1 = Bus(xsub_address=BUS1_XSUB, xpub_address=BUS1_XPUB, cpu_core=None)
    threading.Thread(target=nexus.run, daemon=True).start()
    threading.Thread(target=bus1.run, daemon=True).start()
    time.sleep(0.15)

    # Define RecordingModule subclass (service_name required by Module)
    class Recorder(RecordingModule):
        service_name = "test.recorder.writes"
        cpu_core = None

    rec = Recorder(file_path=file_path, nexus_address=NEXUS,
                   bus_xsub=BUS1_XSUB, bus_xpub=BUS1_XPUB)
    rec_thread = threading.Thread(target=rec.run, daemon=True)
    rec_thread.start()
    time.sleep(0.30)  # wait for registration + subscription propagation

    # Publish N messages
    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    pub.connect(BUS1_XSUB)
    time.sleep(0.05)
    _publish_n(pub, topic, payload, n_msgs)
    time.sleep(0.25)

    # Stop recording
    rec.stop()
    rec_thread.join(timeout=3.0)
    nexus.stop()
    bus1.stop()
    pub.close()
    ctx.term()

    # Verify file exists and has correct record count
    assert os.path.exists(file_path), ".tyche file was not created"
    assert os.path.getsize(file_path) > 0, ".tyche file is empty"

    records = []
    with open(file_path, "rb") as f:
        unpacker = msgpack.Unpacker(raw=False)
        unpacker.feed(f.read())
        for record in unpacker:
            records.append(record)

    assert len(records) == n_msgs, f"Expected {n_msgs} records, got {len(records)}"

    # Verify record structure: [topic, timestamp_ns, payload_bytes, wall_ns]
    for rec_data in records:
        assert len(rec_data) == 4
        assert rec_data[0] == topic
        assert isinstance(rec_data[1], int) and rec_data[1] > 0   # timestamp_ns
        assert rec_data[2] == payload                              # payload bytes match
        assert isinstance(rec_data[3], int) and rec_data[3] > 0   # wall_ns


# ---------------------------------------------------------------------------
# Test 2: Full record → replay roundtrip; payload bytes must be byte-equal
# ---------------------------------------------------------------------------

def test_record_replay_roundtrip(tmp_path):
    from tyche.core.nexus import Nexus
    from tyche.core.bus import Bus
    from tyche.backtest.recording import RecordingModule, ReplayBus

    file_path = str(tmp_path / "roundtrip.tyche")
    n_msgs = 3
    topic = "EQUITY.NYSE.AAPL.QUOTE"
    orig_payload = _make_payload()

    # ── Phase 1: Record ──────────────────────────────────────────────────────
    nexus = Nexus(address=NEXUS, cpu_core=None)
    bus1 = Bus(xsub_address=BUS1_XSUB, xpub_address=BUS1_XPUB, cpu_core=None)
    threading.Thread(target=nexus.run, daemon=True).start()
    threading.Thread(target=bus1.run, daemon=True).start()
    time.sleep(0.15)

    class Recorder(RecordingModule):
        service_name = "test.recorder.roundtrip"
        cpu_core = None

    rec = Recorder(file_path=file_path, nexus_address=NEXUS,
                   bus_xsub=BUS1_XSUB, bus_xpub=BUS1_XPUB)
    rec_thread = threading.Thread(target=rec.run, daemon=True)
    rec_thread.start()
    time.sleep(0.30)

    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    pub.connect(BUS1_XSUB)
    time.sleep(0.05)
    _publish_n(pub, topic, orig_payload, n_msgs, gap_s=0.03)
    time.sleep(0.25)

    rec.stop()
    rec_thread.join(timeout=3.0)
    nexus.stop()
    bus1.stop()
    pub.close()
    time.sleep(0.1)

    # ── Phase 2: Replay ──────────────────────────────────────────────────────
    bus2 = Bus(xsub_address=BUS2_XSUB, xpub_address=BUS2_XPUB, cpu_core=None)
    threading.Thread(target=bus2.run, daemon=True).start()
    time.sleep(0.1)

    sub = ctx.socket(zmq.SUB)
    sub.connect(BUS2_XPUB)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    time.sleep(0.1)  # subscription propagation through proxy

    # ReplayBus.run() is blocking; speed=0.0 → publish as fast as possible
    replay = ReplayBus(file_path=file_path, bus_xsub=BUS2_XSUB, speed=0.0)
    replay.run()
    time.sleep(0.1)

    # Drain received messages
    received_payloads = []
    poller = zmq.Poller()
    poller.register(sub, zmq.POLLIN)
    while True:
        evts = dict(poller.poll(timeout=150))
        if not evts:
            break
        frames = sub.recv_multipart()
        if len(frames) >= 3:
            received_payloads.append(frames[2])

    bus2.stop()
    sub.close()
    ctx.term()

    assert len(received_payloads) == n_msgs, \
        f"Expected {n_msgs} replayed messages, got {len(received_payloads)}"
    for p in received_payloads:
        assert p == orig_payload, "Replayed payload bytes differ from original"


# ---------------------------------------------------------------------------
# Test 3: ReplayBus speed=0.0 completes faster than wall-clock timing
# ---------------------------------------------------------------------------

def test_replay_bus_speed_zero_is_faster(tmp_path):
    """speed=0.0 must complete significantly faster than speed=1.0 for a known file."""
    from tyche.backtest.recording import ReplayBus
    from tyche.core.bus import Bus

    # Craft a .tyche file manually: 3 records with wall_ns 0.5s apart
    file_path = str(tmp_path / "speed_test.tyche")
    payload = _make_payload()
    base_ns = time.time_ns()
    gap_ns = 500_000_000  # 0.5s apart

    with open(file_path, "wb") as f:
        for i in range(3):
            record = ["EQUITY.NYSE.AAPL.QUOTE", base_ns + i * gap_ns, payload,
                      base_ns + i * gap_ns]
            f.write(msgpack.packb(record, use_bin_type=True))

    bus2 = Bus(xsub_address=BUS2_XSUB, xpub_address=BUS2_XPUB, cpu_core=None)
    threading.Thread(target=bus2.run, daemon=True).start()
    time.sleep(0.1)

    t0 = time.time()
    ReplayBus(file_path=file_path, bus_xsub=BUS2_XSUB, speed=0.0).run()
    elapsed_fast = time.time() - t0

    bus2.stop()

    # elapsed_fast must be much less than the 1.0s of simulated inter-message time
    assert elapsed_fast < 0.5, f"speed=0.0 replay took {elapsed_fast:.2f}s, expected < 0.5s"
