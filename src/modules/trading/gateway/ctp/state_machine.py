"""Connection state machine for CTP gateway with auto-reconnect backoff."""
import random
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional


class ConnectionState(Enum):
    """Gateway connection lifecycle states."""
    IDLE = "IDLE"
    CONNECTING = "CONNECTING"
    CONNECTED = "CONNECTED"
    RECONNECTING = "RECONNECTING"
    DISCONNECTED = "DISCONNECTED"


@dataclass
class ReconnectConfig:
    """Auto-reconnect configuration."""
    enabled: bool = True
    max_retries: int = 10
    base_delay_ms: int = 1000
    max_delay_ms: int = 30000


_VALID_TRANSITIONS: Dict[ConnectionState, set] = {
    ConnectionState.IDLE: {ConnectionState.CONNECTING, ConnectionState.DISCONNECTED},
    ConnectionState.CONNECTING: {ConnectionState.CONNECTED, ConnectionState.DISCONNECTED},
    ConnectionState.CONNECTED: {ConnectionState.RECONNECTING, ConnectionState.DISCONNECTED},
    ConnectionState.RECONNECTING: {ConnectionState.CONNECTING, ConnectionState.DISCONNECTED},
    ConnectionState.DISCONNECTED: {ConnectionState.CONNECTING},
}


class ConnectionStateMachine:
    """Manages gateway connection state with retry tracking."""

    def __init__(
        self,
        venue: str = "openctp",
        reconnect_config: Optional[ReconnectConfig] = None,
    ):
        self._state = ConnectionState.IDLE
        self._previous_state: Optional[ConnectionState] = None
        self._venue = venue
        self._reconnect_config = reconnect_config or ReconnectConfig()
        self._retry_count = 0

    @property
    def state(self) -> ConnectionState:
        return self._state

    @property
    def previous_state(self) -> Optional[ConnectionState]:
        return self._previous_state

    @property
    def retry_count(self) -> int:
        return self._retry_count

    def transition(self, new_state: ConnectionState) -> bool:
        """Attempt a state transition. Returns True if successful."""
        valid = _VALID_TRANSITIONS.get(self._state, set())
        if new_state not in valid:
            return False
        self._previous_state = self._state
        self._state = new_state
        if new_state == ConnectionState.RECONNECTING:
            self._retry_count += 1
        return True

    def next_backoff_ms(self) -> int:
        """Calculate next reconnect delay with exponential backoff and jitter."""
        if not self._reconnect_config.enabled:
            return 0
        base = self._reconnect_config.base_delay_ms
        max_delay = self._reconnect_config.max_delay_ms
        delay = base * (2 ** max(0, self._retry_count - 1))
        delay = min(delay, max_delay)
        return int(delay)

    def max_retries_exceeded(self) -> bool:
        """Check if retry count exceeds configured max."""
        return self._retry_count > self._reconnect_config.max_retries

    def to_payload(self, reason: str = "") -> Dict[str, Any]:
        """Build state event payload."""
        return {
            "venue": self._venue,
            "previous_state": self._previous_state.value if self._previous_state else "",
            "state": self._state.value,
            "reason": reason,
            "retry_count": self._retry_count,
            "next_retry_ms": self.next_backoff_ms(),
        }
