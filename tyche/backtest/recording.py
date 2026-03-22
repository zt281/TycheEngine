"""Backtest recording and replay utilities."""
import time

import msgpack
import zmq

from tyche.core.module import Module


class RecordingModule(Module):
    """Subscribes to all Bus topics and writes every message to a .tyche file.

    File format: sequential MessagePack arrays, each:
        [topic: str, timestamp_ns: int, payload: bytes, wall_ns: int]

    wall_ns is always time.time_ns() — unconditional wall clock.
    timestamp_ns is self._clock.now_ns() — injectable for SimClock backtest.

    Override _dispatch() so ALL messages are captured (typed handlers would
    miss unknown dtypes; overriding on_raw() would miss typed market data).
    """

    def __init__(self, file_path: str, nexus_address: str, bus_xsub: str, bus_xpub: str):
        super().__init__(nexus_address, bus_xsub, bus_xpub)
        self._file_path = file_path
        self._file = None

    def on_start(self):
        self._file = open(self._file_path, "ab")
        # Subscribe to all topics — bypass TopicValidator (empty string is not a
        # valid topic but is a legal ZMQ XSUB subscription)
        self._sub_sock.setsockopt(zmq.SUBSCRIBE, b"")

    def on_stop(self):
        if self._file is not None:
            self._file.flush()
            self._file.close()
            self._file = None

    def _dispatch(self, topic: str, payload: bytes):
        if self._file is None:
            return
        wall_ns = time.time_ns()              # always wall clock
        timestamp_ns = self._clock.now_ns()  # injectable clock for backtest
        record = [topic, timestamp_ns, payload, wall_ns]
        try:
            self._file.write(msgpack.packb(record, use_bin_type=True))
        except OSError as exc:
            self._log.error("Recording write failed", error=str(exc))
            return
        super()._dispatch(topic, payload)


class ReplayBus:
    """Reads a .tyche recording file and re-publishes all messages to a Bus.

    Constructor: ReplayBus(file_path, bus_xsub, speed=1.0)
      speed=0.0  → publish as fast as possible (no inter-message delay)
      speed=1.0  → wall-clock timing (mirrors original recording rate)
      speed=10.0 → 10x accelerated

    run() is blocking. It replays the file exactly once and returns.
    The ZMQ context is created in __init__ and terminated in run() after completion.
    """

    def __init__(self, file_path: str, bus_xsub: str, speed: float = 1.0):
        if speed < 0.0:
            raise ValueError(f"speed must be >= 0.0, got {speed!r}")
        self._file_path = file_path
        self._bus_xsub = bus_xsub
        self._speed = speed
        self._ctx = zmq.Context()

    def run(self):
        sock = self._ctx.socket(zmq.PUB)
        sock.connect(self._bus_xsub)
        time.sleep(0.05)  # allow subscription propagation before first publish
        try:
            prev_wall_ns = None
            with open(self._file_path, "rb") as f:
                for record in msgpack.Unpacker(f, raw=False):
                    # record = [topic, timestamp_ns, payload, wall_ns]
                    if prev_wall_ns is not None:
                        if self._speed == 0.0:
                            pass  # no sleep — publish as fast as possible
                        else:
                            delay_s = (record[3] - prev_wall_ns) / self._speed / 1_000_000_000
                            if delay_s > 0:
                                time.sleep(delay_s)
                    prev_wall_ns = record[3]

                    sock.send_multipart([
                        record[0].encode(),                    # topic bytes
                        record[1].to_bytes(8, "big", signed=True),  # timestamp_ns
                        record[2],                             # payload bytes (unchanged)
                    ])
        finally:
            sock.close()
            self._ctx.term()
