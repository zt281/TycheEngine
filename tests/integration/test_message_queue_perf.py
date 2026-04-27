"""Integration performance tests for message queue throughput and latency.

Tests the XPUB/XSUB event proxy under load to verify message queue efficiency.
"""

import time
from typing import List

import pytest

from tyche.engine import TycheEngine
from tyche.module import TycheModule
from tyche.types import Endpoint

# ── Throughput Test ───────────────────────────────────────────────

@pytest.mark.slow
class TestMessageQueueThroughput:
    """Measure how many events the XPUB/XSUB proxy can forward per second."""

    def test_single_sender_single_receiver_throughput(self):
        """One sender → one receiver via the event proxy."""
        engine = TycheEngine(
            registration_endpoint=Endpoint("127.0.0.1", 25000),
            event_endpoint=Endpoint("127.0.0.1", 25002),
            heartbeat_endpoint=Endpoint("127.0.0.1", 25004),
            heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25006),
        )
        engine.start_nonblocking()
        time.sleep(0.3)

        received: List[dict] = []

        class Receiver(TycheModule):
            def on_perf_event(self, payload: dict) -> None:
                received.append(payload)

        receiver = Receiver(
            engine_endpoint=Endpoint("127.0.0.1", 25000),
            heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25006),
            module_id="recv_tp_1",
        )
        receiver.add_interface("on_perf_event", receiver.on_perf_event)

        sender = TycheModule(
            engine_endpoint=Endpoint("127.0.0.1", 25000),
            heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25006),
            module_id="send_tp_1",
        )

        try:
            receiver.start_nonblocking()
            time.sleep(0.3)
            sender.start_nonblocking()
            time.sleep(0.3)  # let ZMQ SUB connect

            msg_count = 5000
            start_send = time.perf_counter()
            for i in range(msg_count):
                sender.send_event("on_perf_event", {"seq": i})

            # Wait for all messages to propagate
            deadline = time.perf_counter() + 10.0
            while len(received) < msg_count and time.perf_counter() < deadline:
                time.sleep(0.05)

            end_recv = time.perf_counter()
            total_time = end_recv - start_send
            throughput = len(received) / total_time if total_time > 0 else 0

            assert len(received) >= msg_count * 0.95, (
                f"Expected >= {msg_count * 0.95:.0f} messages, got {len(received)}"
            )
            assert throughput >= 1000, (
                f"Throughput too low: {throughput:.1f} msg/s (expected >= 1000)"
            )
        finally:
            sender.stop()
            receiver.stop()
            engine.stop()

    def test_single_sender_multiple_receivers_throughput(self):
        """One sender → three receivers via the event proxy."""
        engine = TycheEngine(
            registration_endpoint=Endpoint("127.0.0.1", 25100),
            event_endpoint=Endpoint("127.0.0.1", 25102),
            heartbeat_endpoint=Endpoint("127.0.0.1", 25104),
            heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25106),
        )
        engine.start_nonblocking()
        time.sleep(0.3)

        received_a: List[dict] = []
        received_b: List[dict] = []
        received_c: List[dict] = []

        class ReceiverA(TycheModule):
            def on_perf_event(self, payload: dict) -> None:
                received_a.append(payload)

        class ReceiverB(TycheModule):
            def on_perf_event(self, payload: dict) -> None:
                received_b.append(payload)

        class ReceiverC(TycheModule):
            def on_perf_event(self, payload: dict) -> None:
                received_c.append(payload)

        rec_a = ReceiverA(
            engine_endpoint=Endpoint("127.0.0.1", 25100),
            heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25106),
            module_id="recv_a",
        )
        rec_a.add_interface("on_perf_event", rec_a.on_perf_event)

        rec_b = ReceiverB(
            engine_endpoint=Endpoint("127.0.0.1", 25100),
            heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25106),
            module_id="recv_b",
        )
        rec_b.add_interface("on_perf_event", rec_b.on_perf_event)

        rec_c = ReceiverC(
            engine_endpoint=Endpoint("127.0.0.1", 25100),
            heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25106),
            module_id="recv_c",
        )
        rec_c.add_interface("on_perf_event", rec_c.on_perf_event)

        sender = TycheModule(
            engine_endpoint=Endpoint("127.0.0.1", 25100),
            heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25106),
            module_id="send_multi",
        )

        try:
            for r in (rec_a, rec_b, rec_c):
                r.start_nonblocking()
            time.sleep(0.3)
            sender.start_nonblocking()
            time.sleep(0.3)

            msg_count = 2000
            start_send = time.perf_counter()
            for i in range(msg_count):
                sender.send_event("on_perf_event", {"seq": i})

            deadline = time.perf_counter() + 10.0
            while (
                len(received_a) < msg_count
                or len(received_b) < msg_count
                or len(received_c) < msg_count
            ) and time.perf_counter() < deadline:
                time.sleep(0.05)

            end_recv = time.perf_counter()
            total_time = end_recv - start_send
            throughput = len(received_a) / total_time if total_time > 0 else 0

            assert len(received_a) >= msg_count * 0.95
            assert len(received_b) >= msg_count * 0.95
            assert len(received_c) >= msg_count * 0.95
            assert throughput >= 800, (
                f"Throughput too low: {throughput:.1f} msg/s per receiver (expected >= 800)"
            )
        finally:
            sender.stop()
            for r in (rec_a, rec_b, rec_c):
                r.stop()
            engine.stop()


# ── Latency Test ──────────────────────────────────────────────────

@pytest.mark.slow
class TestMessageQueueLatency:
    """Measure end-to-end latency through the event proxy."""

    def test_event_latency_single_receiver(self):
        """Measure latency for one sender → one receiver."""
        engine = TycheEngine(
            registration_endpoint=Endpoint("127.0.0.1", 25200),
            event_endpoint=Endpoint("127.0.0.1", 25202),
            heartbeat_endpoint=Endpoint("127.0.0.1", 25204),
            heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25206),
        )
        engine.start_nonblocking()
        time.sleep(0.3)

        latencies: List[float] = []

        class Receiver(TycheModule):
            def on_latency_event(self, payload: dict) -> None:
                now = time.perf_counter()
                sent = payload["ts"]
                latencies.append((now - sent) * 1000)  # ms

        receiver = Receiver(
            engine_endpoint=Endpoint("127.0.0.1", 25200),
            heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25206),
            module_id="recv_lat_1",
        )
        receiver.add_interface("on_latency_event", receiver.on_latency_event)

        sender = TycheModule(
            engine_endpoint=Endpoint("127.0.0.1", 25200),
            heartbeat_receive_endpoint=Endpoint("127.0.0.1", 25206),
            module_id="send_lat_1",
        )

        try:
            receiver.start_nonblocking()
            time.sleep(0.3)
            sender.start_nonblocking()
            time.sleep(0.3)

            msg_count = 1000
            for i in range(msg_count):
                sender.send_event("on_latency_event", {"seq": i, "ts": time.perf_counter()})
                # small gap to avoid overwhelming the queue during latency test
                if i % 100 == 0:
                    time.sleep(0.01)

            deadline = time.perf_counter() + 10.0
            while len(latencies) < msg_count and time.perf_counter() < deadline:
                time.sleep(0.05)

            assert len(latencies) >= msg_count * 0.95, (
                f"Expected >= {msg_count * 0.95:.0f} latencies, got {len(latencies)}"
            )

            avg_latency = sum(latencies) / len(latencies)
            p99_latency = sorted(latencies)[int(len(latencies) * 0.99)]
            max_latency = max(latencies)

            assert avg_latency < 50, (
                f"Average latency too high: {avg_latency:.2f} ms (expected < 50 ms)"
            )
            assert p99_latency < 200, (
                f"P99 latency too high: {p99_latency:.2f} ms (expected < 200 ms)"
            )
            assert max_latency < 500, (
                f"Max latency too high: {max_latency:.2f} ms (expected < 500 ms)"
            )
        finally:
            sender.stop()
            receiver.stop()
            engine.stop()

    def test_serialization_roundtrip_latency(self):
        """Measure serialize + deserialize overhead in isolation."""
        from tyche.message import Message, deserialize, serialize
        from tyche.types import DurabilityLevel, MessageType

        msg = Message(
            msg_type=MessageType.EVENT,
            sender="test_module",
            event="on_perf_event",
            payload={"data": "x" * 256, "seq": 42},
            durability=DurabilityLevel.ASYNC_FLUSH,
        )

        iterations = 10000
        start = time.perf_counter()
        for _ in range(iterations):
            data = serialize(msg)
            _ = deserialize(data)
        elapsed = time.perf_counter() - start

        ops_per_sec = iterations / elapsed
        us_per_op = (elapsed / iterations) * 1_000_000

        assert ops_per_sec >= 15000, (
            f"Serialization throughput too low: {ops_per_sec:.0f} ops/s (expected >= 15000)"
        )
        assert us_per_op < 100, (
            f"Serialization latency too high: {us_per_op:.2f} μs/op (expected < 100 μs)"
        )
