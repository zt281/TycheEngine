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
    """Stub — implemented in Task 5."""
