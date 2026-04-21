"""Integration tests for ClickHouseBackend with real ClickHouse.

Requires Docker ClickHouse running:
    docker compose -f docker/clickhouse-compose.yml up -d
"""

import time
from typing import Generator

import pytest

from modules.trading.persistence.clickhouse_backend import ClickHouseBackend
from modules.trading.persistence.schema import SchemaManager


@pytest.fixture
def backend() -> Generator[ClickHouseBackend, None, None]:
    """Create a ClickHouseBackend connected to local Docker ClickHouse."""
    b = ClickHouseBackend(
        host="localhost",
        port=8123,
        database="tyche",
        user="default",
        password="",
    )
    try:
        yield b
    finally:
        b.close()


def _wait_for_clickhouse(max_wait: float = 5.0) -> None:
    """Poll health until ClickHouse is ready or timeout."""
    b = ClickHouseBackend(host="localhost", port=8123, database="tyche")
    deadline = time.time() + max_wait
    while time.time() < deadline:
        h = b.health()
        if h.get("status") == "ok":
            b.close()
            return
        time.sleep(0.3)
    b.close()
    pytest.skip("ClickHouse not available -- run 'docker compose -f docker/clickhouse-compose.yml up -d'")


def test_health_check():
    """Backend reports healthy when ClickHouse is reachable."""
    _wait_for_clickhouse()
    b = ClickHouseBackend(host="localhost", port=8123, database="tyche")
    try:
        h = b.health()
        assert h["status"] == "ok"
        assert h["backend"] == "clickhouse"
        assert h["database"] == "tyche"
    finally:
        b.close()


def test_ensure_schema_creates_tables(backend: ClickHouseBackend):
    """SchemaManager creates events and schema_meta tables."""
    _wait_for_clickhouse()
    assert backend.ensure_schema() is True

    # Verify tables exist by querying system.tables
    client = backend._get_client()
    tables = client.query(
        "SELECT name FROM system.tables WHERE database = 'tyche' AND name IN ('events', 'schema_meta')"
    )
    table_names = {r[0] for r in tables.result_rows}
    assert "events" in table_names
    assert "schema_meta" in table_names


def test_schema_version_tracking(backend: ClickHouseBackend):
    """Schema version is recorded after ensure_schema."""
    _wait_for_clickhouse()
    backend.ensure_schema()
    sm = SchemaManager(database="tyche")
    version = sm.get_version(backend._get_client())
    assert version == 1


def test_insert_and_query_roundtrip(backend: ClickHouseBackend):
    """Inserted rows are queryable with correct data."""
    _wait_for_clickhouse()
    backend.ensure_schema()

    # Clean any existing test data
    client = backend._get_client()
    client.command("TRUNCATE TABLE IF EXISTS tyche.events")

    rows = [
        {
            "timestamp": 1700000000.0,
            "event_type": "quote",
            "instrument_id": "IF2501",
            "module_id": "gateway_ctp",
            "payload": b"\x81\xa5price\xcb@Y\x06\x24\xdd\x2f\x1b\x00",  # msgpack bytes
        },
        {
            "timestamp": 1700000001.0,
            "event_type": "trade",
            "instrument_id": "IF2501",
            "module_id": "gateway_ctp",
            "payload": b"\x81\xa4size\xcd\x00\x64",  # msgpack bytes
        },
        {
            "timestamp": 1700000002.0,
            "event_type": "quote",
            "instrument_id": "IF2502",
            "module_id": "gateway_ctp",
            "payload": b"\x81\xa5price\xcb@Y\x06\x24\xdd\x2f\x1b\x00",
        },
    ]

    result = backend.insert_batch(rows)
    assert result.success is True
    assert result.rows_inserted == 3
    assert result.error is None

    # Query all
    qr = backend.query()
    assert qr.success is True
    assert len(qr.rows) == 3
    assert qr.rows[0]["event_type"] == "quote"
    assert qr.rows[0]["instrument_id"] == "IF2501"


def test_query_time_range_filter(backend: ClickHouseBackend):
    """Query filters by start_ts and end_ts."""
    _wait_for_clickhouse()
    backend.ensure_schema()
    client = backend._get_client()
    client.command("TRUNCATE TABLE IF EXISTS tyche.events")

    rows = [
        {"timestamp": 1700000000.0, "event_type": "quote", "instrument_id": "IF2501", "module_id": "m1", "payload": b"x"},
        {"timestamp": 1700000010.0, "event_type": "quote", "instrument_id": "IF2501", "module_id": "m1", "payload": b"x"},
        {"timestamp": 1700000020.0, "event_type": "quote", "instrument_id": "IF2501", "module_id": "m1", "payload": b"x"},
    ]
    backend.insert_batch(rows)

    qr = backend.query(start_ts=1700000005.0, end_ts=1700000015.0)
    assert len(qr.rows) == 1
    assert qr.rows[0]["timestamp"] == 1700000010.0


def test_query_event_type_filter(backend: ClickHouseBackend):
    """Query filters by event_type."""
    _wait_for_clickhouse()
    backend.ensure_schema()
    client = backend._get_client()
    client.command("TRUNCATE TABLE IF EXISTS tyche.events")

    rows = [
        {"timestamp": 1700000000.0, "event_type": "quote", "instrument_id": "IF2501", "module_id": "m1", "payload": b"x"},
        {"timestamp": 1700000001.0, "event_type": "trade", "instrument_id": "IF2501", "module_id": "m1", "payload": b"x"},
    ]
    backend.insert_batch(rows)

    qr = backend.query(event_type="trade")
    assert len(qr.rows) == 1
    assert qr.rows[0]["event_type"] == "trade"


def test_query_instrument_id_filter(backend: ClickHouseBackend):
    """Query filters by instrument_id."""
    _wait_for_clickhouse()
    backend.ensure_schema()
    client = backend._get_client()
    client.command("TRUNCATE TABLE IF EXISTS tyche.events")

    rows = [
        {"timestamp": 1700000000.0, "event_type": "quote", "instrument_id": "IF2501", "module_id": "m1", "payload": b"x"},
        {"timestamp": 1700000001.0, "event_type": "quote", "instrument_id": "IF2502", "module_id": "m1", "payload": b"x"},
    ]
    backend.insert_batch(rows)

    qr = backend.query(instrument_id="IF2502")
    assert len(qr.rows) == 1
    assert qr.rows[0]["instrument_id"] == "IF2502"


def test_query_limit(backend: ClickHouseBackend):
    """Query respects limit parameter."""
    _wait_for_clickhouse()
    backend.ensure_schema()
    client = backend._get_client()
    client.command("TRUNCATE TABLE IF EXISTS tyche.events")

    rows = [
        {"timestamp": 1700000000.0 + i, "event_type": "quote", "instrument_id": "IF2501", "module_id": "m1", "payload": b"x"}
        for i in range(10)
    ]
    backend.insert_batch(rows)

    qr = backend.query(limit=3)
    assert len(qr.rows) == 3


def test_query_order_by_timestamp(backend: ClickHouseBackend):
    """Query results are ordered by timestamp ascending."""
    _wait_for_clickhouse()
    backend.ensure_schema()
    client = backend._get_client()
    client.command("TRUNCATE TABLE IF EXISTS tyche.events")

    rows = [
        {"timestamp": 1700000005.0, "event_type": "quote", "instrument_id": "IF2501", "module_id": "m1", "payload": b"x"},
        {"timestamp": 1700000001.0, "event_type": "quote", "instrument_id": "IF2501", "module_id": "m1", "payload": b"x"},
        {"timestamp": 1700000003.0, "event_type": "quote", "instrument_id": "IF2501", "module_id": "m1", "payload": b"x"},
    ]
    backend.insert_batch(rows)

    qr = backend.query()
    timestamps = [r["timestamp"] for r in qr.rows]
    assert timestamps == [1700000001.0, 1700000003.0, 1700000005.0]


def test_payload_bytes_roundtrip(backend: ClickHouseBackend):
    """Payload bytes survive round-trip (inserted as base64, retrieved as string)."""
    _wait_for_clickhouse()
    backend.ensure_schema()
    client = backend._get_client()
    client.command("TRUNCATE TABLE IF EXISTS tyche.events")

    original_payload = b"\x81\xa5price\xcb@Y\x06\x24\xdd\x2f\x1b\x00"
    rows = [
        {"timestamp": 1700000000.0, "event_type": "quote", "instrument_id": "IF2501", "module_id": "m1", "payload": original_payload},
    ]
    backend.insert_batch(rows)

    qr = backend.query()
    assert len(qr.rows) == 1
    # Payload is base64-encoded for storage, returned as the encoded string
    import base64
    expected_b64 = base64.b64encode(original_payload).decode("ascii")
    assert qr.rows[0]["payload"] == expected_b64
