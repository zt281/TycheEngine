"""JSONL file-based persistence backend implementation.

Dev/test fallback backend that writes events to date-partitioned JSONL files.
Refactored from the existing DataRecorderModule pattern.
Conforms to the PersistenceBackend interface.
"""

import base64
import json
import logging
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from modules.trading.persistence.backend import InsertResult, PersistenceBackend, QueryResult

logger = logging.getLogger(__name__)


class JsonlBackend(PersistenceBackend):
    """File-based persistence backend using date-partitioned JSONL files.

    File layout::

        {data_dir}/{date}/events.jsonl

    Each line is a JSON object with keys: timestamp, event_type,
    instrument_id, module_id, payload.

    Args:
        data_dir: Root directory for JSONL files.
    """

    def __init__(self, data_dir: str = "./data/recorded", **kwargs: Any):
        self._data_dir = Path(data_dir)
        self._data_dir.mkdir(parents=True, exist_ok=True)
        self._closed = False
        self._event_count = 0

    def ensure_schema(self) -> bool:
        """No schema needed for file backend."""
        return True

    def insert_batch(self, rows: List[Dict[str, Any]]) -> InsertResult:
        """Insert a batch of event rows into JSONL files.

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
            # Group rows by date
            by_date: Dict[str, List[Dict[str, Any]]] = {}
            for row in rows:
                date_str = time.strftime("%Y-%m-%d", time.localtime(row["timestamp"]))
                by_date.setdefault(date_str, []).append(row)

            # Write each date group to its file
            for date_str, date_rows in by_date.items():
                file_path = self._data_dir / date_str / "events.jsonl"
                file_path.parent.mkdir(parents=True, exist_ok=True)

                with open(file_path, "a", encoding="utf-8") as f:
                    for row in date_rows:
                        record = dict(row)
                        payload = record["payload"]
                        if isinstance(payload, bytes):
                            record["payload"] = base64.b64encode(payload).decode("ascii")
                        f.write(json.dumps(record, default=str) + "\n")
                        self._event_count += 1

            return InsertResult(success=True, rows_inserted=len(rows))
        except OSError as exc:
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
        """Query events from JSONL files.

        Scans all JSONL files under data_dir, filters, and returns matching
        rows sorted by timestamp ascending.
        """
        if self._closed:
            return QueryResult(success=False, error="backend closed")

        try:
            all_rows: List[Dict[str, Any]] = []

            for jsonl_file in self._data_dir.rglob("*.jsonl"):
                try:
                    with open(jsonl_file, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            row = json.loads(line)

                            # Apply filters
                            if start_ts is not None and row.get("timestamp", 0) < start_ts:
                                continue
                            if end_ts is not None and row.get("timestamp", 0) > end_ts:
                                continue
                            if event_type is not None and row.get("event_type") != event_type:
                                continue
                            if instrument_id is not None and row.get("instrument_id") != instrument_id:
                                continue
                            if module_id is not None and row.get("module_id") != module_id:
                                continue

                            all_rows.append(row)
                except (OSError, json.JSONDecodeError) as exc:
                    logger.error("Error reading %s: %s", jsonl_file, exc)
                    continue

            # Sort by timestamp ascending
            all_rows.sort(key=lambda r: r.get("timestamp", 0.0))

            # Apply offset and limit
            result_rows = all_rows[offset : offset + limit]

            return QueryResult(success=True, rows=result_rows)
        except Exception as exc:  # noqa: BLE001
            logger.error("Query failed: %s", exc)
            return QueryResult(success=False, error=str(exc))

    def health(self) -> Dict[str, Any]:
        """Return backend health status."""
        file_count = len(list(self._data_dir.rglob("*.jsonl")))
        return {
            "status": "ok",
            "backend": "jsonl",
            "data_dir": str(self._data_dir),
            "file_count": file_count,
        }

    def close(self) -> None:
        """Release resources held by the backend."""
        self._closed = True
