# Technology Stack

**Analysis Date:** 2026-05-14

## Languages

**Primary:**
- **Python 3.9+** - Core engine, module framework, event routing, heartbeat management
  - Runtime detected: `3.9.12 (MSC v.1916 64 bit AMD64)`
  - Source: `src/tyche/*.py` (~2,100 LOC)
- **Rust 1.88** - High-performance module implementation, serialization
  - Edition: 2021
  - Source: `src/tyche/rust/src/*.rs` (~1,000 LOC)
- **C++17** - Native module bindings, pybind11 integration
  - Compiler: `clang++ -std=c++17`
  - Source: `src/tyche/cpp/*` (~950 LOC)

**Secondary:**
- **TypeScript 5.x** - Terminal UI (TycheTUI)
  - Source: `tui/src/*.ts` (~2,500 LOC)

## Runtime

**Python Environment:**
- Requires Python >= 3.9
- Package manager: `pip` (hatchling build backend)
- Lockfile: `Cargo.lock` present (Rust dependencies)

**Rust Environment:**
- Toolchain: `rustc 1.88.0`, `cargo 1.88.0`
- Workspace resolver: 2

**JavaScript Environment:**
- Runtime: Bun 1.3.11
- Node.js: v24.1.0 (available as fallback)

## Build System

**Python:**
- Build backend: `hatchling` (defined in `pyproject.toml`)
- Wheel targets: `src/tyche`, `src/modules`

**Rust:**
- Cargo workspace with 2 members:
  - `src/tyche/rust` - Core tyche crate
  - `src/rust_module/example` - Example module (not yet populated)

**C++:**
- No primary build system (header-only + compiled via pybind11/CMake)
- `compile_commands.json` present for clangd/IDE support
- Third-party C++ libraries built via CMake: `cppzmq`, `libzmq`, `msgpack-c`

**TypeScript:**
- Bundler: Bun (`bun build --target=bun`)
- Config: `tui/tsconfig.json` (strict mode, ESNext, bundler resolution)

## Frameworks

**Core Engine:**
- **ZeroMQ (pyzmq >= 25.0.0)** - All inter-process communication
  - Socket types used: ROUTER, DEALER, PUB, SUB, XPUB, XSUB, REQ, REP
  - Pattern: Paranoid Pirate (reliable heartbeating)
- **MessagePack (msgpack >= 1.0.5)** - Wire serialization format
  - Custom `Decimal` encoder/decoder in `src/tyche/message.py`

**Rust Crate:**
- **zmq 0.10** - Rust ZeroMQ bindings
- **serde + rmp-serde 1.3** - MessagePack serialization
- **serde_json 1.0** - JSON payload handling
- **rand 0.8** - Module ID generation

**C++ Module:**
- **cppzmq** - C++ ZeroMQ header-only wrapper (git submodule)
- **msgpack-c** - C++ MessagePack implementation (git submodule)
- **pybind11** - Python/C++ interop (git submodule)

**TUI:**
- **@opentui/core ^0.1.103** - Terminal UI framework
- **zeromq ^6.5.0** - Node.js ZeroMQ bindings
- **@msgpack/msgpack ^3.1.3** - MessagePack for JavaScript

## Key Dependencies

**Critical Runtime:**
| Package | Version | Purpose |
|---------|---------|---------|
| `pyzmq` | >= 25.0.0 | ZeroMQ Python bindings - all IPC |
| `msgpack` | >= 1.0.5 | Binary serialization protocol |
| `zmq` (Rust) | 0.10 | Rust ZeroMQ bindings |
| `rmp-serde` | 1.3 | Rust MessagePack via serde |

**Optional Trading:**
| Package | Version | Purpose |
|---------|---------|---------|
| `openctp-ctp` | >= 6.7.0 | CTP futures trading API (optional extras: `ctp`) |
| `clickhouse-connect` | >= 0.7.0 | ClickHouse persistence (optional extras: `persistence`) |

**Development:**
| Package | Version | Purpose |
|---------|---------|---------|
| `pytest` | >= 7.4.0 | Test runner |
| `pytest-asyncio` | >= 0.21.0 | Async test support |
| `pytest-timeout` | >= 2.2.0 | Test timeout enforcement |
| `pytest-cov` | >= 4.1.0 | Coverage reporting |
| `mypy` | >= 1.5.0 | Static type checking |
| `ruff` | >= 0.0.280 | Linting and formatting |

## Configuration

**Python Tooling (pyproject.toml):**
- `pytest`: testpaths=`tests`, timeout=30s, asyncio_mode=auto
- `mypy`: python_version=3.9, disallow_untyped_defs=true
- `ruff`: line-length=100, select=[E,F,I,W], ignore=[E501]
- `coverage`: source=["src/tyche","src/modules"], exclude `if __name__ == "__main__"`

**Git Hooks:**
- Pre-push hook at `.githooks/pre-push` runs `ruff check src tests` and `mypy src`

## Dependency Graph Highlights

```
pyproject.toml
├── pyzmq >= 25.0.0          [core IPC]
├── msgpack >= 1.0.5         [serialization]
├── openctp-ctp >= 6.7.0     [optional: CTP trading]
├── clickhouse-connect >=0.7.0 [optional: persistence]
└── dev: pytest, mypy, ruff  [quality]

Cargo.toml (workspace)
└── src/tyche/rust/Cargo.toml
    ├── zmq 0.10
    ├── serde 1.0
    ├── rmp-serde 1.3
    ├── serde_json 1.0
    └── rand 0.8

tui/package.json
├── @opentui/core ^0.1.103   [terminal UI]
├── zeromq ^6.5.0            [Node ZMQ]
├── @msgpack/msgpack ^3.1.3  [JS msgpack]
└── typescript ^5             [peer dep]
```

## Platform Requirements

**Development:**
- Python 3.9+
- Rust toolchain (cargo, rustc)
- Bun runtime (for TUI)
- ZeroMQ C library (libzmq) - vendored as `third_party/libzmq`
- CMake (for building C++ dependencies)

**Production:**
- Target: Linux/Windows trading workstation
- Deployment: Python wheel + Rust crate + C++ extension module
- Docker: ClickHouse compose file at `docker/clickhouse-compose.yml`

## Third-Party Submodules

| Submodule | Path | Purpose |
|-----------|------|---------|
| libzmq | `third_party/libzmq` | ZeroMQ C core library |
| cppzmq | `third_party/cppzmq` | C++ header-only ZMQ wrapper |
| msgpack-c | `third_party/msgpack-c` | C++ MessagePack (cpp_master branch) |
| pybind11 | `third_party/pybind11` | Python/C++ binding generator |
| TycheTUI | `tui` | Terminal UI (external repo) |

---

*Stack analysis: 2026-05-14*
