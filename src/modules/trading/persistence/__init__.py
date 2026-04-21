"""Persistence backends for TycheEngine event storage.

Provides swappable storage implementations:
- ClickHouseBackend: Production backend with connection pooling
- JsonlBackend: Dev/test fallback with file-based storage
- PersistenceBackend: Abstract base class for custom backends
- SchemaManager: ClickHouse schema creation and versioning
"""

from modules.trading.persistence.backend import (
    InsertResult,
    PersistenceBackend,
    QueryResult,
)
from modules.trading.persistence.clickhouse_backend import ClickHouseBackend
from modules.trading.persistence.jsonl_backend import JsonlBackend
from modules.trading.persistence.schema import SchemaManager

__all__ = [
    "ClickHouseBackend",
    "InsertResult",
    "JsonlBackend",
    "PersistenceBackend",
    "QueryResult",
    "SchemaManager",
]
