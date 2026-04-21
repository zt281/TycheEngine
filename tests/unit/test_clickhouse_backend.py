"""Tests for ClickHouseBackend with mocked clickhouse_connect client."""

from unittest.mock import MagicMock, patch

import pytest

from modules.trading.persistence.backend import InsertResult, PersistenceBackend, QueryResult
from modules.trading.persistence.clickhouse_backend import ClickHouseBackend


# --- Construction / subclass tests ---

def test_clickhouse_backend_is_subclass():
    """ClickHouseBackend is a subclass of PersistenceBackend."""
    assert issubclass(ClickHouseBackend, PersistenceBackend)


def test_clickhouse_backend_init_defaults():
    """ClickHouseBackend.__init__ stores correct defaults."""
    backend = ClickHouseBackend()
    assert backend._host == "localhost"
    assert backend._port == 8123
    assert backend._database == "tyche"
    assert backend._user == "default"
    assert backend._password == ""
    assert backend._secure is False
    assert backend._pool_size == 4
    assert backend._client is None
    assert backend._closed is False


def test_clickhouse_backend_init_overrides():
    """ClickHouseBackend accepts all config overrides."""
    backend = ClickHouseBackend(
        host="ch.example.com",
        port=9000,
        database="prod",
        user="admin",
        password="secret",
        secure=True,
        pool_size=8,
    )
    assert backend._host == "ch.example.com"
    assert backend._port == 9000
    assert backend._database == "prod"
    assert backend._user == "admin"
    assert backend._password == "secret"
    assert backend._secure is True
    assert backend._pool_size == 8


# --- Lazy client init ---

def test_clickhouse_backend_lazy_client():
    """_get_client creates client lazily via clickhouse_connect.get_client."""
    with patch("modules.trading.persistence.clickhouse_backend.clickhouse_connect") as mock_ch:
        mock_client = MagicMock()
        mock_ch.get_client.return_value = mock_client

        backend = ClickHouseBackend(host="test", port=9999)
        client = backend._get_client()

        assert client is mock_client
        mock_ch.get_client.assert_called_once_with(
            host="test",
            port=9999,
            database="tyche",
            username="default",
            password="",
            secure=False,
            pool_size=4,
        )


def test_clickhouse_backend_lazy_client_caches():
    """_get_client returns cached client on second call."""
    with patch("modules.trading.persistence.clickhouse_backend.clickhouse_connect") as mock_ch:
        mock_client = MagicMock()
        mock_ch.get_client.return_value = mock_client

        backend = ClickHouseBackend()
        c1 = backend._get_client()
        c2 = backend._get_client()

        assert c1 is c2
        mock_ch.get_client.assert_called_once()


# --- ensure_schema ---

def test_clickhouse_backend_ensure_schema_delegates():
    """ensure_schema delegates to SchemaManager.ensure_schema."""
    with patch("modules.trading.persistence.clickhouse_backend.clickhouse_connect") as mock_ch:
        mock_client = MagicMock()
        mock_ch.get_client.return_value = mock_client

        backend = ClickHouseBackend()
        with patch.object(backend._schema_manager, "ensure_schema", return_value=True) as mock_ensure:
            result = backend.ensure_schema()
            assert result is True
            mock_ensure.assert_called_once_with(mock_client)


def test_clickhouse_backend_ensure_schema_catches_exception():
    """ensure_schema returns False on exception."""
    backend = ClickHouseBackend()
    with patch.object(backend, "_get_client", side_effect=Exception("conn refused")):
        result = backend.ensure_schema()
        assert result is False


# --- insert_batch ---

def test_clickhouse_backend_insert_batch_success():
    """insert_batch returns InsertResult(success=True, rows_inserted=N)."""
    with patch("modules.trading.persistence.clickhouse_backend.clickhouse_connect") as mock_ch:
        mock_client = MagicMock()
        mock_ch.get_client.return_value = mock_client

        backend = ClickHouseBackend()
        rows = [
            {"timestamp": 1.0, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"\x01\x02"},
            {"timestamp": 2.0, "event_type": "quote", "instrument_id": "ETH", "module_id": "m2", "payload": b"\x03\x04"},
        ]

        result = backend.insert_batch(rows)

        assert result.success is True
        assert result.rows_inserted == 2
        assert result.error is None
        mock_client.insert.assert_called_once()
        call_args = mock_client.insert.call_args
        assert call_args[0][0] == "events"
        assert call_args[1]["column_names"] == [
            "timestamp", "event_type", "instrument_id", "module_id", "payload",
        ]


def test_clickhouse_backend_insert_batch_catches_exception():
    """insert_batch catches exceptions and returns InsertResult(success=False, error=str)."""
    with patch("modules.trading.persistence.clickhouse_backend.clickhouse_connect") as mock_ch:
        mock_client = MagicMock()
        mock_client.insert.side_effect = Exception("insert failed")
        mock_ch.get_client.return_value = mock_client

        backend = ClickHouseBackend()
        rows = [{"timestamp": 1.0, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"\x01"}]

        result = backend.insert_batch(rows)

        assert result.success is False
        assert result.rows_inserted == 0
        assert "insert failed" in result.error


def test_clickhouse_backend_insert_batch_when_closed():
    """insert_batch returns error when backend is closed."""
    backend = ClickHouseBackend()
    backend._closed = True

    result = backend.insert_batch([{"timestamp": 1.0, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"\x01"}])

    assert result.success is False
    assert "closed" in result.error.lower()


def test_clickhouse_backend_insert_batch_payload_bytes_encoding():
    """insert_batch base64-encodes bytes payload for ClickHouse String column."""
    with patch("modules.trading.persistence.clickhouse_backend.clickhouse_connect") as mock_ch:
        mock_client = MagicMock()
        mock_ch.get_client.return_value = mock_client

        backend = ClickHouseBackend()
        rows = [{"timestamp": 1.0, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": b"\x01\x02\x03"}]

        backend.insert_batch(rows)

        data = mock_client.insert.call_args[1]["data"]
        assert len(data) == 1
        assert data[0][4] == "AQID"  # base64 of b'\x01\x02\x03'


def test_clickhouse_backend_insert_batch_payload_string_passes_through():
    """insert_batch passes through string payload as-is."""
    with patch("modules.trading.persistence.clickhouse_backend.clickhouse_connect") as mock_ch:
        mock_client = MagicMock()
        mock_ch.get_client.return_value = mock_client

        backend = ClickHouseBackend()
        rows = [{"timestamp": 1.0, "event_type": "trade", "instrument_id": "BTC", "module_id": "m1", "payload": "hello"}]

        backend.insert_batch(rows)

        data = mock_client.insert.call_args[1]["data"]
        assert data[0][4] == "hello"


# --- query ---

def test_clickhouse_backend_query_success():
    """query returns QueryResult with parsed rows."""
    with patch("modules.trading.persistence.clickhouse_backend.clickhouse_connect") as mock_ch:
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.result_rows = [
            [1.0, "trade", "BTC", "m1", "payload1"],
            [2.0, "quote", "ETH", "m2", "payload2"],
        ]
        mock_client.query.return_value = mock_result
        mock_ch.get_client.return_value = mock_client

        backend = ClickHouseBackend()
        result = backend.query(start_ts=0.0, end_ts=10.0, limit=10)

        assert result.success is True
        assert len(result.rows) == 2
        assert result.rows[0] == {
            "timestamp": 1.0,
            "event_type": "trade",
            "instrument_id": "BTC",
            "module_id": "m1",
            "payload": "payload1",
        }


def test_clickhouse_backend_query_with_all_filters():
    """query builds SQL with all filter conditions."""
    with patch("modules.trading.persistence.clickhouse_backend.clickhouse_connect") as mock_ch:
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.result_rows = []
        mock_client.query.return_value = mock_result
        mock_ch.get_client.return_value = mock_client

        backend = ClickHouseBackend()
        backend.query(
            start_ts=1.0,
            end_ts=2.0,
            event_type="trade",
            instrument_id="BTC",
            module_id="m1",
            limit=50,
            offset=10,
        )

        sql = mock_client.query.call_args[0][0]
        assert "timestamp >= toDateTime64(1.0, 3)" in sql
        assert "timestamp <= toDateTime64(2.0, 3)" in sql
        assert "event_type = 'trade'" in sql
        assert "instrument_id = 'BTC'" in sql
        assert "module_id = 'm1'" in sql
        assert "LIMIT 50" in sql
        assert "OFFSET 10" in sql


def test_clickhouse_backend_query_no_filters():
    """query builds SQL without WHERE when no filters provided."""
    with patch("modules.trading.persistence.clickhouse_backend.clickhouse_connect") as mock_ch:
        mock_client = MagicMock()
        mock_result = MagicMock()
        mock_result.result_rows = []
        mock_client.query.return_value = mock_result
        mock_ch.get_client.return_value = mock_client

        backend = ClickHouseBackend()
        backend.query()

        sql = mock_client.query.call_args[0][0]
        assert "WHERE" not in sql
        assert "LIMIT 1000" in sql
        assert "OFFSET 0" in sql


def test_clickhouse_backend_query_catches_exception():
    """query catches exceptions and returns QueryResult(success=False, error=str)."""
    with patch("modules.trading.persistence.clickhouse_backend.clickhouse_connect") as mock_ch:
        mock_client = MagicMock()
        mock_client.query.side_effect = Exception("query failed")
        mock_ch.get_client.return_value = mock_client

        backend = ClickHouseBackend()
        result = backend.query()

        assert result.success is False
        assert result.rows == []
        assert "query failed" in result.error


def test_clickhouse_backend_query_when_closed():
    """query returns error when backend is closed."""
    backend = ClickHouseBackend()
    backend._closed = True

    result = backend.query()

    assert result.success is False
    assert "closed" in result.error.lower()


# --- health ---

def test_clickhouse_backend_health_ok():
    """health returns ok status when client responds."""
    with patch("modules.trading.persistence.clickhouse_backend.clickhouse_connect") as mock_ch:
        mock_client = MagicMock()
        mock_ch.get_client.return_value = mock_client

        backend = ClickHouseBackend(database="mydb")
        result = backend.health()

        assert result["status"] == "ok"
        assert result["backend"] == "clickhouse"
        assert result["database"] == "mydb"
        mock_client.command.assert_called_once_with("SELECT 1")


def test_clickhouse_backend_health_unavailable():
    """health returns unavailable when client fails."""
    with patch("modules.trading.persistence.clickhouse_backend.clickhouse_connect") as mock_ch:
        mock_client = MagicMock()
        mock_client.command.side_effect = Exception("connection refused")
        mock_ch.get_client.return_value = mock_client

        backend = ClickHouseBackend()
        result = backend.health()

        assert result["status"] == "unavailable"
        assert result["backend"] == "clickhouse"
        assert "connection refused" in result["error"]


# --- close ---

def test_clickhouse_backend_close_sets_flag():
    """close sets _closed flag."""
    backend = ClickHouseBackend()
    backend.close()
    assert backend._closed is True


def test_clickhouse_backend_close_closes_client():
    """close closes client and clears reference."""
    with patch("modules.trading.persistence.clickhouse_backend.clickhouse_connect") as mock_ch:
        mock_client = MagicMock()
        mock_ch.get_client.return_value = mock_client

        backend = ClickHouseBackend()
        backend._get_client()  # initialize client
        backend.close()

        assert backend._closed is True
        assert backend._client is None
        mock_client.close.assert_called_once()


def test_clickhouse_backend_close_is_idempotent():
    """close is safe to call multiple times."""
    backend = ClickHouseBackend()
    backend.close()
    backend.close()
    assert backend._closed is True
