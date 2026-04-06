"""Core type definitions for Tyche Engine."""

import hashlib
import random
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

# Paranoid Pirate Pattern constants
HEARTBEAT_INTERVAL = 1.0  # seconds
HEARTBEAT_LIVENESS = 3    # missed heartbeats before considered dead


class ModuleId:
    """Module identifier with format: {deity_name}{6-char MD5}."""

    DEITIES = [
        "zeus", "hera", "poseidon", "hades", "athena",
        "apollo", "artemis", "ares", "aphrodite", "hermes",
        "dionysus", "demeter", "hephaestus", "hestia"
    ]

    @classmethod
    def generate(cls, deity: Optional[str] = None) -> str:
        """Generate a new module ID.

        Args:
            deity: Optional deity name. If None, random selection.

        Returns:
            Module ID string in format {deity}{6-char MD5}
        """
        if deity is None:
            deity = random.choice(cls.DEITIES)

        # Generate 6-char MD5 hash suffix
        hash_input = f"{deity}{random.getrandbits(32)}".encode()
        hash_suffix = hashlib.md5(hash_input).hexdigest()[:6]

        return f"{deity}{hash_suffix}"


class EventType(Enum):
    """Message event types."""
    REQUEST = "request"
    RESPONSE = "response"
    EVENT = "event"
    HEARTBEAT = "heartbeat"
    REGISTER = "register"
    ACK = "ack"


class InterfacePattern(Enum):
    """Module interface naming patterns."""
    ON = "on_"           # Fire-and-forget, load-balanced
    ACK = "ack_"         # Must reply with ACK
    WHISPER = "whisper_" # Direct P2P
    ON_COMMON = "on_common_"  # Broadcast to all
    BROADCAST = "broadcast_"  # Publish via Engine


class DurabilityLevel(Enum):
    """Event persistence durability levels."""
    BEST_EFFORT = 0      # No persistence guarantee
    ASYNC_FLUSH = 1      # Async write (default)
    SYNC_FLUSH = 2       # Sync write, confirmed


class MessageType(Enum):
    """Internal message types."""
    COMMAND = "cmd"
    EVENT = "evt"
    HEARTBEAT = "hbt"
    REGISTER = "reg"
    ACK = "ack"


@dataclass
class Endpoint:
    """Network endpoint configuration."""
    host: str
    port: int

    def __str__(self) -> str:
        return f"tcp://{self.host}:{self.port}"


@dataclass
class Interface:
    """Module interface definition."""
    name: str
    pattern: InterfacePattern
    event_type: str
    durability: DurabilityLevel = DurabilityLevel.ASYNC_FLUSH


@dataclass
class ModuleInfo:
    """Module registration information."""
    module_id: str
    endpoint: Endpoint
    interfaces: List[Interface]
    metadata: Dict[str, Any]
