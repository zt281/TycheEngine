"""Schema management for ClickHouse persistence backend.

Provides DDL constants and SchemaManager for idempotent table creation
and lightweight schema versioning via a schema_meta table.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)

CURRENT_SCHEMA_VERSION = 1

EVENTS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS events (
    timestamp DateTime64(3),
    event_type LowCardinality(String),
    instrument_id LowCardinality(String),
    module_id String,
    payload String
) ENGINE = MergeTree()
PARTITION BY toYYYYMMDD(timestamp)
ORDER BY (timestamp, instrument_id, event_type)
"""

SCHEMA_META_DDL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    version UInt32,
    applied_at DateTime64(3)
) ENGINE = MergeTree()
ORDER BY version
"""


class SchemaManager:
    """Manages ClickHouse schema creation and version tracking.

    Uses duck-typed ``client`` with ``.command(sql: str)`` and
    ``.query(sql: str)`` methods (compatible with clickhouse_connect.Client).
    All operations are idempotent (CREATE TABLE IF NOT EXISTS).
    """

    def __init__(self, database: str = "tyche") -> None:
        """Initialise the schema manager.

        Args:
            database: ClickHouse database name.  Tables are created in this
                database; callers should ensure the database itself exists.
        """
        self.database = database

    def ensure_schema(self, client: Any) -> bool:
        """Create tables and set schema version if not present.

        Executes both DDLs via ``client.command()``.  If ``schema_meta`` is
        empty after creation, inserts the current version row.

        Args:
            client: Duck-typed client with ``.command(sql)`` and
                ``.query(sql)`` methods.

        Returns:
            True on success, False on failure.
        """
        try:
            client.command(EVENTS_TABLE_DDL)
            client.command(SCHEMA_META_DDL)

            version = self.get_version(client)
            if version == 0:
                insert_sql = (
                    f"INSERT INTO schema_meta (version, applied_at) "
                    f"VALUES ({CURRENT_SCHEMA_VERSION}, now64(3))"
                )
                client.command(insert_sql)
                logger.info(
                    "Schema version %d inserted into schema_meta",
                    CURRENT_SCHEMA_VERSION,
                )

            logger.info("Schema ensured successfully (version %d)", CURRENT_SCHEMA_VERSION)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to ensure schema: %s", exc)
            return False

    def get_version(self, client: Any) -> int:
        """Return the current schema version from schema_meta.

        Args:
            client: Duck-typed client with ``.query(sql)`` method.

        Returns:
            Version number (0 if table is empty or query fails).
        """
        try:
            result = client.query(
                "SELECT version FROM schema_meta ORDER BY version DESC LIMIT 1"
            )
            rows = getattr(result, "result_rows", [])
            if rows:
                return int(rows[0][0])
            return 0
        except Exception as exc:  # noqa: BLE001
            logger.error("Failed to get schema version: %s", exc)
            return 0
