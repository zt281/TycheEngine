"""Tyche Engine - Distributed Event-Driven Framework.

A high-performance distributed system built on ZeroMQ with:
- REQ-ROUTER: Module registration and interface discovery
- XPUB/XSUB: Event broadcasting
- DEALER-ROUTER: Direct P2P whisper messaging
- PUSH-PULL: Load-balanced work distribution
- Paranoid Pirate: Reliable heartbeat monitoring
"""

__version__ = "0.1.0"

from tyche.types import (
    ModuleId,
    EventType,
    InterfacePattern,
    DurabilityLevel,
    MessageType,
    Endpoint,
    Interface,
    ModuleInfo,
    HEARTBEAT_INTERVAL,
    HEARTBEAT_LIVENESS,
)
from tyche.message import Message, Envelope, serialize, deserialize
from tyche.heartbeat import HeartbeatMonitor, HeartbeatSender, HeartbeatManager
from tyche.module_base import ModuleBase
from tyche.module import TycheModule
from tyche.engine import TycheEngine
from tyche.example_module import ExampleModule

__all__ = [
    # Version
    "__version__",
    # Types
    "ModuleId",
    "EventType",
    "InterfacePattern",
    "DurabilityLevel",
    "MessageType",
    "Endpoint",
    "Interface",
    "ModuleInfo",
    "HEARTBEAT_INTERVAL",
    "HEARTBEAT_LIVENESS",
    # Message
    "Message",
    "Envelope",
    "serialize",
    "deserialize",
    # Heartbeat
    "HeartbeatMonitor",
    "HeartbeatSender",
    "HeartbeatManager",
    # Module
    "ModuleBase",
    "TycheModule",
    "TycheEngine",
    "ExampleModule",
]
