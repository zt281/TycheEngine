# tyche/core/module.py
import time, threading
from typing import Optional
import zmq
from abc import ABC
import tyche_core
from tyche.utils.logging import StructuredLogger
from tyche.utils.topics import TopicValidator, suffix_to_bar_interval

PROTOCOL = b"TYCHE"
_REG_TIMEOUT_MS = 500
_REG_MAX_RETRIES = 20
_PAIR_INPROC_PREFIX = "inproc://tyche-rust-"

_MARKET_DISPATCH = {
    "TICK":  ("deserialize_tick", "on_tick"),
    "QUOTE": ("deserialize_quote", "on_quote"),
    "TRADE": ("deserialize_trade", "on_trade"),
}

_INTERNAL_DISPATCH = {
    "ORDER":       ("deserialize_order", "on_order"),
    "ORDER_EVENT": ("deserialize_order_event", "on_order_event"),
    "ACK":         ("deserialize_ack", "on_ack"),
    "POSITION":    ("deserialize_position", "on_position"),
    "RISK_UPDATE": ("deserialize_risk", "on_risk"),
    "VOL_SURFACE": ("deserialize_model", "on_model"),
}


class Module(ABC):
    service_name: str = "module.base"
    cpu_core: Optional[int] = None

    def __init__(self, nexus_address: str, bus_xsub: str, bus_xpub: str):
        self._nexus_address = nexus_address
        self._bus_xsub = bus_xsub
        self._bus_xpub = bus_xpub
        self._stop_event = threading.Event()
        self._log = StructuredLogger(self.service_name)
        self._correlation_id = 0
        self._ctx: Optional[zmq.Context] = None
        self._pub_sock: Optional[zmq.Socket] = None
        self._sub_sock: Optional[zmq.Socket] = None
        self._pair_sock: Optional[zmq.Socket] = None

    def on_start(self): pass
    def on_stop(self): pass
    def on_reconfigure(self, cfg: dict): pass

    def on_tick(self, topic: str, tick): pass
    def on_quote(self, topic: str, quote): pass
    def on_trade(self, topic: str, trade): pass
    def on_bar(self, topic: str, bar, interval): pass
    def on_order(self, topic: str, order): pass
    def on_order_event(self, topic: str, event): pass
    def on_ack(self, topic: str, ack): pass
    def on_position(self, topic: str, position): pass
    def on_risk(self, topic: str, risk): pass
    def on_model(self, topic: str, model): pass
    def on_raw(self, topic: str, payload: bytes): pass

    def on_command(self, command: str, payload: dict) -> dict:
        self._log.warn("Unknown command", command=command)
        return {"status": "UNKNOWN_COMMAND", "command": command}

    _TYCHE_SERIALIZE = {
        "PyQuote": "serialize_quote", "PyTick": "serialize_tick",
        "PyTrade": "serialize_trade", "PyBar": "serialize_bar",
        "PyOrder": "serialize_order", "PyOrderEvent": "serialize_order_event",
        "PyAck": "serialize_ack", "PyPosition": "serialize_position",
        "PyRisk": "serialize_risk", "PyModel": "serialize_model",
    }

    def publish(self, topic: str, payload) -> None:
        TopicValidator.validate(topic)
        if self._pub_sock is None:
            raise RuntimeError("Module not started")
        ts = time.time_ns().to_bytes(8, 'big')
        if isinstance(payload, bytes):
            raw = payload
        else:
            ser_fn = self._TYCHE_SERIALIZE.get(type(payload).__name__)
            if ser_fn is not None:
                raw = bytes(getattr(tyche_core, ser_fn)(payload))
            else:
                import msgpack
                raw = msgpack.packb(payload, use_bin_type=True)
        self._pub_sock.send_multipart([topic.encode(), ts, raw])

    def subscribe(self, topic: str) -> None:
        TopicValidator.validate(topic)
        if self._sub_sock:
            self._sub_sock.setsockopt_string(zmq.SUBSCRIBE, topic)

    def unsubscribe(self, topic: str) -> None:
        if self._sub_sock:
            self._sub_sock.setsockopt_string(zmq.UNSUBSCRIBE, topic)

    def stop(self):
        self._stop_event.set()

    def run(self):
        self._pin_cpu()
        self._ctx = zmq.Context()

        dealer = self._ctx.socket(zmq.DEALER)
        dealer.setsockopt_string(zmq.IDENTITY, self.service_name)
        dealer.connect(self._nexus_address)

        self._pub_sock = self._ctx.socket(zmq.PUB)
        self._pub_sock.connect(self._bus_xsub)
        self._sub_sock = self._ctx.socket(zmq.SUB)
        self._sub_sock.connect(self._bus_xpub)

        pair_addr = f"{_PAIR_INPROC_PREFIX}{self.service_name}"
        self._pair_sock = self._ctx.socket(zmq.PAIR)
        self._pair_sock.bind(pair_addr)
        tyche_core.init_ffi_bridge(self.service_name)

        self._register(dealer)
        self.on_start()

        poller = zmq.Poller()
        poller.register(dealer, zmq.POLLIN)
        poller.register(self._sub_sock, zmq.POLLIN)
        poller.register(self._pair_sock, zmq.POLLIN)

        next_hb = time.time() + 1.0

        while not self._stop_event.is_set():
            events = dict(poller.poll(timeout=200))

            if dealer in events:
                self._handle_nexus(dealer, dealer.recv_multipart())

            if self._sub_sock in events:
                frames = self._sub_sock.recv_multipart()
                if len(frames) >= 3:
                    self._dispatch(frames[0].decode(), frames[2])

            if self._pair_sock in events:
                self._handle_pair(self._pair_sock.recv())

            if time.time() >= next_hb:
                dealer.send_multipart([PROTOCOL, b"HB", str(time.time_ns()).encode()])
                next_hb = time.time() + 1.0

        self.on_stop()
        dealer.send_multipart([PROTOCOL, b"DISCO", b"shutdown"])
        for s in (dealer, self._pub_sock, self._sub_sock, self._pair_sock):
            s.close()
        self._ctx.term()

    def _register(self, dealer):
        for attempt in range(_REG_MAX_RETRIES):
            self._correlation_id += 1
            dealer.send_multipart([
                PROTOCOL, b"READY",
                str(self._correlation_id).encode(),
                self.service_name.encode(),
                str(self.cpu_core or 0).encode(),
            ])
            poller = zmq.Poller()
            poller.register(dealer, zmq.POLLIN)
            if dict(poller.poll(timeout=_REG_TIMEOUT_MS)).get(dealer):
                frames = dealer.recv_multipart()
                if (len(frames) >= 3 and frames[1] == b"READY_ACK"
                        and frames[2].decode() == str(self._correlation_id)):
                    self._log.info("Registered with Nexus", attempt=attempt + 1)
                    return
                self._log.warn("Ignored stale frame", frames=[f.decode(errors='replace') for f in frames])
        raise RuntimeError(f"Registration failed after {_REG_MAX_RETRIES} retries")

    def _handle_nexus(self, dealer, frames):
        if len(frames) < 2 or frames[0] != PROTOCOL:
            return
        verb = frames[1]
        if verb == b"CMD" and len(frames) >= 4:
            import msgpack, os as _os
            command = frames[2].decode()
            payload = msgpack.unpackb(frames[3], raw=False) if frames[3] else {}

            if command == "STOP":
                result = {"status": "OK"}
                dealer.send_multipart([PROTOCOL, b"REPLY", b"0",
                                       b"OK", msgpack.packb(result, use_bin_type=True)])
                self._stop_event.set()
                return
            elif command == "RECONFIGURE":
                self.on_reconfigure(payload)
                result = {"status": "OK"}
            elif command == "STATUS":
                result = {"status": "RUNNING", "pid": _os.getpid()}
            elif command == "START":
                result = {"status": "OK"}
            else:
                result = self.on_command(command, payload)

            dealer.send_multipart([PROTOCOL, b"REPLY", b"0",
                                   b"OK", msgpack.packb(result, use_bin_type=True)])

    def _handle_pair(self, raw: bytes):
        if not raw:
            return
        signal_type = raw[0]
        if signal_type == 0x01:
            topic = raw[1:].decode()
            item = tyche_core.take_pending(self.service_name, topic)
            if item is not None:
                self._dispatch(topic, bytes(item))
        elif signal_type == 0x02:
            self._stop_event.set()
        elif signal_type == 0x03:
            self._log.error("FFI error", detail=raw[1:].decode())

    def _dispatch(self, topic: str, payload: bytes):
        parts = topic.split(".")

        if parts[0] == "INTERNAL" and len(parts) >= 3:
            event = parts[2]
            if event in _INTERNAL_DISPATCH:
                deser_name, handler_name = _INTERNAL_DISPATCH[event]
                try:
                    obj = getattr(tyche_core, deser_name)(payload)
                    getattr(self, handler_name)(topic, obj)
                except Exception as e:
                    self._log.warn("Internal dispatch failed", event=event, error=str(e))
            else:
                self.on_raw(topic, payload)
            return

        if len(parts) < 4:
            self.on_raw(topic, payload)
            return

        dtype = parts[3]

        if dtype == "BAR" and len(parts) >= 5:
            try:
                bar = tyche_core.deserialize_bar(payload)
                interval = suffix_to_bar_interval(parts[4])
                self.on_bar(topic, bar, interval)
            except Exception as e:
                self._log.warn("Bar dispatch failed", error=str(e))
            return

        if dtype in _MARKET_DISPATCH:
            deser_name, handler_name = _MARKET_DISPATCH[dtype]
            try:
                obj = getattr(tyche_core, deser_name)(payload)
                getattr(self, handler_name)(topic, obj)
            except Exception as e:
                self._log.warn("Market dispatch failed", dtype=dtype, error=str(e))
        else:
            self.on_raw(topic, payload)

    def _pin_cpu(self):
        if self.cpu_core is None:
            return
        try:
            import os
            os.sched_setaffinity(0, {self.cpu_core})
        except AttributeError:
            import ctypes
            h = ctypes.windll.kernel32.GetCurrentThread()
            ctypes.windll.kernel32.SetThreadAffinityMask(h, 1 << self.cpu_core)
