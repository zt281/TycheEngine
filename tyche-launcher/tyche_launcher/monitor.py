"""Process monitoring with circuit breaker."""

import time
import os
from collections import deque
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class CircuitBreaker:
    """Circuit breaker to prevent restart storms.

    Tracks failures within a time window and opens the circuit
    when failures exceed the threshold.
    """
    max_failures: int
    window_seconds: int
    _failures: deque = field(default_factory=deque)

    def can_execute(self) -> bool:
        """Check if execution is allowed.

        Returns True if failures within window are below max_failures.
        """
        self._cleanup_old_failures()
        return len(self._failures) < self.max_failures

    def record_failure(self) -> None:
        """Record a failure."""
        self._failures.append(time.time())

    def record_success(self) -> None:
        """Record a success - clears all failures."""
        self._failures.clear()

    def _cleanup_old_failures(self) -> None:
        """Remove failures outside the window."""
        cutoff = time.time() - self.window_seconds
        while self._failures and self._failures[0] < cutoff:
            self._failures.popleft()


@dataclass
class ProcessMonitor:
    """Monitor for a single module process.

    Tracks process state, restarts, and applies restart policies.
    """
    name: str
    restart_policy: str  # "never", "always", "on-failure"
    max_restarts: int = 3
    restart_window_seconds: int = 60
    cpu_core: int = -1

    start_count: int = 0
    restart_count: int = 0
    last_exit_code: int = 0
    pid: Optional[int] = None
    last_start_time: float = 0
    _circuit_breaker: CircuitBreaker = field(
        default_factory=lambda: CircuitBreaker(max_failures=3, window_seconds=60)
    )

    def __post_init__(self):
        self._circuit_breaker = CircuitBreaker(
            max_failures=self.max_restarts,
            window_seconds=self.restart_window_seconds
        )

    def record_start(self) -> None:
        """Record a process start."""
        self.start_count += 1
        self.pid = os.getpid()
        self.last_start_time = time.time()

    def record_exit(self, code: int) -> None:
        """Record a process exit."""
        self.last_exit_code = code

        if code != 0 and self.restart_policy == "on-failure":
            self._circuit_breaker.record_failure()
            self.restart_count += 1
        elif code == 0:
            # Successful exit clears circuit breaker
            self._circuit_breaker.record_success()

    def is_healthy(self) -> bool:
        """Check if process is healthy (has a pid and not exceeded restarts)."""
        if self.pid is None:
            return False
        return self.should_restart() or self.last_exit_code == 0

    def should_restart(self) -> bool:
        """Determine if process should be restarted based on policy."""
        if self.restart_policy == "never":
            return False

        if self.restart_policy == "always":
            return self._circuit_breaker.can_execute()

        if self.restart_policy == "on-failure":
            if self.last_exit_code == 0:
                return False
            return self._circuit_breaker.can_execute()

        return False

    def get_status(self) -> dict:
        """Get current status as a dict."""
        return {
            "name": self.name,
            "restart_policy": self.restart_policy,
            "start_count": self.start_count,
            "restart_count": self.restart_count,
            "last_exit_code": self.last_exit_code,
            "pid": self.pid,
            "healthy": self.is_healthy(),
            "should_restart": self.should_restart(),
        }
