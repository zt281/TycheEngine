# tyche/utils/latency.py
import struct


class LatencyStats:
    """Fixed-size 1024-sample ring buffer for dispatch latency (nanoseconds).

    Memory: 1024 * 8 = 8192 bytes (fixed; never grows).
    Thread safety: single-writer assumed (only the Module run loop writes).
    """

    _CAPACITY = 1024
    _ITEM_SIZE = 8  # bytes per int64

    def __init__(self):
        self._buf = bytearray(self._CAPACITY * self._ITEM_SIZE)
        self._count = 0  # total samples written (unbounded)

    def record(self, ns: int) -> None:
        """Write a latency sample (nanoseconds) into the ring buffer."""
        struct.pack_into('<q', self._buf, (self._count % self._CAPACITY) * self._ITEM_SIZE, ns)
        self._count += 1

    def percentile(self, p: float) -> int:
        """Return the p-th percentile (p in [0.0, 1.0)).

        Returns 0 when no samples have been recorded.
        Raises ValueError if p >= 1.0.
        """
        if p >= 1.0:
            raise ValueError(f"p must be in [0.0, 1.0), got {p}")
        active_len = min(self._count, self._CAPACITY)
        if active_len == 0:
            return 0
        values = list(struct.unpack_from(f'<{active_len}q', self._buf))
        values.sort()
        return values[min(int(p * active_len), active_len - 1)]
