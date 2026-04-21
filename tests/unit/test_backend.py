"""Tests for PersistenceBackend ABC and result dataclasses."""

from typing import Any, Dict, List, Optional

import pytest

from modules.trading.persistence.backend import (
    InsertResult,
    PersistenceBackend,
    QueryResult,
)


# --- InsertResult tests ---

def test_insert_result_defaults():
    """InsertResult(success=True) has rows_inserted=0 and error=None by default."""
    result = InsertResult(success=True)
    assert result.success is True
    assert result.rows_inserted == 0
    assert result.error is None


def test_insert_result_to_dict():
    """InsertResult.to_dict returns correct dict with all fields."""
    result = InsertResult(success=True, rows_inserted=5)
    d = result.to_dict()
    assert d == {"success": True, "rows_inserted": 5, "error": None}


def test_insert_result_from_dict():
    """InsertResult.from_dict reconstructs correctly with default rows_inserted."""
    result = InsertResult.from_dict({"success": False, "error": "conn refused"})
    assert result.success is False
    assert result.rows_inserted == 0
    assert result.error == "conn refused"


def test_insert_result_roundtrip():
    """InsertResult survives to_dict -> from_dict roundtrip."""
    original = InsertResult(success=True, rows_inserted=42, error="none")
    restored = InsertResult.from_dict(original.to_dict())
    assert restored.success == original.success
    assert restored.rows_inserted == original.rows_inserted
    assert restored.error == original.error


# --- QueryResult tests ---

def test_query_result_defaults():
    """QueryResult(success=True) has rows=[] and error=None by default."""
    result = QueryResult(success=True)
    assert result.success is True
    assert result.rows == []
    assert result.error is None


def test_query_result_to_dict():
    """QueryResult.to_dict returns dict with rows list."""
    result = QueryResult(success=True, rows=[{"a": 1}])
    d = result.to_dict()
    assert d["success"] is True
    assert d["rows"] == [{"a": 1}]
    assert d["error"] is None


def test_query_result_from_dict():
    """QueryResult.from_dict reconstructs correctly with default rows."""
    result = QueryResult.from_dict({"success": False, "error": "timeout"})
    assert result.success is False
    assert result.rows == []
    assert result.error == "timeout"


def test_query_result_roundtrip():
    """QueryResult survives to_dict -> from_dict roundtrip."""
    original = QueryResult(success=True, rows=[{"x": 1}, {"y": 2}], error=None)
    restored = QueryResult.from_dict(original.to_dict())
    assert restored.success == original.success
    assert restored.rows == original.rows
    assert restored.error == original.error


# --- PersistenceBackend ABC tests ---

def test_persistence_backend_is_abc():
    """PersistenceBackend is an ABC with abstractmethods."""
    assert hasattr(PersistenceBackend, "__abstractmethods__")
    abstract_methods = PersistenceBackend.__abstractmethods__
    assert "insert_batch" in abstract_methods
    assert "query" in abstract_methods
    assert "health" in abstract_methods
    assert "close" in abstract_methods
    assert "ensure_schema" in abstract_methods


def test_persistence_backend_cannot_instantiate():
    """Cannot instantiate PersistenceBackend directly."""
    with pytest.raises(TypeError):
        PersistenceBackend()


def test_concrete_backend_can_instantiate():
    """Concrete subclass implementing all methods can be instantiated."""

    class DummyBackend(PersistenceBackend):
        def insert_batch(self, rows: List[Dict[str, Any]]) -> InsertResult:
            return InsertResult(success=True, rows_inserted=len(rows))

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
            return QueryResult(success=True)

        def health(self) -> Dict[str, Any]:
            return {"status": "ok"}

        def close(self) -> None:
            pass

        def ensure_schema(self) -> bool:
            return True

    backend = DummyBackend()
    assert backend is not None
    assert isinstance(backend, PersistenceBackend)

    # Verify methods work
    insert_result = backend.insert_batch([{"a": 1}, {"a": 2}])
    assert insert_result.success is True
    assert insert_result.rows_inserted == 2

    query_result = backend.query(event_type="trade")
    assert query_result.success is True

    health = backend.health()
    assert health["status"] == "ok"

    assert backend.ensure_schema() is True
    backend.close()
