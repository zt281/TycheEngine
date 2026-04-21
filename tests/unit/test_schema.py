"""Tests for SchemaManager with idempotent DDL and versioning."""

from unittest.mock import MagicMock

import pytest

from modules.trading.persistence.schema import (
    CURRENT_SCHEMA_VERSION,
    EVENTS_TABLE_DDL,
    SCHEMA_META_DDL,
    SchemaManager,
)


# --- DDL constant tests ---

def test_events_table_ddl_contains_create():
    """EVENTS_TABLE_DDL constant contains CREATE TABLE IF NOT EXISTS events."""
    assert "CREATE TABLE IF NOT EXISTS events" in EVENTS_TABLE_DDL


def test_schema_meta_ddl_contains_create():
    """SCHEMA_META_DDL constant contains CREATE TABLE IF NOT EXISTS schema_meta."""
    assert "CREATE TABLE IF NOT EXISTS schema_meta" in SCHEMA_META_DDL


def test_events_ddl_has_correct_columns():
    """events DDL contains correct column types."""
    assert "timestamp DateTime64(3)" in EVENTS_TABLE_DDL
    assert "event_type LowCardinality(String)" in EVENTS_TABLE_DDL
    assert "instrument_id LowCardinality(String)" in EVENTS_TABLE_DDL
    assert "module_id String" in EVENTS_TABLE_DDL
    assert "payload String" in EVENTS_TABLE_DDL


def test_events_ddl_has_engine_and_partition():
    """events DDL has MergeTree engine, partition, and order by."""
    assert "ENGINE = MergeTree()" in EVENTS_TABLE_DDL
    assert "PARTITION BY toYYYYMMDD(timestamp)" in EVENTS_TABLE_DDL
    assert "ORDER BY (timestamp, instrument_id, event_type)" in EVENTS_TABLE_DDL


def test_schema_meta_ddl_has_engine():
    """schema_meta DDL has MergeTree engine and order by."""
    assert "ENGINE = MergeTree()" in SCHEMA_META_DDL
    assert "ORDER BY version" in SCHEMA_META_DDL


def test_current_schema_version():
    """CURRENT_SCHEMA_VERSION is 1."""
    assert CURRENT_SCHEMA_VERSION == 1


# --- SchemaManager tests ---

def test_schema_manager_has_methods():
    """SchemaManager has ensure_schema and get_version methods."""
    manager = SchemaManager()
    assert hasattr(manager, "ensure_schema")
    assert hasattr(manager, "get_version")
    assert callable(manager.ensure_schema)
    assert callable(manager.get_version)


def test_ensure_schema_executes_both_ddls():
    """SchemaManager calls client.command for both DDLs and INSERTs version."""
    client = MagicMock()
    # get_version returns 0 so INSERT is triggered
    query_result = MagicMock()
    query_result.result_rows = []
    client.query.return_value = query_result

    manager = SchemaManager()

    result = manager.ensure_schema(client)

    assert result is True
    assert client.command.call_count == 3  # events DDL + schema_meta DDL + INSERT version

    calls = [call.args[0] for call in client.command.call_args_list]
    assert any("CREATE TABLE IF NOT EXISTS events" in c for c in calls)
    assert any("CREATE TABLE IF NOT EXISTS schema_meta" in c for c in calls)
    assert any("INSERT INTO schema_meta" in c for c in calls)


def test_ensure_schema_with_empty_schema_meta():
    """ensure_schema inserts version when schema_meta is empty."""
    client = MagicMock()
    # First call: events DDL
    # Second call: schema_meta DDL
    # Third call: INSERT version
    # query for version check returns empty result
    query_result = MagicMock()
    query_result.result_rows = []
    client.query.return_value = query_result

    manager = SchemaManager()
    result = manager.ensure_schema(client)

    assert result is True
    # Check that INSERT was called with version 1
    calls = [call.args[0] for call in client.command.call_args_list]
    insert_calls = [c for c in calls if "INSERT INTO schema_meta" in c]
    assert len(insert_calls) == 1
    assert str(CURRENT_SCHEMA_VERSION) in insert_calls[0]


def test_get_version_returns_zero_when_empty():
    """get_version returns 0 when no schema_meta row exists."""
    client = MagicMock()
    query_result = MagicMock()
    query_result.result_rows = []
    client.query.return_value = query_result

    manager = SchemaManager()
    version = manager.get_version(client)

    assert version == 0
    client.query.assert_called_once()
    assert "schema_meta" in client.query.call_args[0][0]


def test_get_version_returns_version_number():
    """get_version returns version number when schema_meta has a row."""
    client = MagicMock()
    query_result = MagicMock()
    query_result.result_rows = [[5]]
    client.query.return_value = query_result

    manager = SchemaManager()
    version = manager.get_version(client)

    assert version == 5


def test_ensure_schema_catches_exception():
    """ensure_schema returns False when client.command raises."""
    client = MagicMock()
    client.command.side_effect = Exception("connection refused")

    manager = SchemaManager()
    result = manager.ensure_schema(client)

    assert result is False


def test_get_version_catches_exception():
    """get_version returns 0 when client.query raises."""
    client = MagicMock()
    client.query.side_effect = Exception("connection refused")

    manager = SchemaManager()
    version = manager.get_version(client)

    assert version == 0


def test_schema_manager_database_default():
    """SchemaManager defaults database to 'tyche'."""
    manager = SchemaManager()
    assert manager.database == "tyche"


def test_schema_manager_database_override():
    """SchemaManager accepts custom database name."""
    manager = SchemaManager(database="mydb")
    assert manager.database == "mydb"


def test_ensure_schema_skips_insert_when_version_exists():
    """ensure_schema does not INSERT version if schema_meta already has a row."""
    client = MagicMock()
    # query returns existing version
    query_result = MagicMock()
    query_result.result_rows = [[1]]
    client.query.return_value = query_result

    manager = SchemaManager()
    result = manager.ensure_schema(client)

    assert result is True
    # Should only have 2 command calls (both DDLs), no INSERT
    calls = [call.args[0] for call in client.command.call_args_list]
    insert_calls = [c for c in calls if "INSERT INTO schema_meta" in c]
    assert len(insert_calls) == 0
