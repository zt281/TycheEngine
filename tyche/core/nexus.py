import time
import threading
from dataclasses import dataclass
from typing import Dict, Optional
import zmq
import msgpack

PROTOCOL = b"TYCHE"
HB_INTERVAL_S = 1.0


@dataclass
class ModuleDescriptor:
    service_name: str
    pid: int
    cpu_core: int
    status: str
    last_heartbeat_ns: int
    socket_identity: bytes


class Nexus:
    def __init__(self, address: str, cpu_core: Optional[int] = None):
        self._address = address
        self._cpu_core = cpu_core
        self._stop_event = threading.Event()
        self.registry: Dict[str, ModuleDescriptor] = {}
        self._lock = threading.Lock()
        self._ctx: Optional[zmq.Context] = None
        self._router: Optional[zmq.Socket] = None

    def _pin_cpu(self) -> None:
        if self._cpu_core is None:
            return
        try:
            import os
            os.sched_setaffinity(0, {self._cpu_core})
        except AttributeError:
            import ctypes
            h = ctypes.windll.kernel32.GetCurrentThread()  # type: ignore[attr-defined]
            ctypes.windll.kernel32.SetThreadAffinityMask(h, 1 << self._cpu_core)  # type: ignore[attr-defined]

    def _send(self, identity: bytes, frames: list) -> None:
        if self._router is not None:
            self._router.send_multipart([identity] + frames)

    def _handle_ready(self, identity: bytes, frames: list) -> None:
        # frames: [PROTOCOL, b"READY", correlation_id, service_name, cpu_core]
        if len(frames) < 5:
            return
        correlation_id = frames[2]
        service_name = frames[3].decode()
        cpu_core = int(frames[4].decode())

        with self._lock:
            self.registry[service_name] = ModuleDescriptor(
                service_name=service_name,
                pid=0,
                cpu_core=cpu_core,
                status="REGISTERED",
                last_heartbeat_ns=time.time_ns(),
                socket_identity=identity,
            )

        # READY_ACK: [PROTOCOL, b"READY_ACK", correlation_id, timestamp_ns]
        self._send(identity, [
            PROTOCOL, b"READY_ACK", correlation_id,
            str(time.time_ns()).encode(),
        ])

    def _handle_hb(self, identity: bytes) -> None:
        with self._lock:
            for desc in self.registry.values():
                if desc.socket_identity == identity:
                    desc.last_heartbeat_ns = time.time_ns()
                    break

    def _handle_command(self, identity: bytes, frames: list) -> None:
        # frames: [PROTOCOL, b"CMD", command, payload_bytes]
        if len(frames) < 4:
            return
        command = frames[2].decode()
        raw_payload = frames[3]
        payload = msgpack.unpackb(raw_payload, raw=False) if raw_payload else {}

        if command == "STATUS":
            result = {"status": "OK", "registry_size": len(self.registry)}
        elif command == "STOP":
            result = {"status": "OK"}
        elif command == "RECONFIGURE":
            result = {"status": "OK"}
        elif command == "START":
            result = {"status": "OK"}
        else:
            result = {"status": "UNKNOWN_COMMAND", "command": command}

        # REPLY: [PROTOCOL, b"REPLY", correlation_id, status, payload_bytes]
        self._send(identity, [
            PROTOCOL, b"REPLY", b"0", b"OK",
            msgpack.packb(result, use_bin_type=True),
        ])

    def _handle_disco(self, identity: bytes) -> None:
        with self._lock:
            to_remove = [
                name for name, desc in self.registry.items()
                if desc.socket_identity == identity
            ]
            for name in to_remove:
                del self.registry[name]

    def _process_frames(self, frames: list) -> None:
        # ROUTER prepends identity; rest is [PROTOCOL, verb, ...]
        if len(frames) < 3:
            return
        identity = frames[0]
        if frames[1] != PROTOCOL:
            return
        verb = frames[2]
        tail = frames[1:]  # keep PROTOCOL as frames[0] for handlers

        if verb == b"READY":
            # tail: [PROTOCOL, b"READY", correlation_id, service_name, cpu_core]
            self._handle_ready(identity, tail)
        elif verb == b"HB":
            self._handle_hb(identity)
        elif verb == b"CMD":
            # tail: [PROTOCOL, b"CMD", command, payload]
            self._handle_command(identity, tail)
        elif verb == b"DISCO":
            self._handle_disco(identity)

    def _heartbeat_loop(self) -> None:
        while not self._stop_event.is_set():
            time.sleep(HB_INTERVAL_S)
            now = time.time_ns()
            dead_threshold_ns = int(3 * HB_INTERVAL_S * 1e9)

            # Collect recipients and mark dead modules under the lock.
            # Do NOT call send_multipart while holding the lock — ZMQ sends
            # can block and would deadlock with the recv loop in run().
            to_send: list = []
            with self._lock:
                for desc in list(self.registry.values()):
                    age_ns = now - desc.last_heartbeat_ns
                    if age_ns > dead_threshold_ns:
                        desc.status = "DEAD"
                        continue
                    to_send.append(desc.socket_identity)

            if self._router is not None and not self._stop_event.is_set():
                hb_ts = str(now).encode()
                for identity in to_send:
                    try:
                        self._router.send_multipart([
                            identity, PROTOCOL, b"HB", hb_ts,
                        ])
                    except zmq.ZMQError:
                        # Socket closed by stop() — exit silently
                        return

    def run(self) -> None:
        self._pin_cpu()
        self._ctx = zmq.Context()
        self._router = self._ctx.socket(zmq.ROUTER)
        self._router.bind(self._address)
        self._router.setsockopt(zmq.RCVTIMEO, 200)

        hb_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        hb_thread.start()

        while not self._stop_event.is_set():
            try:
                frames = self._router.recv_multipart()
                if frames:
                    self._process_frames(frames)
            except zmq.Again:
                continue
            except zmq.ZMQError:
                if not self._stop_event.is_set():
                    raise

        self._router.close()
        self._ctx.term()

    def stop(self) -> None:
        self._stop_event.set()
