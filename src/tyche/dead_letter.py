"""Dead letter persistence for failed/timed-out messages.

Stores undeliverable messages in date-partitioned JSON Lines files
for later inspection and replay.
"""

import json
import logging
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.tyche.message import Message

__all__ = ["DeadLetterStore"]

logger = logging.getLogger(__name__)


def _message_to_dict(message: Message) -> Dict[str, Any]:
    """Convert a Message to a JSON-serializable dict."""
    return {
        "msg_type": message.msg_type.value if hasattr(message.msg_type, "value") else message.msg_type,
        "sender": message.sender,
        "event": message.event,
        "payload": message.payload,
        "recipient": message.recipient,
        "durability": message.durability.value if hasattr(message.durability, "value") else message.durability,
        "timestamp": message.timestamp,
        "correlation_id": message.correlation_id,
        "wait_timeout": message.wait_timeout,
        "run_timeout": message.run_timeout,
    }


class DeadLetterStore:
    """Persists failed/timed-out messages to date-partitioned JSONL files.

    Messages that cannot be delivered (due to timeout, missing handler, etc.)
    are written to ``{base_dir}/dead_letters/{YYYY-MM-DD}.jsonl`` for later
    inspection and optional replay.

    Thread-safe: concurrent writes are serialized via an internal lock.
    """

    def __init__(self, base_dir: Path) -> None:
        """Initialize with base directory for storage.

        Args:
            base_dir: Root directory; dead letters stored under
                      ``base_dir/dead_letters/``.
        """
        self._base_dir = Path(base_dir)
        self._lock = threading.Lock()

    @property
    def _dead_letter_dir(self) -> Path:
        return self._base_dir / "dead_letters"

    def persist(self, message: Message, topic: str, reason: str) -> None:
        """Persist a dead-lettered message.

        Args:
            message: The Message object that failed delivery.
            topic: The topic/event name.
            reason: Why it was dead-lettered (e.g. "wait_timeout",
                    "run_timeout", "no_handler").

        This method is thread-safe. Persistence failures are logged
        but never propagated to the caller.
        """
        record: Dict[str, Any] = {
            "timestamp": time.time(),
            "topic": topic,
            "reason": reason,
            "message": _message_to_dict(message),
        }

        try:
            today = date.today().isoformat()  # YYYY-MM-DD
            file_path = self._dead_letter_dir / f"{today}.jsonl"

            with self._lock:
                file_path.parent.mkdir(parents=True, exist_ok=True)
                with open(file_path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception:
            logger.exception("Failed to persist dead letter for topic=%s reason=%s", topic, reason)

    def replay(
        self, topic: Optional[str] = None, since: Optional[date] = None
    ) -> List[Dict[str, Any]]:
        """Query dead-lettered messages.

        Args:
            topic: Filter by topic (None = all topics).
            since: Only return messages from this date onward (None = all).

        Returns:
            List of dicts with keys: message, topic, reason, timestamp.
        """
        results: List[Dict[str, Any]] = []
        dl_dir = self._dead_letter_dir

        if not dl_dir.exists():
            return results

        try:
            files = sorted(dl_dir.glob("*.jsonl"))
        except Exception:
            logger.exception("Failed to list dead letter files")
            return results

        for file_path in files:
            # Extract date from filename
            file_date = self._parse_file_date(file_path)
            if file_date is not None and since is not None and file_date < since:
                continue

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                        except json.JSONDecodeError:
                            logger.warning("Skipping malformed line in %s", file_path)
                            continue

                        if topic is not None and record.get("topic") != topic:
                            continue

                        results.append(record)
            except Exception:
                logger.exception("Failed to read dead letter file %s", file_path)

        return results

    def count(self, topic: Optional[str] = None, since: Optional[date] = None) -> int:
        """Return count of dead-lettered messages matching the filter.

        Args:
            topic: Filter by topic (None = all topics).
            since: Only return messages from this date onward (None = all).

        Returns:
            Number of matching dead-lettered messages.
        """
        return len(self.replay(topic=topic, since=since))

    @staticmethod
    def _parse_file_date(file_path: Path) -> Optional[date]:
        """Extract date from a JSONL filename like 2024-01-15.jsonl."""
        try:
            return datetime.strptime(file_path.stem, "%Y-%m-%d").date()
        except ValueError:
            return None
