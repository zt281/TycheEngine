"""Tyche Engine - Distributed Event-Driven Framework.

A high-performance distributed system built on ZeroMQ with:
- REQ-ROUTER: Module registration and interface discovery
- XPUB/XSUB: Event broadcasting
- DEALER-ROUTER: Direct P2P whisper messaging
- PUSH-PULL: Load-balanced work distribution
- Paranoid Pirate: Reliable heartbeat monitoring
"""

__version__ = "0.1.0"

from src.tyche.dead_letter import DeadLetterStore
from src.tyche.engine import TycheEngine
from src.tyche.heartbeat import HeartbeatManager, HeartbeatMonitor, HeartbeatSender
from src.tyche.message import Envelope, Message, deserialize, serialize
from src.tyche.module import TycheModule
from src.tyche.module_base import ModuleBase
from src.tyche.types import (
    HEARTBEAT_INTERVAL,
    HEARTBEAT_LIVENESS,
    DurabilityLevel,
    Endpoint,
    EventType,
    Interface,
    InterfacePattern,
    MessageType,
    ModuleId,
    ModuleInfo,
)

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
    # Dead Letter
    "DeadLetterStore",
]
