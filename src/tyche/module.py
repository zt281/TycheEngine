"""TycheModule - Base implementation for Tyche Engine modules.

Modules connect to TycheEngine and handle events using interface patterns.
"""

import threading
import time
from typing import Dict, List, Optional, Callable, Any
import zmq

from tyche.module_base import ModuleBase
from tyche.types import (
    Endpoint, Interface, InterfacePattern,
    MessageType, DurabilityLevel, ModuleId, HEARTBEAT_INTERVAL
)
from tyche.message import Message, serialize, deserialize


class TycheModule(ModuleBase):
    """Base class for Tyche Engine modules.

    Connects to TycheEngine and provides event handling.

    Args:
        engine_endpoint: Endpoint for TycheEngine registration
        module_id: Optional module ID (auto-generated if None)
        event_endpoint: Optional endpoint for event subscription
        heartbeat_endpoint: Optional endpoint for heartbeat
    """

    def __init__(
        self,
        engine_endpoint: Endpoint,
        module_id: Optional[str] = None,
        event_endpoint: Optional[Endpoint] = None,
        heartbeat_endpoint: Optional[Endpoint] = None
    ):
        self._module_id = module_id or ModuleId.generate()
        self.engine_endpoint = engine_endpoint
        self.event_endpoint = event_endpoint
        self.heartbeat_endpoint = heartbeat_endpoint

        # Event handlers: event_name -> handler_function
        self._handlers: Dict[str, Callable] = {}

        # Discovered interfaces
        self._interfaces: List[Interface] = []

        # ZMQ context and sockets
        self.context: Optional[zmq.Context] = None
        self.reg_socket: Optional[zmq.Socket] = None
        self.heartbeat_socket: Optional[zmq.Socket] = None

        # Threading
        self._threads: List[threading.Thread] = []
        self._running = False
        self._stop_event = threading.Event()
        self._registered = False

    @property
    def module_id(self) -> str:
        """Return module identifier."""
        return self._module_id

    @property
    def interfaces(self) -> List[Interface]:
        """Return discovered interfaces."""
        return self._interfaces

    def add_interface(
        self,
        name: str,
        handler: Callable,
        pattern: InterfacePattern = InterfacePattern.ON,
        durability: DurabilityLevel = DurabilityLevel.ASYNC_FLUSH
    ) -> None:
        """Add an event handler interface.

        Args:
            name: Interface name (e.g., "on_data", "ack_request")
            handler: Function to handle events
            pattern: Interface pattern type
            durability: Message durability level
        """
        self._handlers[name] = handler
        self._interfaces.append(Interface(
            name=name,
            pattern=pattern,
            event_type=name,
            durability=durability
        ))

    def start(self) -> None:
        """Start the module (alias for run, for compatibility with ModuleBase)."""
        self.run()

    def run(self) -> None:
        """Start the module - blocks until stop() is called."""
        self._start_workers()

        # Block until stopped
        try:
            while not self._stop_event.is_set():
                time.sleep(0.1)
        except KeyboardInterrupt:
            pass

    def start_nonblocking(self) -> None:
        """Start the module without blocking (for testing)."""
        self._start_workers()

    def _start_workers(self) -> None:
        """Start worker threads and connect to engine."""
        self.context = zmq.Context()
        self._running = True
        self._stop_event.clear()

        # Registration socket (REQ for REQ-ROUTER pattern)
        self.reg_socket = self.context.socket(zmq.REQ)
        self.reg_socket.setsockopt(zmq.LINGER, 0)
        self.reg_socket.connect(str(self.engine_endpoint))

        # Register with engine
        if not self._register():
            print(f"[{self._module_id}] Failed to register with engine")
            return

        # Start background threads
        self._threads = [
            threading.Thread(target=self._receive_heartbeats, name="heartbeat_recv"),
        ]

        for t in self._threads:
            t.start()

    def stop(self) -> None:
        """Stop the module gracefully."""
        self._running = False
        self._stop_event.set()

        # Wait for threads
        for t in self._threads:
            t.join(timeout=2.0)

        # Close sockets
        for socket in [self.reg_socket, self.heartbeat_socket]:
            if socket:
                socket.close()

        if self.context:
            self.context.term()
            self.context = None

    def _register(self) -> bool:
        """Register with TycheEngine.

        Returns:
            True if registration successful
        """
        if not self.reg_socket:
            return False

        # Build interface list for registration
        interfaces_data = [
            {
                "name": iface.name,
                "pattern": iface.pattern.value,
                "event_type": iface.event_type,
                "durability": iface.durability.value
            }
            for iface in self._interfaces
        ]

        msg = Message(
            msg_type=MessageType.REGISTER,
            sender=self._module_id,
            event="register",
            payload={
                "module_id": self._module_id,
                "interfaces": interfaces_data,
                "metadata": {}
            }
        )

        self.reg_socket.send(serialize(msg))

        # Wait for acknowledgment with timeout
        self.reg_socket.setsockopt(zmq.RCVTIMEO, 5000)  # 5 second timeout
        try:
            reply_data = self.reg_socket.recv()
            reply = deserialize(reply_data)

            if reply.msg_type == MessageType.ACK:
                self._registered = True
                print(f"[{self._module_id}] Registered with engine")
                return True
        except zmq.error.Again:
            print(f"[{self._module_id}] Registration timeout")

        return False

    def _receive_heartbeats(self) -> None:
        """Receive heartbeats from engine (placeholder)."""
        # TODO: Implement heartbeat subscription
        while self._running:
            time.sleep(0.1)

    def send_event(
        self,
        event: str,
        payload: Dict[str, Any],
        recipient: Optional[str] = None
    ) -> None:
        """Send an event to the engine.

        Args:
            event: Event name
            payload: Event data
            recipient: Optional specific recipient module
        """
        if not self.reg_socket:
            return

        msg = Message(
            msg_type=MessageType.EVENT,
            sender=self._module_id,
            recipient=recipient,
            event=event,
            payload=payload
        )

        self.reg_socket.send(serialize(msg))

    def call_ack(
        self,
        event: str,
        payload: Dict[str, Any],
        timeout_ms: int = 5000
    ) -> Optional[Dict[str, Any]]:
        """Call an ACK interface and wait for response.

        Args:
            event: Event name (should start with "ack_")
            payload: Event data
            timeout_ms: Timeout in milliseconds

        Returns:
            Response payload or None if timeout
        """
        if not self.reg_socket:
            return None

        msg = Message(
            msg_type=MessageType.REQUEST,
            sender=self._module_id,
            event=event,
            payload=payload
        )

        self.reg_socket.send(serialize(msg))

        self.reg_socket.setsockopt(zmq.RCVTIMEO, timeout_ms)
        try:
            reply_data = self.reg_socket.recv()
            reply = deserialize(reply_data)
            return reply.payload
        except zmq.error.Again:
            return None
