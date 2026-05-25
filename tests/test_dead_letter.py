"""Tests for dead letter persistence."""
import json
import threading
import time
from datetime import date
from pathlib import Path

import pytest

from src.tyche.dead_letter import DeadLetterStore
from src.tyche.message import Message, MessageType
from src.tyche.types import DurabilityLevel


class TestDeadLetterPersist:
    """Tests for DeadLetterStore.persist()."""

    def test_persist_creates_date_partitioned_file(self, dead_letter_store, make_message):
        """Verify file created at correct date-partitioned path."""
        msg = make_message()
        dead_letter_store.persist(message=msg, topic="test_topic", reason="test_reason")

        today = date.today().isoformat()
        expected_file = dead_letter_store._base_dir / "dead_letters" / f"{today}.jsonl"
        assert expected_file.exists()

    def test_persist_writes_valid_jsonl(self, dead_letter_store, make_message):
        """Each line is valid JSON with expected fields."""
        msg = make_message(event="my_event", sender="sender_mod")
        dead_letter_store.persist(message=msg, topic="my_topic", reason="wait_timeout")

        today = date.today().isoformat()
        file_path = dead_letter_store._base_dir / "dead_letters" / f"{today}.jsonl"

        with open(file_path, "r", encoding="utf-8") as f:
            line = f.readline().strip()

        record = json.loads(line)
        assert "timestamp" in record
        assert record["topic"] == "my_topic"
        assert record["reason"] == "wait_timeout"
        assert "message" in record
        assert record["message"]["sender"] == "sender_mod"
        assert record["message"]["event"] == "my_event"

    def test_persist_is_thread_safe(self, dead_letter_store, make_message):
        """Multiple threads writing simultaneously don't corrupt data."""
        num_threads = 10
        messages_per_thread = 20
        threads = []

        def writer(thread_id):
            for i in range(messages_per_thread):
                msg = make_message(
                    sender=f"thread_{thread_id}",
                    event=f"event_{i}",
                )
                dead_letter_store.persist(
                    message=msg, topic=f"topic_{thread_id}", reason="test"
                )

        for t_id in range(num_threads):
            t = threading.Thread(target=writer, args=(t_id,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        # Verify all messages were written and are valid JSON
        results = dead_letter_store.replay()
        assert len(results) == num_threads * messages_per_thread

        # Verify each record is well-formed
        for record in results:
            assert "timestamp" in record
            assert "topic" in record
            assert "reason" in record
            assert "message" in record

    def test_persist_handles_errors_gracefully(self, make_message):
        """Invalid path doesn't crash (no exception propagated)."""
        # Use a path that likely can't be written (invalid chars on Windows)
        store = DeadLetterStore(base_dir=Path("Z:\\nonexistent\\path\\impossible"))
        msg = make_message()
        # Should not raise — errors are logged internally
        store.persist(message=msg, topic="test", reason="test")


class TestDeadLetterReplay:
    """Tests for DeadLetterStore.replay()."""

    def test_replay_returns_all_messages(self, dead_letter_store, make_message):
        """Replay without filters returns everything."""
        for i in range(5):
            msg = make_message(event=f"event_{i}")
            dead_letter_store.persist(message=msg, topic=f"topic_{i}", reason="test")

        results = dead_letter_store.replay()
        assert len(results) == 5

    def test_replay_filters_by_topic(self, dead_letter_store, make_message):
        """Only returns messages matching topic."""
        for i in range(3):
            msg = make_message(event=f"event_a_{i}")
            dead_letter_store.persist(message=msg, topic="topic_a", reason="test")

        for i in range(2):
            msg = make_message(event=f"event_b_{i}")
            dead_letter_store.persist(message=msg, topic="topic_b", reason="test")

        results_a = dead_letter_store.replay(topic="topic_a")
        results_b = dead_letter_store.replay(topic="topic_b")

        assert len(results_a) == 3
        assert len(results_b) == 2
        assert all(r["topic"] == "topic_a" for r in results_a)
        assert all(r["topic"] == "topic_b" for r in results_b)

    def test_replay_filters_by_date(self, dead_letter_store, make_message):
        """Only returns messages from specified date onward."""
        # Write a message today
        msg = make_message()
        dead_letter_store.persist(message=msg, topic="test", reason="test")

        # Replay with today's date should return it
        today = date.today()
        results = dead_letter_store.replay(since=today)
        assert len(results) == 1

        # Replay with tomorrow's date should return nothing
        from datetime import timedelta
        tomorrow = today + timedelta(days=1)
        results = dead_letter_store.replay(since=tomorrow)
        assert len(results) == 0

    def test_count_matches_replay_length(self, dead_letter_store, make_message):
        """count() matches len(replay())."""
        for i in range(4):
            msg = make_message(event=f"event_{i}")
            dead_letter_store.persist(
                message=msg,
                topic="counted_topic" if i < 3 else "other_topic",
                reason="test",
            )

        assert dead_letter_store.count() == len(dead_letter_store.replay())
        assert dead_letter_store.count(topic="counted_topic") == 3
        assert dead_letter_store.count(topic="other_topic") == 1
