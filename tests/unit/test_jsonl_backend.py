"""Tests for JsonlBackend with temporary directories."""

import base64
import json
import time
from pathlib import Path

import pytest

from modules.trading.persistence.backend import InsertResult, PersistenceBackend, QueryResult
from modules.trading.persistence.jsonl_backend import JsonlBackend


# --- Construction / subclass tests ---

def test_jsonl_backend_is_subclass():
    """JsonlBackend is a subclass of PersistenceBackend."""
    assert issubclass(JsonlBackend, PersistenceBackend)


def test_jsonl_backend_init_defaults(tmp_path):
    """JsonlBackend.__init__ stores correct defaults and creates directory."""
    data_dir = tmp_path / "recorded"
    backend = JsonlBackend(data_dir=str(data_dir))
    assert backend._data_dir == data_dir
    assert data_dir.exists()
    assert backend._closed is False


def test_jsonl_backend_init_creates_nested_dir(tmp_path):
    """JsonlBackend creates nested directories."""
    data_dir = tmp_path / "a" / "b" / "recorded"
    backend = JsonlBackend(data_dir=str(data_dir))
    assert data_dir.exists()


# --- ensure_schema ---

def test_jsonl_backend_ensure_schema_returns_true():
    """ensure_schema returns True (no-op for file backend)."""
    backend = JsonlBackend(data_dir="/tmp/jsonl_test")
    assert backend.ensure_schema() is True


# --- insert_batch ---

def test_jsonl_backend_insert_batch_writes_files(tmp_path):
    """insert_batch writes rows to date-partitioned JSONL files."""
    backend = JsonlBackend(data_dir=str(tmp_path))
    ts = time.mktime((2024, 1, 15, 10, 30, 0, 0, 0, 0))
    rows = [
        {"timestamp": ts, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"\x01\x02"},
        {"timestamp": ts + 1, "event_type": "quote", "instrument_id": "ETH", "module_id": "m2", "payload": b"\x03\x04"},
    ]

    result = backend.insert_batch(rows)

    assert result.success is True
    assert result.rows_inserted == 2
    assert result.error is None

    # Check file was created under date partition
    date_dir = tmp_path / "2024-01-15"
    assert date_dir.exists()
    jsonl_file = date_dir / "events.jsonl"
    assert jsonl_file.exists()

    lines = jsonl_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2
    record0 = json.loads(lines[0])
    assert record0["event_type"] == "trade"
    assert record0["instrument_id"] == "BTC"


def test_jsonl_backend_insert_batch_base64_payload(tmp_path):
    """insert_batch base64-encodes bytes payload."""
    backend = JsonlBackend(data_dir=str(tmp_path))
    ts = time.mktime((2024, 1, 15, 0, 0, 0, 0, 0, 0))
    rows = [
        {"timestamp": ts, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"\x01\x02\x03"},
    ]

    backend.insert_batch(rows)

    jsonl_file = tmp_path / "2024-01-15" / "events.jsonl"
    record = json.loads(jsonl_file.read_text(encoding="utf-8").strip())
    assert record["payload"] == "AQID"  # base64 of b'\x01\x02\x03'


def test_jsonl_backend_insert_batch_string_payload(tmp_path):
    """insert_batch passes through string payload."""
    backend = JsonlBackend(data_dir=str(tmp_path))
    ts = time.mktime((2024, 1, 15, 0, 0, 0, 0, 0, 0))
    rows = [
        {"timestamp": ts, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": "hello"},
    ]

    backend.insert_batch(rows)

    jsonl_file = tmp_path / "2024-01-15" / "events.jsonl"
    record = json.loads(jsonl_file.read_text(encoding="utf-8").strip())
    assert record["payload"] == "hello"


def test_jsonl_backend_insert_batch_groups_by_date(tmp_path):
    """insert_batch groups rows by date into separate files."""
    backend = JsonlBackend(data_dir=str(tmp_path))
    ts1 = time.mktime((2024, 1, 15, 0, 0, 0, 0, 0, 0))
    ts2 = time.mktime((2024, 1, 16, 0, 0, 0, 0, 0, 0))
    rows = [
        {"timestamp": ts1, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"a"},
        {"timestamp": ts2, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"b"},
    ]

    backend.insert_batch(rows)

    assert (tmp_path / "2024-01-15" / "events.jsonl").exists()
    assert (tmp_path / "2024-01-16" / "events.jsonl").exists()


def test_jsonl_backend_insert_batch_appends(tmp_path):
    """insert_batch appends to existing files."""
    backend = JsonlBackend(data_dir=str(tmp_path))
    ts = time.mktime((2024, 1, 15, 0, 0, 0, 0, 0, 0))

    backend.insert_batch([
        {"timestamp": ts, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"a"},
    ])
    backend.insert_batch([
        {"timestamp": ts + 1, "event_type": "quote", "instrument_id": "ETH", "module_id": "m2", "payload": b"b"},
    ])

    jsonl_file = tmp_path / "2024-01-15" / "events.jsonl"
    lines = jsonl_file.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) == 2


def test_jsonl_backend_insert_batch_when_closed(tmp_path):
    """insert_batch returns error when backend is closed."""
    backend = JsonlBackend(data_dir=str(tmp_path))
    backend._closed = True

    result = backend.insert_batch([
        {"timestamp": 1.0, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"a"},
    ])

    assert result.success is False
    assert "closed" in result.error.lower()


# --- query ---

def test_jsonl_backend_query_all_rows(tmp_path):
    """query with no filters returns all rows up to limit."""
    backend = JsonlBackend(data_dir=str(tmp_path))
    ts = time.mktime((2024, 1, 15, 0, 0, 0, 0, 0, 0))
    rows = [
        {"timestamp": ts, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"a"},
        {"timestamp": ts + 1, "event_type": "quote", "instrument_id": "ETH", "module_id": "m2", "payload": b"b"},
    ]
    backend.insert_batch(rows)

    result = backend.query()

    assert result.success is True
    assert len(result.rows) == 2


def test_jsonl_backend_query_ordered_by_timestamp(tmp_path):
    """query returns rows ordered by timestamp ascending."""
    backend = JsonlBackend(data_dir=str(tmp_path))
    ts = time.mktime((2024, 1, 15, 0, 0, 0, 0, 0, 0))
    rows = [
        {"timestamp": ts + 2, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"c"},
        {"timestamp": ts, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"a"},
        {"timestamp": ts + 1, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"b"},
    ]
    backend.insert_batch(rows)

    result = backend.query()

    timestamps = [r["timestamp"] for r in result.rows]
    assert timestamps == [ts, ts + 1, ts + 2]


def test_jsonl_backend_query_filter_by_date_range(tmp_path):
    """query filters by start_ts and end_ts."""
    backend = JsonlBackend(data_dir=str(tmp_path))
    ts = time.mktime((2024, 1, 15, 12, 0, 0, 0, 0, 0))
    rows = [
        {"timestamp": ts, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"a"},
        {"timestamp": ts + 3600, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"b"},
        {"timestamp": ts + 7200, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"c"},
    ]
    backend.insert_batch(rows)

    result = backend.query(start_ts=ts + 1800, end_ts=ts + 5400)

    assert len(result.rows) == 1
    assert base64.b64decode(result.rows[0]["payload"]) == b"b"


def test_jsonl_backend_query_filter_by_event_type(tmp_path):
    """query filters by event_type."""
    backend = JsonlBackend(data_dir=str(tmp_path))
    ts = time.mktime((2024, 1, 15, 0, 0, 0, 0, 0, 0))
    rows = [
        {"timestamp": ts, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"a"},
        {"timestamp": ts + 1, "event_type": "quote", "instrument_id": "ETH", "module_id": "m2", "payload": b"b"},
    ]
    backend.insert_batch(rows)

    result = backend.query(event_type="quote")

    assert len(result.rows) == 1
    assert result.rows[0]["event_type"] == "quote"


def test_jsonl_backend_query_filter_by_instrument_id(tmp_path):
    """query filters by instrument_id."""
    backend = JsonlBackend(data_dir=str(tmp_path))
    ts = time.mktime((2024, 1, 15, 0, 0, 0, 0, 0, 0))
    rows = [
        {"timestamp": ts, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"a"},
        {"timestamp": ts + 1, "event_type": "trade", "instrument_id": "ETH", "module_id": "m2", "payload": b"b"},
    ]
    backend.insert_batch(rows)

    result = backend.query(instrument_id="ETH")

    assert len(result.rows) == 1
    assert result.rows[0]["instrument_id"] == "ETH"


def test_jsonl_backend_query_filter_by_module_id(tmp_path):
    """query filters by module_id."""
    backend = JsonlBackend(data_dir=str(tmp_path))
    ts = time.mktime((2024, 1, 15, 0, 0, 0, 0, 0, 0))
    rows = [
        {"timestamp": ts, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"a"},
        {"timestamp": ts + 1, "event_type": "trade", "instrument_id": "BTC", "module_id": "m2", "payload": b"b"},
    ]
    backend.insert_batch(rows)

    result = backend.query(module_id="m2")

    assert len(result.rows) == 1
    assert result.rows[0]["module_id"] == "m2"


def test_jsonl_backend_query_limit_and_offset(tmp_path):
    """query respects limit and offset."""
    backend = JsonlBackend(data_dir=str(tmp_path))
    ts = time.mktime((2024, 1, 15, 0, 0, 0, 0, 0, 0))
    for i in range(5):
        backend.insert_batch([
            {"timestamp": ts + i, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": str(i).encode()},
        ])

    result = backend.query(limit=2, offset=1)

    assert len(result.rows) == 2
    assert base64.b64decode(result.rows[0]["payload"]) == b"1"
    assert base64.b64decode(result.rows[1]["payload"]) == b"2"


def test_jsonl_backend_query_across_multiple_dates(tmp_path):
    """query scans all date directories."""
    backend = JsonlBackend(data_dir=str(tmp_path))
    ts1 = time.mktime((2024, 1, 15, 0, 0, 0, 0, 0, 0))
    ts2 = time.mktime((2024, 1, 16, 0, 0, 0, 0, 0, 0))
    backend.insert_batch([
        {"timestamp": ts1, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"a"},
    ])
    backend.insert_batch([
        {"timestamp": ts2, "event_type": "trade", "instrument_id": "ETH", "module_id": "m2", "payload": b"b"},
    ])

    result = backend.query()

    assert len(result.rows) == 2
    instrument_ids = {r["instrument_id"] for r in result.rows}
    assert instrument_ids == {"BTC", "ETH"}


def test_jsonl_backend_query_empty_result(tmp_path):
    """query returns empty rows when no data matches."""
    backend = JsonlBackend(data_dir=str(tmp_path))

    result = backend.query()

    assert result.success is True
    assert result.rows == []


def test_jsonl_backend_query_when_closed(tmp_path):
    """query returns error when backend is closed."""
    backend = JsonlBackend(data_dir=str(tmp_path))
    backend._closed = True

    result = backend.query()

    assert result.success is False
    assert "closed" in result.error.lower()


# --- health ---

def test_jsonl_backend_health(tmp_path):
    """health returns ok status with file count."""
    backend = JsonlBackend(data_dir=str(tmp_path))
    ts = time.mktime((2024, 1, 15, 0, 0, 0, 0, 0, 0))
    backend.insert_batch([
        {"timestamp": ts, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"a"},
    ])

    result = backend.health()

    assert result["status"] == "ok"
    assert result["backend"] == "jsonl"
    assert result["data_dir"] == str(tmp_path)
    assert result["file_count"] == 1


def test_jsonl_backend_health_empty(tmp_path):
    """health returns ok with 0 files when empty."""
    backend = JsonlBackend(data_dir=str(tmp_path))

    result = backend.health()

    assert result["status"] == "ok"
    assert result["file_count"] == 0


# --- close ---

def test_jsonl_backend_close_sets_flag(tmp_path):
    """close sets _closed flag."""
    backend = JsonlBackend(data_dir=str(tmp_path))
    backend.close()
    assert backend._closed is True


def test_jsonl_backend_close_is_idempotent(tmp_path):
    """close is safe to call multiple times."""
    backend = JsonlBackend(data_dir=str(tmp_path))
    backend.close()
    backend.close()
    assert backend._closed is True
