# tyche/core/bus.py
import threading
from typing import Optional
import zmq


class Bus:
    def __init__(self, xsub_address: str, xpub_address: str, cpu_core: Optional[int] = None, sndhwm: int = 10000):
        self._xsub_address = xsub_address
        self._xpub_address = xpub_address
        self._cpu_core = cpu_core
        self._sndhwm = sndhwm
        self._ctx: Optional[zmq.Context] = None
        self._xsub: Optional[zmq.Socket] = None
        self._xpub: Optional[zmq.Socket] = None
        self._stop_event = threading.Event()
        self._proxy_thread: threading.Thread | None = None

    def _pin_cpu(self):
        if self._cpu_core is None:
            return
        try:
            import os
            os.sched_setaffinity(0, {self._cpu_core})
        except AttributeError:
            import ctypes
            h = ctypes.windll.kernel32.GetCurrentThread()
            ctypes.windll.kernel32.SetThreadAffinityMask(h, 1 << self._cpu_core)

    def _proxy(self):
        self._pin_cpu()
        self._ctx = zmq.Context()

        self._xsub = self._ctx.socket(zmq.XSUB)
        self._xsub.set_hwm(self._sndhwm)
        self._xsub.bind(self._xsub_address)

        self._xpub = self._ctx.socket(zmq.XPUB)
        self._xpub.set_hwm(self._sndhwm)
        self._xpub.bind(self._xpub_address)

        # zmq.proxy blocks until interrupted
        try:
            zmq.proxy(self._xsub, self._xpub)
        except zmq.ZMQError:
            pass

        self._xsub.close()
        self._xpub.close()
        self._ctx.term()

    def run(self):
        self._proxy_thread = threading.Thread(target=self._proxy, daemon=True)
        self._proxy_thread.start()

    def stop(self):
        """Stop the proxy by closing the sockets from another thread."""
        if self._ctx and self._xsub and self._xpub:
            # Closing sockets unblocks zmq.proxy
            try:
                self._xsub.close()
                self._xpub.close()
            except zmq.ZMQError:
                pass

    def wait(self):
        """Block until proxy thread exits."""
        if self._proxy_thread:
            self._proxy_thread.join()
