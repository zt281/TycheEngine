"""Module base class for TycheEngine strategies."""

import zmq
import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Callable

from .types import Tick, Quote, Trade, Bar, Order, OrderEvent
from .serialization import encode, decode
from .protocol import (
    READY, ACK, HB, CMD, REPLY, DISCO,
    CMD_START, CMD_STOP, CMD_RECONFIGURE, CMD_STATUS,
    STATUS_OK, STATUS_ERROR, PROTOCOL_VERSION,
    DEFAULT_HEARTBEAT_INTERVAL_MS,
)


class Module(ABC):
    """Base class for all TycheEngine modules.

    Modules are completely independent processes that communicate with Core
    via ZeroMQ IPC sockets. They import only tyche_client, never tyche_core.
    """

    service_name: str = "module.base"
    service_version: str = "1.0.0"

    def __init__(
        self,
        nexus_endpoint: str,
        bus_xsub_endpoint: str,
        bus_xpub_endpoint: str,
        config_path: Optional[str] = None,
        metrics_enabled: bool = False,
        metrics_buffer_size: int = 1024,
    ):
        self.nexus_endpoint = nexus_endpoint
        self.bus_xsub_endpoint = bus_xsub_endpoint
        self.bus_xpub_endpoint = bus_xpub_endpoint
        self.config_path = config_path

        self._config: Dict[str, Any] = {}
        self._correlation_id: int = 0
        self._assigned_id: str = ""
        self._running = False
        self._initialized = False
        self._ctx = zmq.Context()
        self._nexus_socket: Optional[zmq.Socket] = None
        self._pub_socket: Optional[zmq.Socket] = None
        self._sub_socket: Optional[zmq.Socket] = None
        self._poller = zmq.Poller()

        self._logger = logging.getLogger(self.service_name)
        self._heartbeat_interval_ms = DEFAULT_HEARTBEAT_INTERVAL_MS
        self._last_heartbeat_send = 0
        self._metrics_enabled = metrics_enabled
        self._metrics_buffer_size = metrics_buffer_size
        self._dropped_messages = 0

        # Handlers for different message types
        self._handlers: Dict[str, Callable] = {
            "Tick": self.on_tick,
            "Quote": self.on_quote,
            "Trade": self.on_trade,
            "Bar": self.on_bar,
            "OrderEvent": self.on_order_event,
        }

    def _load_config(self) -> None:
        """Load module configuration from JSON file."""
        if self.config_path:
            with open(self.config_path) as f:
                self._config = json.load(f)
                self._logger.info(f"Loaded config from {self.config_path}")

    def _encode(self, obj: Any) -> bytes:
        """Encode object to MessagePack."""
        return encode(obj)

    def _decode(self, data: bytes) -> Any:
        """Decode MessagePack to object."""
        return decode(data)

    def _register(self) -> bool:
        """Register with Nexus."""
        self._nexus_socket.send_multipart([
            READY,
            PROTOCOL_VERSION.to_bytes(4, "big"),
            json.dumps({
                "service_name": self.service_name,
                "service_version": self.service_version,
                "protocol_version": PROTOCOL_VERSION,
                "subscriptions": [],
                "heartbeat_interval_ms": self._heartbeat_interval_ms,
                "capabilities": ["publish", "subscribe"],
                "metadata": {},
            }).encode(),
        ])

        # Wait for ACK
        if self._nexus_socket.poll(timeout=5000):
            frames = self._nexus_socket.recv_multipart()
            if frames[0] == ACK:
                self._correlation_id = int.from_bytes(frames[1], "big")
                self._assigned_id = frames[2].decode()
                self._heartbeat_interval_ms = int.from_bytes(frames[3], "big")
                self._logger.info(f"Registered with Nexus as {self._assigned_id}")
                return True

        self._logger.error("Failed to register with Nexus")
        return False

    def _send_heartbeat(self) -> None:
        """Send heartbeat to Nexus."""
        now = time.time_ns()
        self._nexus_socket.send_multipart([
            HB,
            now.to_bytes(8, "big"),
            self._correlation_id.to_bytes(8, "big"),
        ])

    def _handle_command(self, cmd_type: bytes, payload: bytes) -> None:
        """Handle command from Nexus."""
        if cmd_type == CMD_START:
            self._logger.info("Received START command")
            self.on_start()
            self._send_reply(STATUS_OK)
        elif cmd_type == CMD_STOP:
            self._logger.info("Received STOP command")
            self._send_reply(STATUS_OK)
            self._running = False
        elif cmd_type == CMD_RECONFIGURE:
            self._logger.info("Received RECONFIGURE command")
            try:
                new_config = json.loads(payload)
                self.on_reconfigure(new_config)
                self._send_reply(STATUS_OK)
            except json.JSONDecodeError as e:
                self._send_reply(STATUS_ERROR, str(e).encode())
        elif cmd_type == CMD_STATUS:
            self.on_status()
            self._send_reply(STATUS_OK)

    def _send_reply(self, status: bytes, message: bytes = b"") -> None:
        """Send reply to Nexus."""
        frames = [REPLY, self._correlation_id.to_bytes(8, "big"), status]
        if message:
            frames.append(message)
        self._nexus_socket.send_multipart(frames)

    def _handle_nexus_message(self, frames: list) -> None:
        """Handle message from Nexus."""
        msg_type = frames[0]

        if msg_type == CMD:
            cmd_type = frames[1] if len(frames) > 1 else b""
            payload = frames[2] if len(frames) > 2 else b""
            self._handle_command(cmd_type, payload)

    def _dispatch(self, topic: bytes, payload: bytes) -> None:
        """Dispatch incoming Bus message to appropriate handler."""
        try:
            obj = self._decode(payload)
            handler = self._handlers.get(type(obj).__name__)
            if handler:
                handler(obj)
        except Exception as e:
            self._logger.error(f"Error dispatching message: {e}")
            self._dropped_messages += 1

    def subscribe(self, topic_pattern: str) -> None:
        """Subscribe to topic pattern on Bus."""
        if self._sub_socket:
            self._sub_socket.setsockopt(zmq.SUBSCRIBE, topic_pattern.encode())
            self._logger.debug(f"Subscribed to: {topic_pattern}")

    def publish(self, topic: str, obj: Any) -> None:
        """Publish object to Bus topic."""
        if self._pub_socket:
            self._pub_socket.send_multipart([
                topic.encode(),
                self._encode(obj),
            ])

    def send_order(self, order: Order) -> None:
        """Send order via internal topic."""
        self.publish("INTERNAL.OMS.ORDER", order)

    def run(self) -> None:
        """Main run loop."""
        self._load_config()

        # Create and connect sockets
        self._nexus_socket = self._ctx.socket(zmq.DEALER)
        self._nexus_socket.connect(self.nexus_endpoint)

        self._pub_socket = self._ctx.socket(zmq.PUB)
        self._pub_socket.connect(self.bus_xsub_endpoint)

        self._sub_socket = self._ctx.socket(zmq.SUB)
        self._sub_socket.connect(self.bus_xpub_endpoint)

        # Register with Nexus
        if not self._register():
            self._cleanup()
            return

        self._initialized = True
        self.on_init()

        self._running = True
        self._poller.register(self._nexus_socket, zmq.POLLIN)
        self._poller.register(self._sub_socket, zmq.POLLIN)

        self._logger.info("Module running")

        heartbeat_interval_ns = self._heartbeat_interval_ms * 1_000_000

        try:
            while self._running:
                events = dict(self._poller.poll(timeout=100))

                # Handle Nexus messages
                if self._nexus_socket in events:
                    frames = self._nexus_socket.recv_multipart()
                    self._handle_nexus_message(frames)

                # Handle Bus messages
                if self._sub_socket in events:
                    topic, payload = self._sub_socket.recv_multipart()
                    self._dispatch(topic, payload)

                # Send heartbeat
                now = time.time_ns()
                if now - self._last_heartbeat_send > heartbeat_interval_ns:
                    self._send_heartbeat()
                    self._last_heartbeat_send = now

        except KeyboardInterrupt:
            self._logger.info("Interrupted by user")
        finally:
            self._cleanup()

    def _cleanup(self) -> None:
        """Clean up resources."""
        self._logger.info("Cleaning up...")

        if self._nexus_socket:
            # Send disconnect
            try:
                self._nexus_socket.send_multipart([
                    DISCO,
                    self._correlation_id.to_bytes(8, "big"),
                ])
            except Exception:
                pass
            self._nexus_socket.close()

        if self._pub_socket:
            self._pub_socket.close()

        if self._sub_socket:
            self._sub_socket.close()

        self._ctx.term()
        self._logger.info("Module stopped")

    @abstractmethod
    def on_init(self) -> None:
        """Called after successful registration."""
        pass

    @abstractmethod
    def on_start(self) -> None:
        """Called when Nexus sends START command."""
        pass

    @abstractmethod
    def on_stop(self) -> None:
        """Called when Nexus sends STOP command."""
        pass

    def on_reconfigure(self, new_config: Dict[str, Any]) -> None:
        """Called when Nexus sends RECONFIGURE command."""
        self._config.update(new_config)
        self._logger.info("Configuration updated")

    def on_status(self) -> None:
        """Called when Nexus sends STATUS command."""
        pass

    def on_tick(self, tick: Tick) -> None:
        """Override to handle Tick messages."""
        pass

    def on_quote(self, quote: Quote) -> None:
        """Override to handle Quote messages."""
        pass

    def on_trade(self, trade: Trade) -> None:
        """Override to handle Trade messages."""
        pass

    def on_bar(self, bar: Bar) -> None:
        """Override to handle Bar messages."""
        pass

    def on_order_event(self, event: OrderEvent) -> None:
        """Override to handle OrderEvent messages."""
        pass
