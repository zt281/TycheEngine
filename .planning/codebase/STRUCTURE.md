# Codebase Structure

**Analysis Date:** 2026-05-14

## Directory Layout

```
D:/dev/TycheEngine/
├── src/
│   ├── tyche/              # Core framework (Python)
│   │   ├── cpp/            # C++ module bindings
│   │   └── rust/           # Rust module crate
│   └── modules/            # Application/trading modules (Python)
├── tests/                  # Test directory (currently empty)
├── docs/
│   ├── design/             # Design specifications (versioned)
│   ├── plan/               # Implementation plans (versioned)
│   ├── review/             # Plan review logs
│   └── impl/               # Implementation logs
├── tui/                    # Terminal UI dashboard (TypeScript/Bun)
│   └── src/                # TUI source components
├── research/               # Third-party research code (vendored)
│   └── binance-connector-python/
├── third_party/            # Vendored dependencies
│   └── pybind11/           # Python-C++ binding library
├── docker/                 # Docker compose files
├── ctp_flow/               # CTP (Chinese futures) flow files
├── build/                  # Build artifacts (C++ binaries)
├── .claude/                # Agent configuration and skills
│   ├── agents/             # Agent role definitions
│   ├── memory/             # Shared agent memory
│   └── skills/             # Skill definitions
├── .planning/              # Planning artifacts
│   └── codebase/           # Codebase analysis documents
├── .cache/                 # clangd index cache
├── Cargo.toml              # Rust workspace root
├── pyproject.toml          # Python project config
├── compile_commands.json   # clangd compilation database
├── README.md               # Project documentation
└── CLAUDE.md               # Agent cooperation guide
```

## Directory Purposes

**`src/tyche/` — Core Framework:**
- Purpose: The Tyche Engine distributed event framework
- Contains: Engine broker, module base classes, types, serialization, heartbeat
- Key files:
  - `src/tyche/engine.py` — Central broker (`TycheEngine` class)
  - `src/tyche/module.py` — Module base class (`TycheModule`)
  - `src/tyche/module_base.py` — Protocol definition (`ModuleBase`)
  - `src/tyche/types.py` — Core types (`Endpoint`, `Interface`, `MessageType`, etc.)
  - `src/tyche/message.py` — MessagePack serialization (`Message`, `Envelope`)
  - `src/tyche/heartbeat.py` — Paranoid Pirate heartbeat (`HeartbeatManager`)
  - `src/tyche/events.py` — Event name constants (QUOTE, TRADE, ORDER_SUBMIT, etc.)
  - `src/tyche/__init__.py` — Public API exports

**`src/tyche/cpp/` — C++ Language Bindings:**
- Purpose: C++ modules can connect to TycheEngine
- Contains: Header-only types, PIMPL-based module implementation
- Key files:
  - `src/tyche/cpp/types.h` — C++ mirrors of Python types (enums, structs, `ModuleId::generate()`)
  - `src/tyche/cpp/module.h` — `tyche::TycheModule` class declaration
  - `src/tyche/cpp/module.cpp` — Full ZMQ implementation with msgpack-cxx serialization

**`src/tyche/rust/` — Rust Language Bindings:**
- Purpose: Rust modules can connect to TycheEngine
- Contains: Rust crate with types, serialization, and module base
- Key files:
  - `src/tyche/rust/Cargo.toml` — Crate manifest (depends on zmq, serde, rmp-serde, rand)
  - `src/tyche/rust/src/lib.rs` — Crate root, re-exports
  - `src/tyche/rust/src/types.rs` — Rust types (`Endpoint`, `Message`, `Interface`, enums)
  - `src/tyche/rust/src/message.rs` — MessagePack serialization helpers
  - `src/tyche/rust/src/module.rs` — `TycheModuleBase` with dispatcher closure pattern

**`src/modules/` — Application Modules:**
- Purpose: Domain-specific trading modules built on the core framework
- Contains: Currently only `__init__.py` (framework placeholder)
- Expected future contents: gateway, OMS, risk, portfolio, strategy, persistence, store, clock

**`tests/` — Test Suite:**
- Purpose: pytest-based test suite
- Contains: Currently empty directory (tests were referenced in impl logs but files not present)
- Expected structure per CLAUDE.md:
  - `tests/unit/` — Unit tests (≥80% coverage target)
  - `tests/integration/` — Integration tests (full stack minus external venues)
  - `tests/perf/` — Performance tests (p99 latency < 10μs target)
  - `tests/property/` — Property-based tests (hypothesis, serialization round-trips)

**`docs/` — Project Documentation:**
- Purpose: Versioned design specs, plans, reviews, and implementation logs
- Key files:
  - `docs/design/tyche_engine_design_v1.md` — Initial design (5 ad-hoc interface patterns)
  - `docs/design/tyche_engine_design_v2.md` — Simplified 3-category model
  - `docs/design/unified_queue_design_v1.md` — v3 unified queue design (current)
  - `docs/plan/tyche_engine_plan_v1.md`, `plan_v2.md` — Implementation plans
  - `docs/plan/unified_queue_plan_v1.md` — Unified queue implementation plan
  - `docs/impl/tyche_engine_implement_v2.md` — Process separation implementation log

**`tui/` — Terminal UI Dashboard:**
- Purpose: Real-time monitoring and process supervision
- Contains: TypeScript/Bun application using OpenTUI and ZeroMQ
- Key files:
  - `tui/src/app.ts` — Main application, render loop, keyboard handling
  - `tui/src/connection.ts` — ZeroMQ connection manager (Subscriber, Request sockets)
  - `tui/src/state.ts` — Application state manager, admin polling
  - `tui/src/types.ts` — TypeScript type definitions
  - `tui/src/process-manager.ts` — Process lifecycle management
  - `tui/src/components/` — UI components (header, module-panel, queue-panel, event-log, stats-bar, footer, process-panel)

**`research/` — Vendored Research Code:**
- Purpose: Third-party libraries for reference/study
- Contains: `binance-connector-python/` (full Binance API client library)
- Note: Not part of the core project; do not modify

**`third_party/` — Vendored Dependencies:**
- Purpose: Build dependencies not available via package manager
- Contains: `pybind11/` — Python-C++ binding library

## Key File Locations

**Entry Points:**
- `src/tyche/engine.py` — `TycheEngine.run()` / `start_nonblocking()` — Engine process entry
- `src/tyche/module.py` — `TycheModule.run()` / `start()` — Module process entry
- `tui/src/app.ts` — `runApp(options)` — TUI dashboard entry

**Configuration:**
- `pyproject.toml` — Python project: dependencies, pytest config, mypy, ruff, coverage, hatch build
- `Cargo.toml` — Rust workspace: members `src/tyche/rust`, `src/rust_module/example`
- `src/tyche/rust/Cargo.toml` — Rust crate dependencies
- `compile_commands.json` — clangd compilation database for C++ intellisense

**Core Logic:**
- `src/tyche/engine.py` — Broker: registration, event proxy, heartbeat, job routing, admin
- `src/tyche/module.py` — Module: registration, event pub/sub, heartbeat, job request/response
- `src/tyche/message.py` — MessagePack serialization with Decimal support
- `src/tyche/heartbeat.py` — Paranoid Pirate heartbeat implementation
- `src/tyche/types.py` — All core dataclasses and enums

**Testing:**
- `tests/` — Empty; expected per CLAUDE.md structure (unit/, integration/, perf/, property/)

## Naming Conventions

**Files:**
- Python modules: `snake_case.py` (e.g., `engine.py`, `module_base.py`)
- C++ headers: `PascalCase.h` (e.g., `module.h`, `types.h`)
- C++ sources: `snake_case.cpp` (e.g., `module.cpp`)
- Rust modules: `snake_case.rs` (e.g., `types.rs`, `message.rs`)
- TypeScript: `kebab-case.ts` (e.g., `event-log.ts`, `process-manager.ts`)

**Directories:**
- Python packages: `snake_case` (e.g., `tyche/`, `modules/`)
- Rust crate: matches Cargo package name (`rust/`)
- Docs: `{spec}_{kind}_v{N}.md` (e.g., `tyche_engine_design_v2.md`)

**Classes:**
- Python: `PascalCase` (e.g., `TycheEngine`, `TycheModule`, `HeartbeatManager`)
- C++: `PascalCase` in `tyche` namespace (e.g., `tyche::TycheModule`)
- Rust: `PascalCase` (e.g., `TycheModuleBase`, `ReceivedEvent`)

**Methods/Functions:**
- Python: `snake_case` with leading underscore for private (e.g., `_event_receiver()`, `_dispatch()`)
- C++: `snake_case` with leading underscore for private (e.g., `_start_workers()`, `_dispatch()`)
- Rust: `snake_case` (e.g., `start_with_dispatcher()`, `send_event()`)

**Module IDs:**
- Format: `{deity}{6-char hex}` (e.g., `zeus3f7a9c`, `apollo8b2d4e`)
- Generated by: `ModuleId.generate()` in Python/C++/Rust

## Where to Add New Code

**New Core Framework Feature:**
- Primary code: `src/tyche/{feature}.py`
- Types: `src/tyche/types.py` (add enums/dataclasses)
- Tests: `tests/unit/test_{feature}.py`
- If C++ parity needed: `src/tyche/cpp/{feature}.h`, `src/tyche/cpp/{feature}.cpp`
- If Rust parity needed: `src/tyche/rust/src/{feature}.rs`

**New Trading Module:**
- Implementation: `src/modules/trading/{module_name}/` (e.g., `src/modules/trading/gateway/`)
- Module class: subclass `TycheModule`, implement `on_*`/`send_*` handlers
- Tests: `tests/unit/trading/test_{module_name}.py`

**New Event Type:**
- Constant: `src/tyche/events.py` (add UPPER_CASE constant)
- If trading-specific: `src/modules/trading/events.py`

**New C++ Module:**
- Header: `src/tyche/cpp/{module}.h`
- Implementation: `src/tyche/cpp/{module}.cpp`
- Build: Update `compile_commands.json` or CMakeLists if present

**New Rust Module:**
- Source: `src/tyche/rust/src/{module}.rs`
- Export: Add `pub mod {module};` to `src/tyche/rust/src/lib.rs`

**New TUI Component:**
- Component: `tui/src/components/{component-name}.ts`
- Export types and render functions following existing component pattern
- Wire into `tui/src/app.ts` layout and keyboard handlers

## Special Directories

**`.cache/clangd/index/`:**
- Purpose: clangd language server index cache
- Generated: Yes (by clangd)
- Committed: No (has `.gitignore`)

**`build/Release/`:**
- Purpose: C++ build artifacts
- Generated: Yes (by compiler)
- Committed: No
- Contains: `cpp_example_standalone.exe` (example C++ module binary)

**`ctp_flow/`:**
- Purpose: CTP (Chinese futures trading API) connection flow files
- Generated: Yes (at runtime by CTP library)
- Committed: Possibly (contains `.con` connection state files)

**`research/`:**
- Purpose: Vendored third-party libraries for study
- Generated: No (cloned)
- Committed: Yes
- Note: Do not modify; not part of core project build

**`third_party/pybind11/`:**
- Purpose: Python-C++ binding headers
- Generated: No (submodule or copied)
- Committed: Yes

---

*Structure analysis: 2026-05-14*
