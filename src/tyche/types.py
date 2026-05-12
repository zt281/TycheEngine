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
        "zeus", "hera", "poseidon", "hades", "example",
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
    """Module interface naming patterns (v3).

    Unified model: modules either consume events (on_*) or produce
    events (send_*). Routing semantics (broadcast, P2P, stream) are
    determined by subscriber configuration, not method name prefixes.
    """
    ON = "on"
    SEND = "send"
    HANDLE = "handle"
    REQUEST = "request"


class BackpressureStrategy(Enum):
    """Queue overflow behavior when max_queue_depth is reached."""
    DROP_OLDEST = "drop_oldest"
    DROP_NEWEST = "drop_newest"
    BLOCK_PRODUCER = "block_producer"


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
    REQUEST = "req"


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
    backpressure: BackpressureStrategy = BackpressureStrategy.DROP_OLDEST
    max_queue_depth: int = 10000


@dataclass
class ModuleInfo:
    """Module registration information."""
    module_id: str
    endpoint: Endpoint
    interfaces: List[Interface]
    metadata: Dict[str, Any]
