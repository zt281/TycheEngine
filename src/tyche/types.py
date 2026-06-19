"""Core type definitions for Tyche Engine."""

import secrets
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

# Paranoid Pirate Pattern constants
HEARTBEAT_INTERVAL = 1.0  # seconds
HEARTBEAT_LIVENESS = 3    # missed heartbeats before considered dead

# Admin endpoint default port.
#
# Port layout (mirrors C++ engine in src/tyche/cpp/engine/main.cpp):
#   Registration ROUTER:  base_port + 0  (5555)
#   Event XPUB:           base_port + 1  (5556)
#   Event XSUB:           base_port + 2  (5557)
#   Admin ROUTER:         base_port + 3  (5558)  ← ADMIN_PORT_DEFAULT
#   Heartbeat PUB:        base_port + 4  (5559)
#   Heartbeat Recv:       base_port + 5  (5560)
#   Job ROUTER:           base_port + 9  (5564)
ADMIN_PORT_DEFAULT = 5558


class ModuleId:
    """Module identifier with format: {family}_{6-char hex}."""

    @classmethod
    def generate(cls, family: str = "unknown") -> str:
        """Generate a new module ID.

        Args:
            family: Module family name (e.g. "openctp_gateway").

        Returns:
            Module ID string in format {family}_{6-char hex}
        """
        suffix = secrets.token_hex(3)  # 6 hex chars
        return f"{family}_{suffix}"


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
    wait_timeout: Optional[float] = None


@dataclass
class ModuleInfo:
    """Module registration information."""
    module_id: str
    interfaces: List[Interface]
    metadata: Dict[str, Any]
    family_name: str = ""
    admin_handlers: Dict[str, Callable] = field(default_factory=dict)
