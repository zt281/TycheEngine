"""TycheEngine - Central broker and coordinator.

Implements:
- REQ-ROUTER: Module registration and interface discovery
- XPUB/XSUB: Event broadcasting
- ROUTER-DEALER: ACK responses and whisper routing
- PUSH-PULL: Load-balanced work distribution
- PUB/SUB: Heartbeat monitoring (Paranoid Pirate)
"""

import asyncio
import time
from typing import Dict, List, Optional, Any
import zmq
from zmq.asyncio import Context, Socket

from tyche.types import (
    Endpoint, ModuleInfo, Interface, InterfacePattern,
    MessageType, HEARTBEAT_INTERVAL, DurabilityLevel
)
from tyche.message import Message, Envelope, serialize, deserialize
from tyche.heartbeat import HeartbeatManager


class TycheEngine:
    """Central broker for Tyche Engine distributed system.

    Manages module registration, event routing, and heartbeat monitoring.

    Socket Layout:
    - registration: ROUTER socket for module registration (REQ-ROUTER)
    - event_pub: XPUB socket for event broadcasting
    - event_sub: XSUB socket for receiving events
    - heartbeat: PUB socket for heartbeat broadcasts
    - ack_router: ROUTER socket for ACK responses

    Args:
        registration_endpoint: Endpoint for module registration
        event_endpoint: Endpoint for event publishing (XPUB/XSUB)
        heartbeat_endpoint: Endpoint for heartbeat broadcasts
        ack_endpoint: Optional endpoint for ACK routing
    """

    def __init__(
        self,
        registration_endpoint: Endpoint,
        event_endpoint: Endpoint,
        heartbeat_endpoint: Endpoint,
        ack_endpoint: Optional[Endpoint] = None
    ):
        self.registration_endpoint = registration_endpoint
        self.event_endpoint = event_endpoint
        self.heartbeat_endpoint = heartbeat_endpoint
        self.ack_endpoint = ack_endpoint or Endpoint(
            event_endpoint.host, event_endpoint.port + 10
        )

        # Module registry: module_id -> ModuleInfo
        self.modules: Dict[str, ModuleInfo] = {}

        # Interface registry: event_name -> [(module_id, interface), ...]
        self.interfaces: Dict[str, List[tuple]] = {}

        # Heartbeat management
        self.heartbeat_manager = HeartbeatManager()

        # ZMQ context and sockets
        self.context: Optional[Context] = None
        self.reg_socket: Optional[Socket] = None
        self.event_pub: Optional[Socket] = None
        self.event_sub: Optional[Socket] = None
        self.heartbeat_socket: Optional[Socket] = None
        self.ack_socket: Optional[Socket] = None

        # Async tasks
        self._tasks: List[asyncio.Task] = []
        self._running = False

    async def start(self) -> None:
        """Start the engine and all sockets."""
        self.context = Context()

        # Registration socket (ROUTER for REQ-ROUTER pattern)
        self.reg_socket = self.context.socket(zmq.ROUTER)
        self.reg_socket.bind(str(self.registration_endpoint))

        # Event publishing (XPUB for subscription visibility)
        self.event_pub = self.context.socket(zmq.XPUB)
        self.event_pub.bind(str(self.event_endpoint))

        # Event subscription (XSUB)
        self.event_sub = self.context.socket(zmq.XSUB)
        self.event_sub.bind(f"tcp://{self.event_endpoint.host}:{self.event_endpoint.port + 1}")

        # Heartbeat socket (PUB)
        self.heartbeat_socket = self.context.socket(zmq.PUB)
        self.heartbeat_socket.bind(str(self.heartbeat_endpoint))

        # ACK router
        self.ack_socket = self.context.socket(zmq.ROUTER)
        self.ack_socket.bind(str(self.ack_endpoint))

        self._running = True

        # Start background tasks
        self._tasks = [
            asyncio.create_task(self._handle_registrations()),
            asyncio.create_task(self._handle_events()),
            asyncio.create_task(self._handle_heartbeats()),
            asyncio.create_task(self._handle_acks()),
            asyncio.create_task(self._monitor_peers()),
        ]

        # Start proxy between event_sub and event_pub
        self._tasks.append(
            asyncio.create_task(self._run_event_proxy())
        )

    async def stop(self) -> None:
        """Stop the engine gracefully."""
        self._running = False

        # Cancel all tasks
        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Close sockets
        for socket in [self.reg_socket, self.event_pub, self.event_sub,
                       self.heartbeat_socket, self.ack_socket]:
            if socket:
                socket.close()

        if self.context:
            self.context.term()

    def register_module(self, module_info: ModuleInfo) -> None:
        """Register a module and its interfaces."""
        self.modules[module_info.module_id] = module_info

        # Register interfaces
        for interface in module_info.interfaces:
            event_name = interface.name
            if event_name not in self.interfaces:
                self.interfaces[event_name] = []
            self.interfaces[event_name].append(
                (module_info.module_id, interface)
            )

        # Start heartbeat monitoring
        self.heartbeat_manager.register(module_info.module_id)

    def unregister_module(self, module_id: str) -> None:
        """Unregister a module."""
        if module_id not in self.modules:
            return

        module_info = self.modules[module_id]

        # Unregister interfaces
        for interface in module_info.interfaces:
            event_name = interface.name
            if event_name in self.interfaces:
                self.interfaces[event_name] = [
                    (mid, iface) for mid, iface in self.interfaces[event_name]
                    if mid != module_id
                ]

        del self.modules[module_id]
        self.heartbeat_manager.unregister(module_id)

    def get_modules_for_event(self, event: str) -> List[str]:
        """Get list of module IDs that handle an event."""
        if event not in self.interfaces:
            return []
        return [mid for mid, _ in self.interfaces[event]]

    async def broadcast_event(self, event: str, payload: Dict[str, Any]) -> None:
        """Broadcast event to all subscribers."""
        if not self.event_pub:
            return

        msg = Message(
            msg_type=MessageType.EVENT,
            sender="engine",
            event=event,
            payload=payload
        )

        # Send as [topic, message]
        await self.event_pub.send_multipart([
            event.encode(),
            serialize(msg)
        ])

    async def _handle_registrations(self) -> None:
        """Handle module registration requests."""
        while self._running:
            try:
                if not self.reg_socket:
                    await asyncio.sleep(0.1)
                    continue

                # Check for incoming messages
                if await self.reg_socket.poll(100):
                    frames = await self.reg_socket.recv_multipart()
                    await self._process_registration(frames)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Registration error: {e}")

    async def _process_registration(self, frames: List[bytes]) -> None:
        """Process a registration request."""
        # frames: [identity, empty, message]
        if len(frames) < 3:
            return

        identity = frames[0]
        msg_data = frames[2] if frames[1] == b"" else frames[1]

        try:
            msg = deserialize(msg_data)

            if msg.msg_type == MessageType.REGISTER:
                # Extract module info from payload
                module_id = msg.payload.get("module_id")
                host = msg.payload.get("host", "127.0.0.1")
                port = msg.payload.get("port", 0)
                interfaces_data = msg.payload.get("interfaces", [])

                interfaces = [
                    Interface(
                        name=i["name"],
                        pattern=InterfacePattern(i["pattern"]),
                        event_type=i.get("event_type", i["name"]),
                        durability=DurabilityLevel(i.get("durability", 1))
                    )
                    for i in interfaces_data
                ]

                module_info = ModuleInfo(
                    module_id=module_id,
                    endpoint=Endpoint(host, port),
                    interfaces=interfaces,
                    metadata=msg.payload.get("metadata", {})
                )

                self.register_module(module_info)

                # Send acknowledgment
                ack = Message(
                    msg_type=MessageType.ACK,
                    sender="engine",
                    event="register_ack",
                    payload={"status": "ok", "module_id": module_id}
                )
                await self.reg_socket.send_multipart([identity, serialize(ack)])

        except Exception as e:
            print(f"Failed to process registration: {e}")

    async def _handle_events(self) -> None:
        """Handle incoming events from modules."""
        while self._running:
            try:
                await asyncio.sleep(0.1)  # Placeholder
            except asyncio.CancelledError:
                break

    async def _handle_heartbeats(self) -> None:
        """Handle incoming heartbeats."""
        while self._running:
            try:
                await asyncio.sleep(0.1)  # Placeholder
            except asyncio.CancelledError:
                break

    async def _handle_acks(self) -> None:
        """Handle ACK responses."""
        while self._running:
            try:
                await asyncio.sleep(0.1)  # Placeholder
            except asyncio.CancelledError:
                break

    async def _monitor_peers(self) -> None:
        """Monitor peer health via heartbeats."""
        while self._running:
            try:
                expired = self.heartbeat_manager.tick_all()
                for module_id in expired:
                    print(f"Module {module_id} expired")
                    self.unregister_module(module_id)

                await asyncio.sleep(HEARTBEAT_INTERVAL)
            except asyncio.CancelledError:
                break

    async def _run_event_proxy(self) -> None:
        """Run XPUB/XSUB proxy for event distribution."""
        try:
            # Use zmq.proxy for efficient forwarding
            # This runs until cancelled
            while self._running:
                if self.event_sub and self.event_pub:
                    # Manual proxy to allow cancellation
                    if await self.event_sub.poll(100):
                        msg = await self.event_sub.recv_multipart()
                        await self.event_pub.send_multipart(msg)
                await asyncio.sleep(0.001)
        except asyncio.CancelledError:
            pass
