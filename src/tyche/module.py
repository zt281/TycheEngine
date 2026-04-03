"""TycheModule - Base implementation for Tyche Engine modules.

Modules connect to TycheEngine and handle events using interface patterns.
"""

import asyncio
from typing import Dict, List, Optional, Callable, Any
import zmq
from zmq.asyncio import Context, Socket

from tyche.module_base import ModuleBase
from tyche.types import (
    Endpoint, Interface, InterfacePattern,
    MessageType, DurabilityLevel, ModuleId, HEARTBEAT_INTERVAL
)
from tyche.message import Message, serialize, deserialize
from tyche.heartbeat import HeartbeatSender


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
        self.context: Optional[Context] = None
        self.reg_socket: Optional[Socket] = None
        self.event_sub: Optional[Socket] = None
        self.heartbeat_socket: Optional[Socket] = None

        # Heartbeat sender
        self._heartbeat_sender: Optional[HeartbeatSender] = None

        # Async tasks
        self._tasks: List[asyncio.Task] = []
        self._running = False
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

    async def start(self) -> None:
        """Start the module and connect to engine."""
        self.context = Context()

        # Registration socket (REQ for REQ-ROUTER pattern)
        self.reg_socket = self.context.socket(zmq.REQ)
        self.reg_socket.connect(str(self.engine_endpoint))

        # Event subscription (SUB)
        if self.event_endpoint:
            self.event_sub = self.context.socket(zmq.SUB)
            self.event_sub.connect(str(self.event_endpoint))

        # Heartbeat socket (SUB to receive engine heartbeats, DEALER to send)
        if self.heartbeat_endpoint:
            self.heartbeat_socket = self.context.socket(zmq.DEALER)
            self.heartbeat_socket.identity = self._module_id.encode()
            self.heartbeat_socket.connect(str(self.heartbeat_endpoint))
            self._heartbeat_sender = HeartbeatSender(
                self.heartbeat_socket,
                self._module_id
            )

        self._running = True

        # Register with engine
        await self._register()

        # Start background tasks
        self._tasks = [
            asyncio.create_task(self._receive_events()),
            asyncio.create_task(self._send_heartbeats()),
        ]

    async def stop(self) -> None:
        """Stop the module gracefully."""
        self._running = False

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Close sockets
        for socket in [self.reg_socket, self.event_sub, self.heartbeat_socket]:
            if socket:
                socket.close()

        if self.context:
            self.context.term()

    async def _register(self) -> bool:
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

        await self.reg_socket.send(serialize(msg))

        # Wait for acknowledgment
        if await self.reg_socket.poll(5000):  # 5 second timeout
            reply_data = await self.reg_socket.recv()
            reply = deserialize(reply_data)

            if reply.msg_type == MessageType.ACK:
                self._registered = True
                return True

        return False

    async def _receive_events(self) -> None:
        """Receive and handle events."""
        while self._running:
            try:
                if not self.event_sub:
                    await asyncio.sleep(0.1)
                    continue

                # Subscribe to all events we handle
                for event_name in self._handlers:
                    self.event_sub.setsockopt(zmq.SUBSCRIBE, event_name.encode())

                if await self.event_sub.poll(100):
                    topic, data = await self.event_sub.recv_multipart()
                    msg = deserialize(data)

                    # Route to handler
                    handler = self._handlers.get(msg.event)
                    if handler:
                        handler(msg.payload)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Event receive error: {e}")

    async def _send_heartbeats(self) -> None:
        """Send periodic heartbeats to engine."""
        while self._running:
            try:
                if self._heartbeat_sender and self._heartbeat_sender.should_send():
                    self._heartbeat_sender.send()

                await asyncio.sleep(HEARTBEAT_INTERVAL / 2)
            except asyncio.CancelledError:
                break

    async def send_event(
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

        await self.reg_socket.send(serialize(msg))

    async def call_ack(
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

        await self.reg_socket.send(serialize(msg))

        if await self.reg_socket.poll(timeout_ms):
            reply_data = await self.reg_socket.recv()
            reply = deserialize(reply_data)
            return reply.payload

        return None
