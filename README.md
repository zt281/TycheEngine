<div align="center">
  <img src="docs/resources/tycheengine_logo_v5_hd.png" alt="TycheEngine" width="340" />

  <h3>Institutional-grade, multi-asset algorithmic trading platform</h3>
  <p>Python orchestration · Rust hot path · ZeroMQ IPC</p>

  <br/>

  [![CI](https://github.com/zt281/TycheEngine/actions/workflows/ci.yml/badge.svg)](https://github.com/zt281/TycheEngine/actions/workflows/ci.yml)
  [![Release](https://github.com/zt281/TycheEngine/actions/workflows/release.yml/badge.svg)](https://github.com/zt281/TycheEngine/actions/workflows/release.yml)
  [![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)

</div>

---

## Overview

TycheEngine is a high-frequency trading platform designed for multi-asset institutional use. It runs every trading component as an **independent OS process pinned to a dedicated CPU core**, communicating over a split control/data ZeroMQ bus. The hot path is implemented in Rust with zero-copy `#[repr(C)]` types; the orchestration layer is Python with PyO3 bindings, keeping strategy and lifecycle code ergonomic without sacrificing data-path performance.

### Key Design Goals

| Goal | Mechanism |
|------|-----------|
| Microsecond-latency data path | Rust `#[repr(C)]` types, MessagePack serialisation, per-core affinity |
| Fault isolation | Each module is an independent OS process — one crash cannot cascade |
| Deterministic replay | `Clock` abstraction; `SimClock` drives backtesting without changing strategy code |
| Future shared-memory migration | Bus XPUB/XSUB is a drop-in replacement target for SPSC ring buffers |
| Multi-asset coverage | Equities, equity options, futures, future options, crypto spot/perp/future, FX, bonds |

---

## Architecture

TycheEngine uses a **split control/data plane**. Two hub processes coordinate everything; trading modules never communicate directly with each other.

```
┌──────────────────────────────────────────────────────────────┐
│                        TYCHE ENGINE                          │
│                                                              │
│   ┌──────────────┐            ┌──────────────────────────┐   │
│   │    NEXUS     │            │           BUS            │   │
│   │ Control Hub  │            │        Data Hub          │   │
│   │              │            │                          │   │
│   │ ROUTER/DEALER│            │       XPUB / XSUB        │   │
│   │  tcp:5555    │            │  xsub: tcp:5556  (← pub) │   │
│   │  CPU core 0  │            │  xpub: tcp:5557  (→ sub) │   │
│   │              │            │       CPU core 1         │   │
│   └──────┬───────┘            └─────────┬────────────────┘   │
│          │ lifecycle / commands          │ streaming data    │
│    ──────┼──────────────────────────────┼─────               │
│          │                              │                    │
│   ┌──────┴───────┐            ┌─────────┴──────┐             │
│   │   Module A   │            │    Module B    │             │
│   │  (e.g. MDS)  │            │  (e.g. OMS)    │             │
│   │  CPU core 2  │            │  CPU core 3    │             │
│   └──────────────┘            └────────────────┘             │
└──────────────────────────────────────────────────────────────┘
```

**Nexus** handles registration, heartbeating, lifecycle commands (START / STOP / RECONFIGURE / STATUS), and ordered shutdown. It is authoritative over which modules are alive.

**Bus** is a pure XPUB/XSUB proxy. Publishers connect to port 5556; subscribers connect to port 5557. It has no knowledge of module state — it simply fans data out by topic prefix.

Every module on startup pins itself to its configured CPU core, registers with Nexus, then enters a `zmq.Poller` loop over its Nexus DEALER socket, Bus SUB socket, and an internal Rust FFI PAIR socket.

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Hot-path types & serialisation | Rust 1.78+ (edition 2021), `#[repr(C)]` structs |
| Python ↔ Rust bindings | PyO3 0.22.x, maturin 1.5+ |
| Serialisation | MessagePack via `rmp-serde` 1.3.x |
| IPC | ZeroMQ (pyzmq 25+, libzmq 4.3.4+) |
| Python runtime | Python 3.11+ |
| CPU affinity | `core_affinity` 0.8.x (Rust), `os.sched_setaffinity` / `SetThreadAffinityMask` (Python) |
| Config | TOML (`tomllib` stdlib) |

---

## Getting Started

### Prerequisites

- Rust stable ≥ 1.78 — [rustup.rs](https://rustup.rs)
- Python 3.11+
- maturin ≥ 1.5 — `pip install "maturin>=1.5,<2.0"`

### Build

```bash
# Build the Rust crate and install the Python package in editable mode
maturin develop --release
```

### Run Tests

```bash
# Rust unit tests
cargo test --manifest-path tyche-core/Cargo.toml

# Python unit + integration tests
pytest tests/ -v
```

### Lint

```bash
cargo clippy --manifest-path tyche-core/Cargo.toml -- -D warnings
ruff check tyche/ tests/
```

> **Windows note:** Use `python` instead of `python3`. Development is supported on Windows 11; the production target is Linux.

---

## Project Layout

```
TycheEngine/
├── tyche/                     # Python package
│   ├── core/
│   │   ├── module.py          # Module abstract base class (run loop, typed dispatch)
│   │   ├── nexus.py           # Nexus process — ROUTER/DEALER lifecycle broker
│   │   ├── bus.py             # Bus process — XPUB/XSUB data proxy
│   │   ├── clock.py           # Clock protocol, LiveClock, SimClock
│   │   └── config.py          # TOML config loaders
│   ├── model/
│   │   ├── instrument.py      # Instrument, InstrumentId, AssetClass, Venue
│   │   ├── types.py           # Re-exports: Quote, Trade, Tick, Bar, Order, …
│   │   └── enums.py           # Re-exports: Side, OrderType, TIF, BarInterval, …
│   └── utils/
│       ├── topics.py          # Topic builder / validator / symbol normalisation
│       ├── serialization.py   # MessagePack helpers
│       └── logging.py         # Structured JSON logger
│
├── tyche-core/                # Rust crate — all hot-path types + PyO3 bindings
│   └── src/
│       ├── types.rs           # #[repr(C)] Tick, Quote, Trade, Bar, Order, …
│       ├── enums.rs           # BarInterval, ModelKind, Side, OrderType, TIF
│       ├── instrument.rs      # InstrumentId 64-bit bit-packed struct
│       ├── serialization.rs   # MessagePack encode/decode (rmp-serde)
│       ├── ffi_bridge.rs      # Rust → Python zero-copy channel (AtomicPtr per topic)
│       └── python.rs          # PyO3 module registration
│
├── config/
│   ├── engine.toml            # Global: Nexus/Bus addresses, CPU core map
│   └── modules/               # Per-module TOML configs
│
├── tests/
│   ├── unit/                  # Fast, no-network tests
│   └── integration/           # Bus pubsub, Nexus lifecycle, end-to-end module
│
├── docs/
│   ├── design/                # Versioned architecture specs
│   ├── plan/                  # Versioned implementation plans
│   ├── review/                # Spec and plan review logs
│   └── impl/                  # Implementation logs per dev cycle
│
├── Cargo.toml                 # Rust workspace root
├── pyproject.toml             # maturin / Python package config
└── Makefile                   # build · test · lint · clean
```

---

## Topic Naming

All data flows over the Bus using structured topic strings:

```
<ASSET_CLASS>.<VENUE>.<SYMBOL>.<DATA_TYPE>[.<INTERVAL>]
```

Examples:

```
CRYPTO_SPOT.BINANCE.BTCUSDT.QUOTE
EQUITY.NYSE.AAPL.BAR.M5
EQUITY_OPTION.CBOE.AAPL_150C_20250117.QUOTE
FUTURE.CME.ES_Z25.TICK
INTERNAL.OMS.ORDER_EVENT
INTERNAL.RISK.RISK_UPDATE
```

ZeroMQ performs **prefix matching** — subscribe to `EQUITY.NYSE` to receive all data for all NYSE equities. Wildcards are not supported; filter in the handler if needed.

---

## Roadmap

TycheEngine is built incrementally. Each sub-project is a self-contained module that plugs into the core engine.

| Sub-project | Description | Status |
|-------------|-------------|--------|
| **Core Engine** | Nexus, Bus, Module base, Rust types, FFI bridge | 🔨 In progress |
| Market Data Service | Feed handlers, normalisation, sequencing | Planned |
| Order Management System | Order lifecycle, position tracking, fills | Planned |
| Risk Engine | Greeks, DV01, pre/post-trade checks | Planned |
| Strategy Framework | Signal generation, portfolio allocation | Planned |
| Backtesting Engine | SimClock replay, historical data pipeline | Planned |
| Exchange Connectors | Live broker/exchange APIs | Planned |

---

## License

TycheEngine is released under the [GNU General Public License v3.0](LICENSE).
