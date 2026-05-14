# State: TycheEngine

## Project Reference

See: .planning/PROJECT.md (updated 2026-05-14)

**Core value:** All events flowing through TycheEngine can be persisted to a database for replay, audit, and analysis.
**Current focus:** Milestone v1.0 — Persistence Module

## Current Position

Phase: Not started (defining requirements)
Plan: —
Status: Defining requirements
Last activity: 2026-05-14 — Milestone v1.0 Persistence Module started

## Accumulated Context

- TycheEngine is a ZeroMQ-based event broker for trading systems
- Existing module base class: `TycheModule` in `src/tyche/module.py`
- Existing message serialization: `Message` with MessagePack in `src/tyche/message.py`
- Existing event constants in `src/tyche/events.py`
- C++ and Rust bindings exist but are not in scope for this milestone
- Previous "Trading Modules" milestone plan was not executed; direction pivoted to persistence module
- All previous tests were deleted; test infrastructure needs rebuilding

## Notes

- Persistence module will live in `src/tyche/persistence/` (new package)
- ClickHouse is primary target database; SQLite is dev/test fallback
- Module subscribes to engine message queue events, not a separate data stream
- Need to handle events, market data, order/position snapshots
