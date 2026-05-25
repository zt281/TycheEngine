"""Additional tests for src.tyche.dead_letter to reach 85%+ coverage."""
import json
import threading
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch, mock_open

import pytest

from src.tyche.dead_letter import DeadLetterStore, _message_to_dict
from src.tyche.message import Message, MessageType
from src.tyche.types import DurabilityLevel


@pytest.fixture
def tmp_dl_dir(tmp_path):
    return tmp_path / "dead_letters"


@pytest.fixture
def dl_store(tmp_dl_dir):
    return DeadLetterStore(base_dir=tmp_dl_dir)


@pytest.fixture
def make_msg():
    def _make(event="test_event", sender="test_sender"):
        return Message(
            msg_type=MessageType.EVENT,
            sender=sender,
            event=event,
            payload={"data": "test"},
            correlation_id="corr-123",
        )
    return _make


class TestReplayEdgeCases:
    def test_replay_empty_dir_returns_empty(self, dl_store):
        """Replay on non-existent directory returns empty list."""
        results = dl_store.replay()
        assert results == []

    def test_replay_list_files_exception(self, dl_store, make_msg, caplog):
        """Exception listing files is logged and returns empty."""
        dl_store.persist(make_msg(), "topic", "reason")
        # Make the directory unreadable by patching glob
        with patch.object(Path, "glob", side_effect=PermissionError("Access denied")):
            results = dl_store.replay()
        assert results == []
        assert "Failed to list dead letter files" in caplog.text

    def test_replay_skips_empty_lines(self, dl_store, make_msg):
        """Empty lines in JSONL are skipped."""
        dl_store.persist(make_msg(), "topic", "reason")
        today = date.today().isoformat()
        file_path = dl_store._dead_letter_dir / f"{today}.jsonl"
        # Append empty lines
        with open(file_path, "a", encoding="utf-8") as f:
            f.write("\n\n")
        results = dl_store.replay()
        assert len(results) == 1

    def test_replay_skips_malformed_json(self, dl_store, make_msg, caplog):
        """Malformed JSON lines are skipped with warning."""
        dl_store.persist(make_msg(), "topic", "reason")
        today = date.today().isoformat()
        file_path = dl_store._dead_letter_dir / f"{today}.jsonl"
        # Append malformed line
        with open(file_path, "a", encoding="utf-8") as f:
            f.write("this is not json\n")
        results = dl_store.replay()
        assert len(results) == 1
        assert "Skipping malformed line" in caplog.text

    def test_replay_read_file_exception(self, dl_store, make_msg, caplog):
        """Exception reading a file is logged and skipped."""
        dl_store.persist(make_msg(), "topic", "reason")
        today = date.today().isoformat()
        file_path = dl_store._dead_letter_dir / f"{today}.jsonl"
        with patch("builtins.open", side_effect=IOError("Read error")):
            results = dl_store.replay()
        assert results == []
        assert "Failed to read dead letter file" in caplog.text

    def test_replay_filter_by_date_skips_older(self, dl_store, make_msg):
        """Date filter skips files older than since date."""
        # Write a message today
        dl_store.persist(make_msg(), "topic", "reason")

        # Create an old file manually
        old_date = (date.today() - timedelta(days=5)).isoformat()
        old_file = dl_store._dead_letter_dir / f"{old_date}.jsonl"
        old_file.parent.mkdir(parents=True, exist_ok=True)
        with open(old_file, "w", encoding="utf-8") as f:
            f.write(json.dumps({"timestamp": 1.0, "topic": "old", "reason": "old", "message": {}}) + "\n")

        # Replay since yesterday — should only get today's message
        yesterday = date.today() - timedelta(days=1)
        results = dl_store.replay(since=yesterday)
        assert len(results) == 1
        assert results[0]["topic"] == "topic"


class TestParseFileDate:
    def test_valid_date(self):
        result = DeadLetterStore._parse_file_date(Path("2024-01-15.jsonl"))
        assert result == date(2024, 1, 15)

    def test_invalid_format_returns_none(self):
        result = DeadLetterStore._parse_file_date(Path("not-a-date.jsonl"))
        assert result is None

    def test_invalid_filename_returns_none(self):
        result = DeadLetterStore._parse_file_date(Path("random.txt"))
        assert result is None

    def test_empty_stem_returns_none(self):
        result = DeadLetterStore._parse_file_date(Path(".jsonl"))
        assert result is None


class TestMessageToDict:
    def test_message_to_dict_with_enum(self, make_msg):
        msg = make_msg()
        result = _message_to_dict(msg)
        assert result["msg_type"] == "evt"
        assert result["durability"] == 1
        assert result["sender"] == "test_sender"
        assert result["event"] == "test_event"

    def test_message_to_dict_without_enum_value(self, make_msg):
        """Test fallback when msg_type doesn't have value attr."""
        msg = make_msg()
        msg.msg_type = "raw_string"  # type: ignore
        result = _message_to_dict(msg)
        assert result["msg_type"] == "raw_string"
