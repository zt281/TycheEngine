"""Abstract base class and result types for persistence backends.

All backend implementations (ClickHouse, JSONL, etc.) implement the
PersistenceBackend interface. Result types use explicit dataclasses with
to_dict/from_dict for serialization round-trips.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


@dataclass
class InsertResult:
    """Result of a batch insert operation.

    Fields:
        success: Whether the insert succeeded.
        rows_inserted: Number of rows successfully inserted (0 on failure).
        error: Operational error message, or None on success.
    """

    success: bool
    rows_inserted: int = 0
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "success": self.success,
            "rows_inserted": self.rows_inserted,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "InsertResult":
        """Reconstruct from a plain dict."""
        return cls(
            success=d["success"],
            rows_inserted=d.get("rows_inserted", 0),
            error=d.get("error"),
        )


@dataclass
class QueryResult:
    """Result of a query operation.

    Fields:
        success: Whether the query succeeded.
        rows: List of row dicts returned by the query.
        error: Operational error message, or None on success.
    """

    success: bool
    rows: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Serialize to a plain dict."""
        return {
            "success": self.success,
            "rows": self.rows,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "QueryResult":
        """Reconstruct from a plain dict."""
        return cls(
            success=d["success"],
            rows=d.get("rows", []),
            error=d.get("error"),
        )


class PersistenceBackend(ABC):
    """Abstract base class for persistence backend implementations.

    Subclasses provide concrete storage (ClickHouse, JSONL, etc.) while
    this base defines the contract for insert, query, health, schema, and
    lifecycle operations.
    """

    @abstractmethod
    def insert_batch(self, rows: List[Dict[str, Any]]) -> InsertResult:
        """Insert a batch of event rows into the backend.

        Args:
            rows: List of row dicts. Each dict must contain at minimum
                ``timestamp`` (float), ``event_type`` (str),
                ``instrument_id`` (str), ``module_id`` (str), and
                ``payload`` (str) keys.

        Returns:
            InsertResult with success flag, row count, and optional error.
        """
        ...

    @abstractmethod
    def query(
        self,
        start_ts: Optional[float] = None,
        end_ts: Optional[float] = None,
        event_type: Optional[str] = None,
        instrument_id: Optional[str] = None,
        module_id: Optional[str] = None,
        limit: int = 1000,
        offset: int = 0,
    ) -> QueryResult:
        """Query events from the backend.

        All filter parameters are optional. When omitted, the query is
        unconstrained in that dimension. ``limit`` defaults to 1000 to
        prevent unbounded result sets.

        Args:
            start_ts: Minimum timestamp (inclusive), as Unix seconds.
            end_ts: Maximum timestamp (inclusive), as Unix seconds.
            event_type: Filter by event type string.
            instrument_id: Filter by instrument identifier.
            module_id: Filter by originating module identifier.
            limit: Maximum rows to return (default 1000).
            offset: Rows to skip for pagination (default 0).

        Returns:
            QueryResult with success flag, row list, and optional error.
        """
        ...

    @abstractmethod
    def health(self) -> Dict[str, Any]:
        """Return backend health status.

        Returns:
            Dict with at minimum a ``status`` key set to one of
            ``"ok"``, ``"degraded"``, or ``"unavailable"``.
        """
        ...

    @abstractmethod
    def close(self) -> None:
        """Release any resources held by the backend.

        Safe to call multiple times.
        """
        ...

    @abstractmethod
    def ensure_schema(self) -> bool:
        """Ensure the required schema exists in the backend.

        Implementations should be idempotent (CREATE IF NOT EXISTS).

        Returns:
            True if schema is ready, False on failure.
        """
        ...
