# TODOS

Items deferred from plan reviews. Each entry has context for future implementers.

---

## [TODO-1] RecordingModule: explicit error test for missing parent directory

**What:** Add a unit test verifying that `RecordingModule(file_path="nonexistent/dir/recording.tyche", ...)` raises `FileNotFoundError` (or `IOError`) with a clear message when `on_start()` is called.

**Why:** The plan spec explicitly states "parent directory must pre-exist (RecordingModule does not call os.makedirs)". Without a test, a user who passes a bad path will get a stack trace from deep inside `open()` with no actionable context. A test both documents the contract and guards against future silent error-handling changes.

**Pros:** Documents the API contract. Catches any future change that silently swallows the error.

**Cons:** Minor test — only exercises a filesystem edge case, not recording correctness.

**Context:** Task 16 (RecordingModule + ReplayBus) in `docs/designs/core-engine-expansions.md`. The `on_start()` method opens the file. The parent directory check is a precondition of the constructor call. Test should be in `tests/integration/test_backtest_replay.py` or `tests/unit/test_recording.py`.

**Effort:** S (human: ~30min / CC: ~5min)

**Priority:** P3 — non-blocking, quality improvement

**Depends on:** Task 16 implemented

---
