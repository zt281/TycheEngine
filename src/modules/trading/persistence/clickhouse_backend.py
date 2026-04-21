"""ClickHouse persistence backend implementation.

Production backend using clickhouse-connect with connection pooling.
Conforms to the PersistenceBackend interface.
"""

import base64
import logging
from typing import Any, Dict, List, Optional

from modules.trading.persistence.backend import InsertResult, PersistenceBackend, QueryResult
from modules.trading.persistence.schema import SchemaManager

logger = logging.getLogger(__name__)

try:
    import clickhouse_connect
except ImportError:  # pragma: no cover
    clickhouse_connect = None  # type: ignore[assignment]


class ClickHouseBackend(PersistenceBackend):
    """ClickHouse persistence backend with connection pooling.

    Stores events in a ClickHouse ``events`` table with daily partitions.
    Payload is base64-encoded for the ``String`` column.

    Args:
        host: ClickHouse server host.
        port: ClickHouse HTTP port.
        database: Database name.
        user: Username.
        password: Password.
        secure: Use HTTPS.
        pool_size: Connection pool size.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8123,
        database: str = "tyche",
        user: str = "default",
        password: str = "",
        secure: bool = False,
        pool_size: int = 4,
        **kwargs: Any,
    ):
        self._host = host
        self._port = port
        self._database = database
        self._user = user
        self._password = password
        self._secure = secure
        self._pool_size = pool_size
        self._client: Optional[Any] = None
        self._schema_manager = SchemaManager(database=database)
        self._closed = False

    def _get_client(self) -> Any:
        """Lazy initialization of the ClickHouse client."""
        if self._client is None:
            if clickhouse_connect is None:  # pragma: no cover
                raise ImportError(
                    "clickhouse-connect is required for ClickHouseBackend. "
                    "Install with: pip install clickhouse-connect"
                )
            self._client = clickhouse_connect.get_client(
                host=self._host,
                port=self._port,
                database=self._database,
                username=self._user,
                password=self._password,
                secure=self._secure,
                pool_size=self._pool_size,
            )
        return self._client

    def ensure_schema(self) -> bool:
        """Ensure the required schema exists in ClickHouse.

        Delegates to SchemaManager.ensure_schema with the current client.
        """
        try:
            client = self._get_client()
            return self._schema_manager.ensure_schema(client)
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to ensure schema: %s", exc)
            return False

    def insert_batch(self, rows: List[Dict[str, Any]]) -> InsertResult:
        """Insert a batch of event rows into ClickHouse.

        Args:
            rows: List of row dicts with keys:
                timestamp (float), event_type (str), instrument_id (str),
                module_id (str), payload (bytes or str).

        Returns:
            InsertResult with success flag, row count, and optional error.
        """
        if self._closed:
            return InsertResult(success=False, error="backend closed")

        try:
            client = self._get_client()
            data: List[tuple] = []
            for row in rows:
                payload = row["payload"]
                if isinstance(payload, bytes):
                    payload = base64.b64encode(payload).decode("ascii")
                data.append(
                    (
                        row["timestamp"],
                        row["event_type"],
                        row["instrument_id"],
                        row["module_id"],
                        payload,
                    )
                )

            client.insert(
                "events",
                data=data,
                column_names=[
                    "timestamp",
                    "event_type",
                    "instrument_id",
                    "module_id",
                    "payload",
                ],
            )
            return InsertResult(success=True, rows_inserted=len(rows))
        except Exception as exc:  # noqa: BLE001
            logger.error("Batch insert failed: %s", exc)
            return InsertResult(success=False, error=str(exc))

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
        """Query events from ClickHouse.

        All filter parameters are optional. ``limit`` defaults to 1000.
        """
        if self._closed:
            return QueryResult(success=False, error="backend closed")

        try:
            client = self._get_client()
            conditions: List[str] = []
            if start_ts is not None:
                conditions.append(f"timestamp >= toDateTime64({start_ts}, 3)")
            if end_ts is not None:
                conditions.append(f"timestamp <= toDateTime64({end_ts}, 3)")
            if event_type is not None:
                conditions.append(f"event_type = '{event_type}'")
            if instrument_id is not None:
                conditions.append(f"instrument_id = '{instrument_id}'")
            if module_id is not None:
                conditions.append(f"module_id = '{module_id}'")

            where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
            sql = (
                f"SELECT timestamp, event_type, instrument_id, module_id, payload "
                f"FROM events {where_clause} ORDER BY timestamp LIMIT {limit} OFFSET {offset}"
            )

            result = client.query(sql)
            rows = [
                {
                    "timestamp": r[0],
                    "event_type": r[1],
                    "instrument_id": r[2],
                    "module_id": r[3],
                    "payload": r[4],
                }
                for r in getattr(result, "result_rows", [])
            ]
            return QueryResult(success=True, rows=rows)
        except Exception as exc:  # noqa: BLE001
            logger.error("Query failed: %s", exc)
            return QueryResult(success=False, error=str(exc))

    def health(self) -> Dict[str, Any]:
        """Return backend health status."""
        try:
            client = self._get_client()
            client.command("SELECT 1")
            return {
                "status": "ok",
                "backend": "clickhouse",
                "database": self._database,
            }
        except Exception as exc:  # noqa: BLE001
            logger.error("Health check failed: %s", exc)
            return {
                "status": "unavailable",
                "backend": "clickhouse",
                "error": str(exc),
            }

    def close(self) -> None:
        """Release resources held by the backend."""
        self._closed = True
        if self._client is not None:
            try:
                self._client.close()
            except Exception as exc:  # noqa: BLE001
                logger.error("Error closing client: %s", exc)
            self._client = None
