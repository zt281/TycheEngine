"""Core type definitions for Tyche Engine."""

import random
import secrets
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

# Paranoid Pirate Pattern constants
HEARTBEAT_INTERVAL = 1.0  # seconds
HEARTBEAT_LIVENESS = 3    # missed heartbeats before considered dead

# Admin endpoint default port
ADMIN_PORT_DEFAULT = 5560


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
            Module ID string in format {deity}{6-char hex}
        """
        if deity is None:
            deity = random.choice(cls.DEITIES)

        hash_suffix = secrets.token_hex(3)  # 6 hex chars

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
    """Module interface naming patterns (v2).

    Three message categories, each with fire-and-forget (on_*) and
    request-response (handle_*) variants.
    """
    ON_BROADCASTED = "on_broadcasted"
    HANDLE_BROADCASTED = "handle_broadcasted"
    ON_WHISPERED = "on_whispered"
    HANDLE_WHISPERED = "handle_whispered"
    ON_STREAMING = "on_streaming"
    HANDLE_STREAMING = "handle_streaming"


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
    RESPONSE = "resp"


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
