"""Bus service - XPUB/XSUB proxy for data streaming."""

import zmq
import threading
import logging
from typing import Optional


class Bus:
    """XPUB/XSUB proxy for pub/sub messaging.

    Publishers connect to XSUB endpoint.
    Subscribers connect to XPUB endpoint.
    """

    def __init__(
        self,
        xsub_endpoint: str,
        xpub_endpoint: str,
        cpu_core: Optional[int] = None,
        high_water_mark: int = 10000,
    ):
        self.xsub_endpoint = xsub_endpoint
        self.xpub_endpoint = xpub_endpoint
        self.cpu_core = cpu_core
        self.high_water_mark = high_water_mark

        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._ctx: Optional[zmq.Context] = None
        self._dropped_messages = 0
        self._logger = logging.getLogger("tyche.bus")

    def start(self) -> None:
        """Start the Bus proxy in a background thread."""
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._logger.info(f"Bus started on {self.xsub_endpoint} / {self.xpub_endpoint}")

    def stop(self) -> None:
        """Stop the Bus proxy."""
        self._running = False
        if self._ctx:
            self._ctx.term()
        if self._thread:
            self._thread.join(timeout=3.0)
        self._logger.info("Bus stopped")

    def _run(self) -> None:
        """Run the ZMQ proxy."""
        if self.cpu_core is not None:
            self._set_cpu_affinity(self.cpu_core)

        self._ctx = zmq.Context()

        xsub = self._ctx.socket(zmq.XSUB)
        xsub.set_hwm(self.high_water_mark)
        xsub.bind(self.xsub_endpoint)

        xpub = self._ctx.socket(zmq.XPUB)
        xpub.set_hwm(self.high_water_mark)
        xpub.bind(self.xpub_endpoint)

        try:
            zmq.proxy(xsub, xpub)
        except zmq.ContextTerminated:
            pass
        finally:
            try:
                xsub.close()
                xpub.close()
            except zmq.ZMQError:
                pass

    def get_dropped_messages(self) -> int:
        """Get count of dropped messages due to HWM."""
        return self._dropped_messages

    def _set_cpu_affinity(self, core: int) -> None:
        """Set CPU affinity for this thread."""
        import sys
        if sys.platform == "linux":
            import os
            os.sched_setaffinity(0, {core})
        elif sys.platform == "win32":
            import ctypes
            ctypes.windll.kernel32.SetThreadAffinityMask(-1, 1 << core)

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()
