# Potential Issues and Risks

## Technical Debt

### Code Duplication
- **Triplicated module implementation**: Same ZMQ lifecycle logic exists in Python (`module.py`), C++ (`cpp/module.cpp`), and Rust (`rust/src/module.rs`). All three handle registration, socket setup, heartbeat, and event dispatch. Changes to the wire protocol or socket architecture require updates in all three.
- **Message serialization**: Python uses `msgpack` with custom Decimal encoder; C++ uses `msgpack.hpp` with manual `pack_any`/`unpack_object`; Rust uses `serde` + `rmp-serde`. The formats are intended to match but have no shared schema or compatibility tests.
- **Types definitions**: `types.py`, `cpp/types.h`, and `rust/src/types.rs` all define equivalent enums and structs independently.

### Incomplete Features
- **`engine_main.py` does not exist** — referenced in README as entry point but file is missing from repo (only `engine.py` exists)
- **TUI dashboard** (`tui/`) referenced in README but directory may be incomplete
- **Module directory** (`src/modules/`) only contains `__init__.py` — trading domain modules (gateway, OMS, risk, etc.) are documented in README but not present in source tree
- **`src/rust_module/example/`** exists but no other Rust modules

### Design Inconsistencies
- C++ `InterfacePattern` enum only defines `ON` and `SEND` (missing `HANDLE` and `REQUEST` that Python has)
- Rust `Payload` type is `serde_json::Value` while Python and C++ use dict/map of `Any`/`std::any`
- Rust module uses `mpsc` channels for thread shutdown; Python uses `threading.Event()`; C++ uses atomic bool with sleep loops

## Security Concerns

### Serialization
- **MessagePack deserialization** does not validate message structure beyond type checking. Malformed messages could cause unexpected behavior.
- **No message size limits** on incoming ZMQ frames — could be exploited for memory exhaustion.

### Network Exposure
- Engine binds to `tcp://*` by default (all interfaces) — no localhost-only mode
- No authentication on registration socket — any process that can reach the port can register
- No TLS/encryption on ZMQ sockets — plaintext over network
- Admin endpoint exposes internal state without authentication

### CTP Integration
- CTP gateway code (in `research/openctp/`) includes platform-specific headers and binaries
- Third-party CTP API headers in repo may have licensing implications

## Performance Risks

### Lock Contention
- `TycheEngine._lock` is held during registration, admin queries, and event counting — potential bottleneck under high registration churn
- `TopicQueue` uses `threading.Lock()` on every put/get — fine-grained but could become hot
- `TycheModule._handlers_lock` acquired on every dispatch

### Memory Pressure
- Topic queues have no TTL-based expiration (only subscriber-based GC after 60s idle)
- Under burst load, queues can grow unbounded if egress worker cannot keep up
- `TrackedQueue` with `maxsize=10000` silently drops on full (no alerting)

### GIL Limitations
- Python engine uses threads but is bound by GIL — CPU-intensive work in handlers blocks the event loop
- Multiple modules are separate processes (good), but engine itself is single-process multi-threaded

## Error Handling Gaps

### Silent Failures
- Handler exceptions in `_dispatch()` are logged but not propagated — events are silently dropped on handler failure
- C++ `_dispatch()` swallows **all** exceptions (not just handler exceptions)
- Rust module does not handle ZMQ `EINTR` gracefully in event loop
- `HeartbeatManager.tick_all()` returns expired IDs but caller must act on them

### Race Conditions
- `_enqueue_from_xsub()` fast path accesses `_topic_queues` without lock (relies on dict atomicity in CPython, but not guaranteed)
- `_event_egress_worker()` copies queue list under lock then accesses queues without lock
- Module stop sequence: threads joined with 2s timeout, sockets may still have pending messages

## Testing Gaps

- No fuzz testing for message deserialization
- No chaos testing for network partitions or ZMQ context termination
- No load/stress tests in CI
- C++ and Rust modules have minimal test coverage
- No compatibility tests between Python/C++/Rust serialization formats

## Dependency Risks

| Dependency | Risk |
|------------|------|
| `pyzmq` | C extension — version lock to >=25.0.0 for compatibility |
| `msgpack` | C extension — version lock to >=1.0.5 |
| `clickhouse-connect` | Optional but critical for production persistence |
| `openctp-ctp` | Platform-specific (Windows/Linux only), not on PyPI for all platforms |
| `zmq` (Rust) | Bindings to libzmq — build complexity on Windows |
| Third-party submodules | `libzmq`, `cppzmq`, `msgpack-c`, `pybind11` as git submodules — may drift from upstream |

## Documentation Gaps

- `docs/design/` has v1 and v2 specs but no clear "current" version indicator
- `docs/plan/` has multiple plans for completed work — no archive of old versions
- `docs/impl/` logs exist but may not cover all recent changes
- No ADR directory visible (mentioned in `CLAUDE.md` but no `docs/adr/` found)
