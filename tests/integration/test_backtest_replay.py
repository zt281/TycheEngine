"""
Integration tests for RecordingModule and ReplayBus.

Port assignments — each test gets its own isolated range to avoid ZMQ
socket-release races when tests run sequentially in the same pytest session:

  Test 1 (writes): NEXUS=35555, BUS_XSUB=35556, BUS_XPUB=35557
  Test 2 (roundtrip): NEXUS=35560, REC_XSUB=35561, REC_XPUB=35562,
                      REPLAY_XSUB=35563, REPLAY_XPUB=35564
  Test 3 (speed):  BUS_XSUB=35565, BUS_XPUB=35566
"""
import os
import time
import threading

import msgpack
import pytest
import zmq
import tyche_core

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

# Isolated ports for test 1
_T1_NEXUS    = "tcp://127.0.0.1:35555"
_T1_BUS_XSUB = "tcp://127.0.0.1:35556"
_T1_BUS_XPUB = "tcp://127.0.0.1:35557"


def test_recording_module_writes_tyche_file(tmp_path):
    from tyche.core.nexus import Nexus
    from tyche.core.bus import Bus
    from tyche.backtest.recording import RecordingModule

    file_path = str(tmp_path / "test.tyche")
    n_msgs = 3
    topic = "EQUITY.NYSE.AAPL.QUOTE"
    payload = _make_payload()

    nexus = Nexus(address=_T1_NEXUS, cpu_core=None)
    bus1 = Bus(xsub_address=_T1_BUS_XSUB, xpub_address=_T1_BUS_XPUB, cpu_core=None)
    threading.Thread(target=nexus.run, daemon=True).start()
    threading.Thread(target=bus1.run, daemon=True).start()
    time.sleep(0.15)

    class Recorder(RecordingModule):
        service_name = "test.recorder.writes"
        cpu_core = None

    rec = Recorder(file_path=file_path, nexus_address=_T1_NEXUS,
                   bus_xsub=_T1_BUS_XSUB, bus_xpub=_T1_BUS_XPUB)
    rec_thread = threading.Thread(target=rec.run, daemon=True)
    rec_thread.start()
    time.sleep(0.30)

    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    pub.connect(_T1_BUS_XSUB)
    time.sleep(0.05)
    _publish_n(pub, topic, payload, n_msgs)
    time.sleep(0.25)

    rec.stop()
    rec_thread.join(timeout=3.0)
    nexus.stop()
    bus1.stop()
    pub.close()
    ctx.term()

    assert os.path.exists(file_path), ".tyche file was not created"
    assert os.path.getsize(file_path) > 0, ".tyche file is empty"

    records = []
    with open(file_path, "rb") as f:
        unpacker = msgpack.Unpacker(raw=False)
        unpacker.feed(f.read())
        for record in unpacker:
            records.append(record)

    assert len(records) == n_msgs, f"Expected {n_msgs} records, got {len(records)}"

    for rec_data in records:
        assert len(rec_data) == 4
        assert rec_data[0] == topic
        assert isinstance(rec_data[1], int) and rec_data[1] > 0   # timestamp_ns
        assert rec_data[2] == payload                              # payload bytes match
        assert isinstance(rec_data[3], int) and rec_data[3] > 0   # wall_ns


# ---------------------------------------------------------------------------
# Test 2: Full record → replay roundtrip; payload bytes must be byte-equal
# ---------------------------------------------------------------------------

# Isolated ports for test 2 — distinct from test 1 and test 3
_T2_NEXUS       = "tcp://127.0.0.1:35560"
_T2_REC_XSUB    = "tcp://127.0.0.1:35561"
_T2_REC_XPUB    = "tcp://127.0.0.1:35562"
_T2_REPLAY_XSUB = "tcp://127.0.0.1:35563"
_T2_REPLAY_XPUB = "tcp://127.0.0.1:35564"


def test_record_replay_roundtrip(tmp_path):
    from tyche.core.nexus import Nexus
    from tyche.core.bus import Bus
    from tyche.backtest.recording import RecordingModule, ReplayBus

    file_path = str(tmp_path / "roundtrip.tyche")
    n_msgs = 3
    topic = "EQUITY.NYSE.AAPL.QUOTE"
    orig_payload = _make_payload()

    # ── Phase 1: Record ──────────────────────────────────────────────────────
    nexus = Nexus(address=_T2_NEXUS, cpu_core=None)
    bus1 = Bus(xsub_address=_T2_REC_XSUB, xpub_address=_T2_REC_XPUB, cpu_core=None)
    threading.Thread(target=nexus.run, daemon=True).start()
    threading.Thread(target=bus1.run, daemon=True).start()
    time.sleep(0.15)

    class Recorder(RecordingModule):
        service_name = "test.recorder.roundtrip"
        cpu_core = None

    rec = Recorder(file_path=file_path, nexus_address=_T2_NEXUS,
                   bus_xsub=_T2_REC_XSUB, bus_xpub=_T2_REC_XPUB)
    rec_thread = threading.Thread(target=rec.run, daemon=True)
    rec_thread.start()
    time.sleep(0.30)

    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    pub.connect(_T2_REC_XSUB)
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
    bus2 = Bus(xsub_address=_T2_REPLAY_XSUB, xpub_address=_T2_REPLAY_XPUB, cpu_core=None)
    threading.Thread(target=bus2.run, daemon=True).start()
    time.sleep(0.1)

    sub = ctx.socket(zmq.SUB)
    sub.connect(_T2_REPLAY_XPUB)
    sub.setsockopt(zmq.SUBSCRIBE, b"")
    time.sleep(0.1)

    replay = ReplayBus(file_path=file_path, bus_xsub=_T2_REPLAY_XSUB, speed=0.0)
    replay.run()
    time.sleep(0.1)

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

# Isolated ports for test 3
_T3_BUS_XSUB = "tcp://127.0.0.1:35565"
_T3_BUS_XPUB = "tcp://127.0.0.1:35566"


def test_replay_bus_speed_zero_is_faster(tmp_path):
    """speed=0.0 must complete significantly faster than speed=1.0 for a known file."""
    from tyche.backtest.recording import ReplayBus
    from tyche.core.bus import Bus

    file_path = str(tmp_path / "speed_test.tyche")
    payload = _make_payload()
    base_ns = time.time_ns()
    gap_ns = 500_000_000  # 0.5s apart

    with open(file_path, "wb") as f:
        for i in range(3):
            record = ["EQUITY.NYSE.AAPL.QUOTE", base_ns + i * gap_ns, payload,
                      base_ns + i * gap_ns]
            f.write(msgpack.packb(record, use_bin_type=True))

    bus3 = Bus(xsub_address=_T3_BUS_XSUB, xpub_address=_T3_BUS_XPUB, cpu_core=None)
    threading.Thread(target=bus3.run, daemon=True).start()
    time.sleep(0.1)

    t0 = time.time()
    ReplayBus(file_path=file_path, bus_xsub=_T3_BUS_XSUB, speed=0.0).run()
    elapsed_fast = time.time() - t0

    bus3.stop()

    assert elapsed_fast < 0.5, f"speed=0.0 replay took {elapsed_fast:.2f}s, expected < 0.5s"
