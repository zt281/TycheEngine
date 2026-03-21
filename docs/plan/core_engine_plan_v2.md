# Core Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the TycheEngine core engine — the shared Rust type library, PyO3 bindings, ZeroMQ Bus/Nexus hub processes, and Python Module base class that all subsequent sub-projects depend on.

**Architecture:** A Rust crate (`tyche-core`) defines all hot-path data types as `#[repr(C)]` structs and `#[repr(u8)]` enums, exposed to Python via PyO3 bindings built with maturin. Two Python hub processes (Nexus: ROUTER/DEALER lifecycle broker; Bus: XPUB/XSUB data proxy) run as independent OS processes pinned to CPU cores 0 and 1 respectively. All trading modules inherit from a Python `Module` base class that connects to both hubs, deserializes inbound MessagePack payloads into typed Rust objects via PyO3, and dispatches them to typed handler methods.

**Tech Stack:** Rust 1.78+ (edition 2021), PyO3 0.22.x, maturin 1.5+, rmp-serde 1.3.x, Python 3.11+, pyzmq 25+, msgpack 1.0+, core_affinity 0.8.x

**Spec:** `docs/design/core_engine_design_v3.md`

**Platform note:** Development on Windows 11; production target is Linux. Use `python` or `py` on Windows where `python3` is shown.

**ZMQ framing note:** The plan uses `DEALER/ROUTER` sockets throughout (not `REQ/REP`). With pure DEALER sockets, frames are sent as-is with no empty delimiter. The ROUTER prepends the sender identity on receive. Pattern: DEALER sends `[f1, f2, ...]` → ROUTER receives `[identity, f1, f2, ...]`. ROUTER sends `[identity, r1, r2, ...]` → DEALER receives `[r1, r2, ...]`.

---

## File Map

### Rust crate — `tyche-core/`
| File | Responsibility |
|------|---------------|
| `tyche-core/Cargo.toml` | Crate manifest; deps: pyo3 0.22, rmp-serde 1.3, serde 1, core_affinity 0.8 |
| `tyche-core/src/lib.rs` | Crate root; declares all modules |
| `tyche-core/src/enums.rs` | `BarInterval`, `ModelKind`, `Side`, `OrderType`, `TIF`, `AssetClass` |
| `tyche-core/src/instrument.rs` | `InstrumentId` 64-bit packed struct + encode/decode |
| `tyche-core/src/types.rs` | All `#[repr(C)]` data types: `Tick`, `Quote`, `Trade`, `Bar`, `Order`, `OrderEvent`, `Ack`, `Position`, `Risk`, `Model`, `Timestamp` |
| `tyche-core/src/clock.rs` | `Clock` trait, `LiveClock`, `SimClock` |
| `tyche-core/src/serialization.rs` | MessagePack encode/decode via rmp-serde |
| `tyche-core/src/ffi_bridge.rs` | Global per-(service,topic) `AtomicPtr<Vec<u8>>` slot registry; module-level `init_ffi_bridge`, `write_pending`, `take_pending`; signal constants |
| `tyche-core/src/python.rs` | PyO3 module; exposes all types, module-level `init_ffi_bridge`, `take_pending`, `serialize_*`, `deserialize_*` |

### Build system
| File | Responsibility |
|------|---------------|
| `Cargo.toml` | Workspace root; pins workspace-level dependency versions |
| `pyproject.toml` | maturin build config; Python package metadata; `python-source` omitted (defaults to `.`) |
| `Makefile` | `build`, `test`, `lint`, `clean` targets |

### Python package — `tyche/`
| File | Responsibility |
|------|---------------|
| `tyche/__init__.py` | Package root |
| `tyche/model/instrument.py` | `Instrument` Python dataclass + `AssetClass`, `Venue` helpers |
| `tyche/model/types.py` | Re-exports all `tyche_core` data types |
| `tyche/model/enums.py` | Re-exports all `tyche_core` enums |
| `tyche/utils/topics.py` | Topic builder, parser, validator; symbol normalisation; `suffix_to_bar_interval` |
| `tyche/utils/serialization.py` | MessagePack helpers wrapping `tyche_core.serialize/deserialize` |
| `tyche/utils/logging.py` | Structured JSON logger |
| `tyche/core/clock.py` | `LiveClock`, `SimClock` Python wrappers |
| `tyche/core/config.py` | `NexusConfig`, `BusConfig`, `ModuleConfig`; TOML loading |
| `tyche/core/bus.py` | `Bus` process: XPUB/XSUB proxy with CPU pinning |
| `tyche/core/nexus.py` | `Nexus` process: ROUTER/DEALER Majordomo broker |
| `tyche/core/module.py` | `Module` abstract base class with run loop, typed dispatch, PAIR socket |

### Config
| File | Responsibility |
|------|---------------|
| `config/engine.toml` | Global: Nexus/Bus addresses, CPU core map |
| `config/modules/nexus.toml` | Nexus-specific: heartbeat interval, retry policy |
| `config/modules/bus.toml` | Bus-specific: HWM, addresses |
| `config/modules/example_strategy.toml` | Example module config |

### Tests
| File | Responsibility |
|------|---------------|
| `tests/unit/test_instrument.py` | InstrumentId encode/decode, field extraction |
| `tests/unit/test_types.py` | Construction and field access for all data types |
| `tests/unit/test_topics.py` | Topic building, parsing, validation, normalisation, interval suffix |
| `tests/unit/test_config.py` | TOML config loading and validation |
| `tests/unit/test_clock.py` | LiveClock monotonicity, SimClock advance |
| `tests/integration/test_bus_pubsub.py` | Bus process: publish/subscribe, topic prefix matching |
| `tests/integration/test_nexus_lifecycle.py` | Nexus: registration, READY_ACK, heartbeat, STOP command |
| `tests/integration/test_module_e2e.py` | Full end-to-end: module registers, subscribes, receives typed data |

---

## Task 1: Project Scaffold

**Files:**
- Create: `Cargo.toml`, `tyche-core/Cargo.toml`, `tyche-core/src/lib.rs`
- Create: `pyproject.toml`, `Makefile`
- Create: `config/engine.toml`, `config/modules/nexus.toml`, `config/modules/bus.toml`, `config/modules/example_strategy.toml`
- Create: all `__init__.py` and empty source stubs

- [ ] **Step 1: Create workspace Cargo.toml**

```toml
# Cargo.toml
[workspace]
members = ["tyche-core"]
resolver = "2"

[workspace.dependencies]
pyo3 = { version = "0.22", features = ["extension-module", "multiple-pymethods"] }
rmp-serde = "1.3"
serde = { version = "1", features = ["derive"] }
core_affinity = "0.8"
```

- [ ] **Step 2: Create tyche-core/Cargo.toml**

```toml
# tyche-core/Cargo.toml
[package]
name = "tyche-core"
version = "0.1.0"
edition = "2021"

[lib]
name = "tyche_core"
crate-type = ["cdylib", "rlib"]

[dependencies]
pyo3 = { workspace = true }
rmp-serde = { workspace = true }
serde = { workspace = true }
core_affinity = { workspace = true }
```

- [ ] **Step 3: Create tyche-core/src/lib.rs**

```rust
// tyche-core/src/lib.rs
pub mod clock;
pub mod enums;
pub mod ffi_bridge;
pub mod instrument;
pub mod serialization;
pub mod types;
mod python;

use pyo3::prelude::*;

#[pymodule]
fn tyche_core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    python::register(m)
}
```

- [ ] **Step 4: Create pyproject.toml**

```toml
# pyproject.toml
[build-system]
requires = ["maturin>=1.5,<2.0"]
build-backend = "maturin"

[project]
name = "tyche"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "pyzmq>=25.0",
    "msgpack>=1.0",
]

[tool.maturin]
module-name = "tyche_core"
manifest-path = "tyche-core/Cargo.toml"
```

Note: `python-source` is intentionally omitted (defaults to `.`). Maturin discovers Python packages by looking for directories with `__init__.py` in the project root — it will find `tyche/` and package it correctly. Test directories must NOT have `__init__.py` (see Step 7) or maturin would include them in the wheel.

- [ ] **Step 5: Create Makefile**

```makefile
# Makefile
.PHONY: build test lint clean

build:
	maturin develop --release

test: build
	cargo test --manifest-path tyche-core/Cargo.toml
	pytest tests/ -v

lint:
	cargo clippy --manifest-path tyche-core/Cargo.toml -- -D warnings
	ruff check tyche/ tests/

clean:
	cargo clean
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -name "*.pyc" -delete
```

- [ ] **Step 6: Create config files**

```toml
# config/engine.toml
[nexus]
address = "tcp://127.0.0.1:5555"
cpu_core = 0

[bus]
xsub_address = "tcp://127.0.0.1:5556"
xpub_address = "tcp://127.0.0.1:5557"
cpu_core = 1
sndhwm = 10000
```

```toml
# config/modules/nexus.toml
[policy]
heartbeat_interval_ms = 1000
missed_heartbeat_limit = 3
registration_timeout_ms = 500
registration_max_retries = 20
restart_policy = "alert-only"
```

```toml
# config/modules/bus.toml
[bus]
sndhwm = 10000
```

```toml
# config/modules/example_strategy.toml
[module]
service_name = "strategy.example"
cpu_core = 4
subscriptions = ["EQUITY.NYSE.AAPL.QUOTE", "EQUITY.NYSE.AAPL.BAR.M5"]
```

- [ ] **Step 7: Create all Python package skeleton files**

Create empty `__init__.py` in: `tyche/`, `tyche/core/`, `tyche/model/`, `tyche/utils/`

**Do NOT create `__init__.py` in `tests/`, `tests/unit/`, or `tests/integration/`.**
Pytest discovers test files without `__init__.py`; omitting them prevents maturin from
accidentally packaging the test directories into the wheel.

Create empty stub files (just `# TODO` comment):
`tyche/core/clock.py`, `tyche/core/config.py`, `tyche/core/bus.py`, `tyche/core/nexus.py`, `tyche/core/module.py`
`tyche/model/instrument.py`, `tyche/model/types.py`, `tyche/model/enums.py`
`tyche/utils/topics.py`, `tyche/utils/serialization.py`, `tyche/utils/logging.py`

- [ ] **Step 8: Verify workspace compiles (empty crate)**

Create minimal `tyche-core/src/python.rs`:
```rust
// tyche-core/src/python.rs
use pyo3::prelude::*;
pub fn register(_m: &Bound<'_, PyModule>) -> PyResult<()> { Ok(()) }
```

Create empty module stubs in each Rust file (`// TODO`).

Run: `cargo check --manifest-path tyche-core/Cargo.toml`
Expected: no errors

- [ ] **Step 9: Commit scaffold**

```bash
git add .
git commit -m "feat: project scaffold — workspace, pyproject.toml, config, package skeleton"
```

---

## Task 2: Rust Enums

**Files:**
- Modify: `tyche-core/src/enums.rs`

- [ ] **Step 1: Write failing Rust tests (no implementation yet)**

```rust
// tyche-core/src/enums.rs — ADD TESTS ONLY, no enum definitions yet
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bar_interval_topic_suffix_matches_variant() {
        assert_eq!(BarInterval::M5.topic_suffix(), "M5");
        assert_eq!(BarInterval::H4.topic_suffix(), "H4");
        assert_eq!(BarInterval::D1.topic_suffix(), "D1");
    }

    #[test]
    fn bar_interval_discriminants_are_stable() {
        assert_eq!(BarInterval::M1 as u8, 0);
        assert_eq!(BarInterval::W1 as u8, 8);
    }

    #[test]
    fn side_discriminants() {
        assert_eq!(Side::Buy as u8, 0);
        assert_eq!(Side::Sell as u8, 1);
    }

    #[test]
    fn model_kind_custom_is_255() {
        assert_eq!(ModelKind::Custom as u8, 255);
    }
}
```

- [ ] **Step 2: Run tests to confirm compile failure**

Run: `cargo test --manifest-path tyche-core/Cargo.toml enums`
Expected: FAIL — `BarInterval`, `Side`, `ModelKind` not defined

- [ ] **Step 3: Implement enums**

```rust
// tyche-core/src/enums.rs — ADD IMPLEMENTATION
use pyo3::prelude::*;
use serde::{Deserialize, Serialize};

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[pyclass(eq, eq_int)]
pub enum BarInterval {
    M1 = 0, M3 = 1, M5 = 2, M15 = 3, M30 = 4,
    H1 = 5, H4 = 6, D1 = 7, W1 = 8,
}

impl BarInterval {
    /// Pure Rust helper — used by `bar_interval_from_suffix` pyfunction and Rust internals.
    pub fn from_suffix(s: &str) -> Option<Self> {
        match s {
            "M1" => Some(Self::M1), "M3" => Some(Self::M3), "M5" => Some(Self::M5),
            "M15" => Some(Self::M15), "M30" => Some(Self::M30), "H1" => Some(Self::H1),
            "H4" => Some(Self::H4), "D1" => Some(Self::D1), "W1" => Some(Self::W1),
            _ => None,
        }
    }
}

/// Separate `#[pymethods]` block (requires `multiple-pymethods` PyO3 feature).
/// Exposes `interval.topic_suffix` as a Python read-only property.
#[pymethods]
impl BarInterval {
    #[getter]
    pub fn topic_suffix(&self) -> &'static str {
        match self {
            Self::M1 => "M1", Self::M3 => "M3", Self::M5 => "M5",
            Self::M15 => "M15", Self::M30 => "M30", Self::H1 => "H1",
            Self::H4 => "H4", Self::D1 => "D1", Self::W1 => "W1",
        }
    }
}

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[pyclass(eq, eq_int)]
pub enum ModelKind {
    VolSurface = 0, FairValue = 1, Signal = 2, RiskFactor = 3, Custom = 255,
}

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[pyclass(eq, eq_int)]
pub enum Side { Buy = 0, Sell = 1 }

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[pyclass(eq, eq_int)]
pub enum OrderType { Market = 0, Limit = 1, Stop = 2, StopLimit = 3 }

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[pyclass(eq, eq_int)]
pub enum TIF { GTC = 0, IOC = 1, FOK = 2, GTD = 3, Day = 4 }

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[pyclass(eq, eq_int)]
pub enum AssetClass {
    Equity = 0, EquityOption = 1, Future = 2, FutureOption = 3,
    CryptoSpot = 4, CryptoPerp = 5, CryptoFuture = 6, FxSpot = 7, Bond = 8,
}

// Keep the test block from Step 1 in place
```

- [ ] **Step 4: Run tests — confirm GREEN**

Run: `cargo test --manifest-path tyche-core/Cargo.toml enums`
Expected: 4 tests pass

- [ ] **Step 5: Commit**

```bash
git add tyche-core/src/enums.rs
git commit -m "feat(rust): add BarInterval, ModelKind, Side, OrderType, TIF, AssetClass enums"
```

---

## Task 3: Rust InstrumentId

**Files:**
- Modify: `tyche-core/src/instrument.rs`

- [ ] **Step 1: Write failing tests**

```rust
// tyche-core/src/instrument.rs — tests only
#[cfg(test)]
mod tests {
    use super::*;
    use crate::enums::AssetClass;

    #[test]
    fn encode_decode_roundtrip() {
        let id = InstrumentId::new(AssetClass::Equity, 1, 42, 0);
        assert_eq!(id.asset_class(), Ok(AssetClass::Equity));
        assert_eq!(id.venue(), 1);
        assert_eq!(id.symbol(), 42);
        assert_eq!(id.expiry_strike(), 0);
    }
    #[test]
    fn raw_value_is_deterministic() {
        let a = InstrumentId::new(AssetClass::CryptoSpot, 7, 100, 0);
        let b = InstrumentId::new(AssetClass::CryptoSpot, 7, 100, 0);
        assert_eq!(a.raw(), b.raw());
    }
    #[test]
    fn all_fields_max_values_fit() {
        let id = InstrumentId::new(AssetClass::Bond, 0xFFF, 0xFFFFFF, 0xFFFFFF);
        assert_eq!(id.venue(), 0xFFF);
        assert_eq!(id.symbol(), 0xFFFFFF);
        assert_eq!(id.expiry_strike(), 0xFFFFFF);
    }
    #[test]
    fn invalid_asset_class_bits_return_err() {
        // Manually craft an ID with asset_class bits = 15 (no enum variant)
        let raw: u64 = 0b1111u64 << 60;
        let id = InstrumentId::from_raw(raw);
        assert!(id.asset_class().is_err());
    }
}
```

Run: `cargo test --manifest-path tyche-core/Cargo.toml instrument`
Expected: FAIL

- [ ] **Step 2: Implement InstrumentId**

```rust
// tyche-core/src/instrument.rs
use crate::enums::AssetClass;
use serde::{Deserialize, Serialize};

/// 64-bit packed instrument identifier.
/// Bit layout: [63..60] AssetClass (4) | [59..48] Venue (12) | [47..24] Symbol (24) | [23..0] Expiry/Strike (24)
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct InstrumentId(u64);

impl InstrumentId {
    pub fn new(asset_class: AssetClass, venue: u16, symbol: u32, expiry_strike: u32) -> Self {
        let v = (asset_class as u64) << 60
            | ((venue as u64) & 0xFFF) << 48
            | ((symbol as u64) & 0xFFFFFF) << 24
            | ((expiry_strike as u64) & 0xFFFFFF);
        Self(v)
    }

    pub fn from_raw(raw: u64) -> Self { Self(raw) }
    pub fn raw(&self) -> u64 { self.0 }

    pub fn asset_class(&self) -> Result<AssetClass, u8> {
        let bits = (self.0 >> 60) as u8;
        match bits {
            0 => Ok(AssetClass::Equity),
            1 => Ok(AssetClass::EquityOption),
            2 => Ok(AssetClass::Future),
            3 => Ok(AssetClass::FutureOption),
            4 => Ok(AssetClass::CryptoSpot),
            5 => Ok(AssetClass::CryptoPerp),
            6 => Ok(AssetClass::CryptoFuture),
            7 => Ok(AssetClass::FxSpot),
            8 => Ok(AssetClass::Bond),
            other => Err(other),
        }
    }

    pub fn venue(&self) -> u16 { ((self.0 >> 48) & 0xFFF) as u16 }
    pub fn symbol(&self) -> u32 { ((self.0 >> 24) & 0xFFFFFF) as u32 }
    pub fn expiry_strike(&self) -> u32 { (self.0 & 0xFFFFFF) as u32 }
}

// Keep test block from Step 1
```

- [ ] **Step 3: Run tests**

Run: `cargo test --manifest-path tyche-core/Cargo.toml instrument`
Expected: 4 tests pass

- [ ] **Step 4: Commit**

```bash
git add tyche-core/src/instrument.rs
git commit -m "feat(rust): add InstrumentId with 64-bit packed fields and safe asset_class decoding"
```

---

## Task 4: Rust Data Types

*(Unchanged from v1 — tests and implementation are correct. Follow the same TDD pattern: write the 6 test functions first without the struct definitions, run to see compile failure, then add the struct definitions.)*

**Files:**
- Modify: `tyche-core/src/types.rs`

- [ ] **Step 1: Write failing tests (struct definitions absent)**

Add only the `#[cfg(test)]` block — no struct definitions.

- [ ] **Step 2: Run to confirm compile failure**

Run: `cargo test --manifest-path tyche-core/Cargo.toml types`
Expected: FAIL — types not defined

- [ ] **Step 3: Implement all data types**

```rust
// tyche-core/src/types.rs
use crate::enums::*;
use serde::{Deserialize, Serialize};

#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Tick {
    pub instrument_id: u64,
    pub price: f64,
    pub size: f64,
    pub side: Side,
    pub _pad: [u8; 7],
    pub seq: u64,
    pub timestamp_ns: u64,
}

#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Quote {
    pub instrument_id: u64,
    pub bid_price: f64,
    pub bid_size: f64,
    pub ask_price: f64,
    pub ask_size: f64,
    pub timestamp_ns: u64,
}

#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Trade {
    pub instrument_id: u64,
    pub price: f64,
    pub size: f64,
    pub aggressor_side: Side,
    pub _pad: [u8; 7],
    pub seq: u64,
    pub timestamp_ns: u64,
}

#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Bar {
    pub instrument_id: u64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
    pub interval: BarInterval,
    pub _pad: [u8; 7],
    pub timestamp_ns: u64,
}

#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Order {
    pub instrument_id: u64,
    pub client_order_id: u64,
    pub price: f64,
    pub qty: f64,
    pub side: Side,
    pub order_type: OrderType,
    pub tif: TIF,
    pub _pad: [u8; 5],
    pub timestamp_ns: u64,
}

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum OrderEventKind {
    New = 0, Cancel = 1, Replace = 2, Fill = 3, PartialFill = 4, Reject = 5,
}

#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct OrderEvent {
    pub instrument_id: u64,
    pub client_order_id: u64,
    pub exchange_order_id: u64,
    pub fill_price: f64,
    pub fill_qty: f64,
    pub kind: OrderEventKind,
    pub _pad: [u8; 7],
    pub timestamp_ns: u64,
}

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum AckStatus { Accepted = 0, Rejected = 1, CancelAcked = 2 }

#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Ack {
    pub client_order_id: u64,
    pub exchange_order_id: u64,
    pub status: AckStatus,
    pub _pad: [u8; 7],
    pub sent_ns: u64,
    pub acked_ns: u64,
}

#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Position {
    pub instrument_id: u64,
    pub net_qty: f64,
    pub avg_cost: f64,
    pub timestamp_ns: u64,
}

#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Risk {
    pub instrument_id: u64,
    pub delta: f64,
    pub gamma: f64,
    pub vega: f64,
    pub theta: f64,
    pub dv01: f64,
    pub notional: f64,
    pub margin: f64,
    pub timestamp_ns: u64,
}

/// Fixed-capacity parameter map: up to 16 key-value pairs.
#[repr(C)]
#[derive(Debug, Clone, Copy, Serialize, Deserialize)]
pub struct Model {
    pub version: u32,
    pub kind: ModelKind,
    pub _pad: [u8; 3],
    pub valid_from_ns: u64,
    pub valid_to_ns: u64,
    pub param_keys: [u32; 16],
    pub param_vals: [f64; 16],
    pub param_count: u8,
    pub _pad2: [u8; 7],
}

pub type Timestamp = u64;

#[cfg(test)]
mod tests {
    use super::*;
    use crate::enums::*;

    #[test]
    fn tick_fields_accessible() {
        let t = Tick { instrument_id: 1, price: 100.0, size: 10.0,
                       side: Side::Buy, _pad: [0; 7], seq: 1, timestamp_ns: 0 };
        assert_eq!(t.price, 100.0);
    }
    #[test]
    fn quote_spread() {
        let q = Quote { instrument_id: 1, bid_price: 99.0, bid_size: 5.0,
                        ask_price: 100.0, ask_size: 3.0, timestamp_ns: 1000 };
        assert!(q.ask_price > q.bid_price);
    }
    #[test]
    fn bar_embeds_interval() {
        let b = Bar { instrument_id: 1, open: 100.0, high: 105.0, low: 99.0, close: 103.0,
                      volume: 1000.0, interval: BarInterval::M5, _pad: [0;7], timestamp_ns: 0 };
        assert_eq!(b.interval, BarInterval::M5);
    }
    #[test]
    fn order_side_and_type() {
        let o = Order { instrument_id: 1, client_order_id: 42, price: 100.0, qty: 10.0,
                        side: Side::Buy, order_type: OrderType::Limit, tif: TIF::GTC,
                        _pad: [0;5], timestamp_ns: 0 };
        assert_eq!(o.side, Side::Buy);
    }
    #[test]
    fn position_net_qty() {
        let p = Position { instrument_id: 1, net_qty: -100.0, avg_cost: 50.5, timestamp_ns: 0 };
        assert!(p.net_qty < 0.0);
    }
    #[test]
    fn model_param_capacity() {
        let m = Model { version: 1, kind: ModelKind::VolSurface, _pad: [0;3],
                        valid_from_ns: 0, valid_to_ns: u64::MAX,
                        param_keys: [0;16], param_vals: [0.0;16], param_count: 0, _pad2: [0;7] };
        assert_eq!(m.param_keys.len(), 16);
    }
}
```

- [ ] **Step 4: Run tests**

Run: `cargo test --manifest-path tyche-core/Cargo.toml types`
Expected: 6 tests pass

- [ ] **Step 5: Commit**

```bash
git add tyche-core/src/types.rs
git commit -m "feat(rust): add all core data types"
```

---

## Task 5: Rust Clock + Serialization

*(Unchanged from v1. Follow TDD: tests first, then implementation.)*

- [ ] **Step 1: Write failing clock tests (no impl)**
- [ ] **Step 2: Run — confirm FAIL**
- [ ] **Step 3: Implement `clock.rs`** (LiveClock, SimClock with AtomicU64)
- [ ] **Step 4: Run clock tests — confirm PASS** (3 tests)
- [ ] **Step 5: Write failing serialization test (no impl)**
- [ ] **Step 6: Run — confirm FAIL**
- [ ] **Step 7: Implement `serialization.rs`** (`serialize<T>`, `deserialize<T>` via rmp-serde)
- [ ] **Step 8: Run serialization test — confirm PASS** (1 test: Quote roundtrip)
- [ ] **Step 9: Commit**

```bash
git add tyche-core/src/clock.rs tyche-core/src/serialization.rs
git commit -m "feat(rust): add Clock trait and MessagePack serialization"
```

---

## Task 6: Rust FFI Bridge

**Files:**
- Modify: `tyche-core/src/ffi_bridge.rs`

- [ ] **Step 1: Write failing tests**

The global slot functions will be module-level (no struct). Each test uses a unique `(service, topic)` pair so parallel test runs don't collide on the global registry.

```rust
// tyche-core/src/ffi_bridge.rs — tests only, no implementation yet
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn take_empty_slot_returns_none() {
        assert!(take_pending("svc_ta", "TOPIC_A").is_none());
    }
    #[test]
    fn write_then_take_returns_payload() {
        write_pending("svc_tb", "TOPIC_B", vec![1, 2, 3]);
        assert_eq!(take_pending("svc_tb", "TOPIC_B"), Some(vec![1, 2, 3]));
    }
    #[test]
    fn take_twice_second_is_none() {
        write_pending("svc_tc", "TOPIC_C", vec![1]);
        take_pending("svc_tc", "TOPIC_C");
        assert!(take_pending("svc_tc", "TOPIC_C").is_none());
    }
    #[test]
    fn write_overwrites_previous_slot() {
        write_pending("svc_td", "TOPIC_D", vec![1]);
        write_pending("svc_td", "TOPIC_D", vec![2, 3]);
        assert_eq!(take_pending("svc_td", "TOPIC_D"), Some(vec![2, 3]));
    }
}
```

- [ ] **Step 2: Run to confirm FAIL**

Run: `cargo test --manifest-path tyche-core/Cargo.toml ffi_bridge`
Expected: FAIL — `write_pending`, `take_pending` not defined

- [ ] **Step 3: Implement global AtomicPtr slot registry**

The spec (§6.4) requires a **per-topic single-slot atomic buffer** using `AtomicPtr<T>`. Write = swap new heap pointer in; drop displaced pointer if non-null. Take = swap null in; reconstruct Box from returned pointer.

```rust
// tyche-core/src/ffi_bridge.rs
use std::collections::HashMap;
use std::ptr;
use std::sync::atomic::{AtomicPtr, Ordering};
use std::sync::{OnceLock, RwLock};

/// Signal byte values sent over the inproc:// PAIR socket.
pub mod signal {
    pub const DATA_READY: u8 = 0x01;
    pub const SHUTDOWN: u8   = 0x02;
    pub const ERROR: u8      = 0x03;
}

// ── Global slot registry ──────────────────────────────────────────────────────
// Key: "{service_name}\0{topic}" (null-byte separator avoids collisions)
// Value: AtomicPtr to heap-allocated Vec<u8>; null = empty slot.
static SLOTS: OnceLock<RwLock<HashMap<String, AtomicPtr<Vec<u8>>>>> = OnceLock::new();

fn registry() -> &'static RwLock<HashMap<String, AtomicPtr<Vec<u8>>>> {
    SLOTS.get_or_init(|| RwLock::new(HashMap::new()))
}

fn slot_key(service_name: &str, topic: &str) -> String {
    format!("{}\0{}", service_name, topic)
}

// ── Public API ────────────────────────────────────────────────────────────────

/// Register a service. Call once per service before any write_pending calls.
/// Currently a no-op (slots are created lazily on first write), reserved
/// for future pre-allocation.
pub fn init_ffi_bridge(_service_name: &str) {}

/// Write payload into the per-topic slot; atomically replaces any un-taken value.
/// # Safety: unsafe block is sound — `Box::into_raw` → `Box::from_raw` is balanced.
pub fn write_pending(service_name: &str, topic: &str, payload: Vec<u8>) {
    let key = slot_key(service_name, topic);
    let new_ptr = Box::into_raw(Box::new(payload));

    // Fast path: slot already registered — just swap
    {
        let map = registry().read().unwrap();
        if let Some(slot) = map.get(&key) {
            let old = slot.swap(new_ptr, Ordering::AcqRel);
            if !old.is_null() {
                unsafe { drop(Box::from_raw(old)); }
            }
            return;
        }
    }

    // Slow path: register new slot, then write
    let mut map = registry().write().unwrap();
    let slot = map.entry(key).or_insert_with(|| AtomicPtr::new(ptr::null_mut()));
    let old = slot.swap(new_ptr, Ordering::AcqRel);
    if !old.is_null() {
        unsafe { drop(Box::from_raw(old)); }
    }
}

/// Atomically take the pending payload; returns None if slot is empty.
/// # Safety: unsafe block is sound — pointer was placed by write_pending.
pub fn take_pending(service_name: &str, topic: &str) -> Option<Vec<u8>> {
    let key = slot_key(service_name, topic);
    let map = registry().read().unwrap();
    let slot = map.get(&key)?;
    let ptr = slot.swap(ptr::null_mut(), Ordering::AcqRel);
    if ptr.is_null() {
        None
    } else {
        Some(unsafe { *Box::from_raw(ptr) })
    }
}

// Keep test block from Step 1
```

- [ ] **Step 4: Run tests**

Run: `cargo test --manifest-path tyche-core/Cargo.toml ffi_bridge`
Expected: 4 tests pass

- [ ] **Step 5: Commit**

```bash
git add tyche-core/src/ffi_bridge.rs
git commit -m "feat(rust): add FFI bridge with per-topic AtomicPtr slot registry"
```

---

## Task 7: Rust PyO3 Bindings + Build Verification

**Files:**
- Modify: `tyche-core/src/python.rs`
- Create: `tests/unit/test_bindings.py`

The PyO3 bindings expose every Rust type as a Python class, plus serialize/deserialize helpers for each type, plus module-level `init_ffi_bridge` and `take_pending` for the PAIR bridge, plus `bar_interval_from_suffix`.

- [ ] **Step 0: Write failing Python binding test (RED)**

```python
# tests/unit/test_bindings.py
import tyche_core

def test_pyquote_construction():
    q = tyche_core.PyQuote(1, 99.0, 10.0, 100.0, 5.0, 0)
    assert q.spread() == 1.0

def test_bar_interval_eq_int():
    b = tyche_core.bar_interval_from_suffix("M5")
    assert b == tyche_core.BarInterval.M5

def test_bar_interval_topic_suffix_property():
    assert tyche_core.BarInterval.M5.topic_suffix == "M5"
    assert tyche_core.BarInterval.H4.topic_suffix == "H4"

def test_init_ffi_bridge_and_take_pending():
    tyche_core.init_ffi_bridge("svc_test_py")
    result = tyche_core.take_pending("svc_test_py", "NO_TOPIC")
    assert result is None

def test_serialize_deserialize_roundtrip():
    q = tyche_core.PyQuote(42, 10.0, 5.0, 11.0, 3.0, 1000)
    raw = bytes(tyche_core.serialize_quote(q))
    q2 = tyche_core.deserialize_quote(raw)
    assert q2.bid_price == 10.0
```

Run: `pytest tests/unit/test_bindings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'tyche_core'` (not yet built)

- [ ] **Step 1: Implement python.rs**

```rust
// tyche-core/src/python.rs
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use crate::{enums::*, types::*, ffi_bridge, serialization};

// ── PyQuote ──────────────────────────────────────────────────────────────────
#[pyclass] #[derive(Clone)] pub struct PyQuote { pub inner: Quote }
#[pymethods] impl PyQuote {
    #[new]
    fn new(instrument_id: u64, bid_price: f64, bid_size: f64,
           ask_price: f64, ask_size: f64, timestamp_ns: u64) -> Self {
        Self { inner: Quote { instrument_id, bid_price, bid_size, ask_price, ask_size, timestamp_ns } }
    }
    #[getter] fn instrument_id(&self) -> u64 { self.inner.instrument_id }
    #[getter] fn bid_price(&self) -> f64 { self.inner.bid_price }
    #[getter] fn ask_price(&self) -> f64 { self.inner.ask_price }
    #[getter] fn bid_size(&self) -> f64 { self.inner.bid_size }
    #[getter] fn ask_size(&self) -> f64 { self.inner.ask_size }
    #[getter] fn timestamp_ns(&self) -> u64 { self.inner.timestamp_ns }
    fn spread(&self) -> f64 { self.inner.ask_price - self.inner.bid_price }
}

// ── Repeat the pattern above for: PyTick, PyTrade, PyBar, PyOrder, ───────────
// ── PyOrderEvent, PyAck, PyPosition, PyRisk, PyModel ─────────────────────────
// Each follows the same #[pyclass] + #[pymethods] getter pattern.
// PyBar must expose: instrument_id, open, high, low, close, volume, interval (BarInterval), timestamp_ns
// PyTick must expose: instrument_id, price, size, side (Side), seq, timestamp_ns

// ── init_ffi_bridge (module-level) ───────────────────────────────────────────
// Python Module calls this AFTER binding the inproc:// PAIR socket.
// Returns nothing; Rust side is a global registry, no handle needed.
#[pyfunction]
fn init_ffi_bridge(service_name: &str) {
    ffi_bridge::init_ffi_bridge(service_name);
}

// ── take_pending (module-level) ───────────────────────────────────────────────
// Python API: tyche_core.take_pending(service_name, topic) -> bytes | None
#[pyfunction]
fn take_pending(service_name: &str, topic: &str, py: Python<'_>) -> Option<PyObject> {
    ffi_bridge::take_pending(service_name, topic)
        .map(|b| PyBytes::new_bound(py, &b).into())
}

// ── BarInterval helpers ───────────────────────────────────────────────────────
#[pyfunction]
fn bar_interval_from_suffix(suffix: &str) -> PyResult<BarInterval> {
    BarInterval::from_suffix(suffix)
        .ok_or_else(|| pyo3::exceptions::PyValueError::new_err(
            format!("Unknown BarInterval suffix: '{suffix}'")))
}

// ── serialize / deserialize pairs for each type ───────────────────────────────
macro_rules! serde_fns {
    ($ty:ty, $ser:ident, $de:ident, $py_ty:ty) => {
        #[pyfunction]
        fn $ser(val: &$py_ty, py: Python<'_>) -> PyResult<PyObject> {
            let bytes = serialization::serialize(&val.inner)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
            Ok(PyBytes::new_bound(py, &bytes).into())
        }
        #[pyfunction]
        fn $de(data: &[u8]) -> PyResult<$py_ty> {
            let inner: $ty = serialization::deserialize(data)
                .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
            Ok(<$py_ty> { inner })
        }
    };
}

serde_fns!(Quote,      serialize_quote,      deserialize_quote,      PyQuote);
serde_fns!(Tick,       serialize_tick,       deserialize_tick,       PyTick);
serde_fns!(Trade,      serialize_trade,      deserialize_trade,      PyTrade);
serde_fns!(Bar,        serialize_bar,        deserialize_bar,        PyBar);
serde_fns!(Order,      serialize_order,      deserialize_order,      PyOrder);
serde_fns!(OrderEvent, serialize_order_event,deserialize_order_event,PyOrderEvent);
serde_fns!(Ack,        serialize_ack,        deserialize_ack,        PyAck);
serde_fns!(Position,   serialize_position,   deserialize_position,   PyPosition);
serde_fns!(Risk,       serialize_risk,       deserialize_risk,       PyRisk);
serde_fns!(Model,      serialize_model,      deserialize_model,      PyModel);

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Enums
    m.add_class::<BarInterval>()?;
    m.add_class::<ModelKind>()?;
    m.add_class::<Side>()?;
    m.add_class::<OrderType>()?;
    m.add_class::<TIF>()?;
    m.add_class::<AssetClass>()?;
    // Types
    m.add_class::<PyQuote>()?;
    m.add_class::<PyTick>()?;
    m.add_class::<PyTrade>()?;
    m.add_class::<PyBar>()?;
    m.add_class::<PyOrder>()?;
    m.add_class::<PyOrderEvent>()?;
    m.add_class::<PyAck>()?;
    m.add_class::<PyPosition>()?;
    m.add_class::<PyRisk>()?;
    m.add_class::<PyModel>()?;
    // FFI bridge functions (module-level, no handle class)
    m.add_function(wrap_pyfunction!(init_ffi_bridge, m)?)?;
    m.add_function(wrap_pyfunction!(take_pending, m)?)?;
    // BarInterval helper
    m.add_function(wrap_pyfunction!(bar_interval_from_suffix, m)?)?;
    // Serialize / deserialize (all 10 pairs)
    m.add_function(wrap_pyfunction!(serialize_quote, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_quote, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_tick, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_tick, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_trade, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_trade, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_bar, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_bar, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_order, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_order, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_order_event, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_order_event, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_ack, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_ack, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_position, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_position, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_risk, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_risk, m)?)?;
    m.add_function(wrap_pyfunction!(serialize_model, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_model, m)?)?;
    Ok(())
}
```

**Note on the macro:** `<$py_ty> { inner }` is valid Rust struct literal syntax only when `inner` is a public field. Each `Py*` wrapper must have `pub inner: $ty`. The macro expansion is correct as written.

- [ ] **Step 2: Build**

Run: `maturin develop --release`
Expected: compiles cleanly

- [ ] **Step 3: Run binding tests (GREEN)**

Run: `pytest tests/unit/test_bindings.py -v`
Expected: 5 tests pass

- [ ] **Step 4: Commit**

```bash
git add tyche-core/src/python.rs tyche-core/src/enums.rs tests/unit/test_bindings.py
git commit -m "feat(rust): add PyO3 bindings — all types, serialize/deserialize, init_ffi_bridge, take_pending"
```

---

## Task 8: Python Model Layer

*(Unchanged from v1 — tests and re-exports are correct.)*

- [ ] Write `tests/unit/test_types.py` — 4 tests (import, spread, bar interval suffix, side equality)
- [ ] Run — confirm FAIL
- [ ] Implement `tyche/model/enums.py`, `tyche/model/types.py`, `tyche/model/instrument.py`
- [ ] Run — confirm PASS
- [ ] Commit: `feat(python): add model layer re-exports`

---

## Task 9: Python Topics Utility

**Files:**
- Modify: `tyche/utils/topics.py`
- Test: `tests/unit/test_topics.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_topics.py
import pytest
from tyche.utils.topics import TopicBuilder, TopicValidator, normalise_symbol, suffix_to_bar_interval

def test_normalise_fx_removes_slash():
    assert normalise_symbol("EUR/USD") == "EURUSD"

def test_normalise_option_uses_underscore():
    assert normalise_symbol("AAPL 150C 2025-01-17") == "AAPL_150C_20250117"

def test_normalise_future_uses_underscore():
    assert normalise_symbol("ES Z25") == "ES_Z25"

def test_build_tick_topic():
    assert TopicBuilder.tick("CRYPTO_SPOT", "BINANCE", "BTCUSDT") == "CRYPTO_SPOT.BINANCE.BTCUSDT.TICK"

def test_build_bar_topic():
    from tyche.model.enums import BarInterval
    assert TopicBuilder.bar("EQUITY", "NYSE", "AAPL", BarInterval.M5) == "EQUITY.NYSE.AAPL.BAR.M5"

def test_build_internal_topic():
    assert TopicBuilder.internal("OMS", "ORDER") == "INTERNAL.OMS.ORDER"

def test_invalid_topic_raises():
    with pytest.raises(ValueError):
        TopicValidator.validate("INVALID TOPIC WITH SPACES")

def test_valid_topic_passes():
    TopicValidator.validate("EQUITY.NYSE.AAPL.QUOTE")  # must not raise

def test_topic_with_slash_raises():
    with pytest.raises(ValueError):
        TopicValidator.validate("FX_SPOT.EBS.EUR/USD.TICK")

def test_suffix_to_bar_interval_roundtrip():
    from tyche.model.enums import BarInterval
    assert suffix_to_bar_interval("M5") == BarInterval.M5
    assert suffix_to_bar_interval("H4") == BarInterval.H4

def test_suffix_to_bar_interval_invalid_raises():
    with pytest.raises(ValueError):
        suffix_to_bar_interval("INVALID")
```

Run: `pytest tests/unit/test_topics.py -v`
Expected: 11 FAILs

- [ ] **Step 2: Implement topics.py**

```python
# tyche/utils/topics.py
import re
import tyche_core
from tyche.model.enums import BarInterval

_VALID_TOPIC_RE = re.compile(r'^[A-Z0-9_\-]+(\.[A-Z0-9_\-]+)*$')


def normalise_symbol(raw: str) -> str:
    """Normalise symbol to alphanumeric + hyphen + underscore.
    - Slashes removed (EUR/USD → EURUSD)
    - Spaces replaced with underscore
    - Dashes between digits removed (date separators: 2025-01-17 → 20250117)
    """
    s = raw.replace("/", "")
    s = s.replace(" ", "_")
    # Remove dashes between digit characters (non-overlapping, applied repeatedly)
    while re.search(r'\d-\d', s):
        s = re.sub(r'(\d)-(\d)', r'\1\2', s)
    return s


def suffix_to_bar_interval(suffix: str) -> BarInterval:
    """Convert a topic suffix string (e.g. 'M5') to a BarInterval enum value."""
    return tyche_core.bar_interval_from_suffix(suffix)


class TopicBuilder:
    @staticmethod
    def tick(asset_class: str, venue: str, symbol: str) -> str:
        return f"{asset_class}.{venue}.{normalise_symbol(symbol)}.TICK"

    @staticmethod
    def quote(asset_class: str, venue: str, symbol: str) -> str:
        return f"{asset_class}.{venue}.{normalise_symbol(symbol)}.QUOTE"

    @staticmethod
    def trade(asset_class: str, venue: str, symbol: str) -> str:
        return f"{asset_class}.{venue}.{normalise_symbol(symbol)}.TRADE"

    @staticmethod
    def bar(asset_class: str, venue: str, symbol: str, interval: BarInterval) -> str:
        return f"{asset_class}.{venue}.{normalise_symbol(symbol)}.BAR.{interval.topic_suffix}"

    @staticmethod
    def internal(subsystem: str, event: str) -> str:
        return f"INTERNAL.{subsystem}.{event}"

    @staticmethod
    def ctrl(source: str, event: str) -> str:
        return f"CTRL.{source}.{event}"


class TopicValidator:
    @staticmethod
    def validate(topic: str) -> None:
        """Raise ValueError if topic contains invalid characters."""
        if not _VALID_TOPIC_RE.match(topic):
            raise ValueError(
                f"Invalid topic '{topic}': must match {_VALID_TOPIC_RE.pattern}")
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_topics.py -v`
Expected: 11 tests pass

- [ ] **Step 4: Commit**

```bash
git add tyche/utils/topics.py tests/unit/test_topics.py
git commit -m "feat(python): add topics utility with suffix_to_bar_interval"
```

---

## Task 10: Python Utils + Config

*(pyproject.toml already includes `msgpack>=1.0` from Task 1. Implement serialization.py, logging.py, config.py.)*

- [ ] **Step 1: Implement `tyche/utils/serialization.py`**

```python
# tyche/utils/serialization.py
import msgpack
import tyche_core

_TYCHE_CORE_MODULE = "tyche_core"

def serialize(payload) -> bytes:
    """Serialize a tyche_core type or plain dict to MessagePack bytes."""
    cls = type(payload)
    if cls.__module__ == _TYCHE_CORE_MODULE:
        fn_name = f"serialize_{cls.__name__.lower().lstrip('py')}"
        fn = getattr(tyche_core, fn_name, None)
        if fn:
            return bytes(fn(payload))
    return msgpack.packb(payload, use_bin_type=True)

def deserialize(type_name: str, data: bytes):
    fn = getattr(tyche_core, f"deserialize_{type_name.lower()}", None)
    if fn:
        return fn(data)
    return msgpack.unpackb(data, raw=False)
```

- [ ] **Step 2: Implement `tyche/utils/logging.py`**

```python
# tyche/utils/logging.py
import json, sys, time

class StructuredLogger:
    def __init__(self, service_name: str):
        self.service_name = service_name

    def _emit(self, level: str, message: str, **kwargs):
        print(json.dumps({"timestamp_ns": time.time_ns(), "service": self.service_name,
                           "level": level, "message": message, **kwargs}),
              file=sys.stderr, flush=True)

    def info(self, msg, **kw): self._emit("INFO", msg, **kw)
    def warn(self, msg, **kw): self._emit("WARN", msg, **kw)
    def error(self, msg, **kw): self._emit("ERROR", msg, **kw)
    def debug(self, msg, **kw): self._emit("DEBUG", msg, **kw)
```

- [ ] **Step 3: Write failing config tests**

```python
# tests/unit/test_config.py
def test_engine_toml_loads():
    from tyche.core.config import EngineConfig
    cfg = EngineConfig.from_file("config/engine.toml")
    assert cfg.nexus.address == "tcp://127.0.0.1:5555"
    assert cfg.nexus.cpu_core == 0
    assert cfg.bus.xsub_address == "tcp://127.0.0.1:5556"

def test_module_config_loads():
    from tyche.core.config import ModuleConfig
    cfg = ModuleConfig.from_file("config/modules/example_strategy.toml")
    assert cfg.service_name == "strategy.example"
    assert cfg.cpu_core == 4
    assert "EQUITY.NYSE.AAPL.QUOTE" in cfg.subscriptions

def test_nexus_policy_loads():
    from tyche.core.config import NexusPolicy
    policy = NexusPolicy.from_file("config/modules/nexus.toml")
    assert policy.heartbeat_interval_ms == 1000
    assert policy.registration_max_retries == 20
```

Run: `pytest tests/unit/test_config.py -v`
Expected: FAIL

- [ ] **Step 4: Implement config.py**

`EngineConfig` loads address/cpu fields from `engine.toml`. `NexusPolicy` loads policy fields from `nexus.toml`. These are separate objects — a full `Nexus` process load both.

```python
# tyche/core/config.py
import tomllib
from dataclasses import dataclass, field

@dataclass
class NexusAddressConfig:
    address: str
    cpu_core: int

@dataclass
class NexusPolicy:
    heartbeat_interval_ms: int = 1000
    missed_heartbeat_limit: int = 3
    registration_timeout_ms: int = 500
    registration_max_retries: int = 20
    restart_policy: str = "alert-only"

    @classmethod
    def from_file(cls, path: str) -> "NexusPolicy":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(**data["policy"])

@dataclass
class BusConfig:
    xsub_address: str
    xpub_address: str
    cpu_core: int
    sndhwm: int = 10000

@dataclass
class EngineConfig:
    nexus: NexusAddressConfig
    bus: BusConfig

    @classmethod
    def from_file(cls, path: str) -> "EngineConfig":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        return cls(
            nexus=NexusAddressConfig(**data["nexus"]),
            bus=BusConfig(**data["bus"]),
        )

@dataclass
class ModuleConfig:
    service_name: str
    cpu_core: int
    subscriptions: list[str] = field(default_factory=list)

    @classmethod
    def from_file(cls, path: str) -> "ModuleConfig":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        m = data["module"]
        return cls(service_name=m["service_name"], cpu_core=m["cpu_core"],
                   subscriptions=m.get("subscriptions", []))
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/unit/test_config.py -v`
Expected: 3 tests pass

- [ ] **Step 6: Commit**

```bash
git add tyche/utils/ tyche/core/config.py tests/unit/test_config.py
git commit -m "feat(python): add serialization helpers, structured logger, TOML config loaders"
```

---

## Task 11: Python Clock

*(Unchanged from v1. Write 4 failing tests, then implement LiveClock/SimClock.)*

- [ ] Write tests → run FAIL → implement → run PASS → commit

---

## Task 12: Python Bus Process

*(Unchanged from v1. Write 2 integration tests, then implement Bus with XPUB/XSUB proxy.)*

- [ ] Write tests → run FAIL → implement → run PASS → commit

---

## Task 13: Python Nexus Process

*(Unchanged from v1. Write 3 integration tests, implement Nexus with READY_ACK.)*

- [ ] Write tests → run FAIL → implement → run PASS → commit

---

## Task 14: Python Module Base Class

**Files:**
- Modify: `tyche/core/module.py`
- Test: `tests/integration/test_module_e2e.py`

- [ ] **Step 1: Write failing integration tests**

```python
# tests/integration/test_module_e2e.py
import time, threading, zmq, pytest
import tyche_core

NEXUS = "tcp://127.0.0.1:25555"
XSUB  = "tcp://127.0.0.1:25556"
XPUB  = "tcp://127.0.0.1:25557"

@pytest.fixture
def engine():
    from tyche.core.nexus import Nexus
    from tyche.core.bus import Bus
    n = Nexus(address=NEXUS, cpu_core=None)
    b = Bus(xsub_address=XSUB, xpub_address=XPUB, cpu_core=None)
    threading.Thread(target=n.run, daemon=True).start()
    threading.Thread(target=b.run, daemon=True).start()
    time.sleep(0.15)
    yield n, b
    n.stop(); b.stop()

def test_module_registers_with_nexus(engine):
    from tyche.core.module import Module
    nexus, _ = engine

    class Mod(Module):
        service_name = "test.reg"
        cpu_core = None

    m = Mod(nexus_address=NEXUS, bus_xsub=XSUB, bus_xpub=XPUB)
    threading.Thread(target=m.run, daemon=True).start()
    time.sleep(0.3)
    assert "test.reg" in nexus.registry
    m.stop()

def test_module_receives_typed_quote(engine):
    from tyche.core.module import Module
    from tyche.model.types import Quote as PyQuote

    received = []

    class QuoteMod(Module):
        service_name = "test.quotemod"
        cpu_core = None

        def on_start(self):
            self.subscribe("EQUITY.NYSE.AAPL.QUOTE")

        def on_quote(self, topic: str, quote):
            received.append(quote)

    m = QuoteMod(nexus_address=NEXUS, bus_xsub=XSUB, bus_xpub=XPUB)
    threading.Thread(target=m.run, daemon=True).start()
    time.sleep(0.2)

    # Publish a serialized Quote onto the Bus
    q = tyche_core.PyQuote(42, 99.5, 10.0, 100.0, 5.0, 12345)
    payload = bytes(tyche_core.serialize_quote(q))
    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    pub.connect(XSUB)
    time.sleep(0.05)
    pub.send_multipart([b"EQUITY.NYSE.AAPL.QUOTE", (0).to_bytes(8, 'big'), payload])
    time.sleep(0.2)

    assert len(received) >= 1
    assert abs(received[0].ask_price - 100.0) < 0.001
    pub.close(); ctx.term(); m.stop()

def test_module_receives_typed_bar(engine):
    from tyche.core.module import Module

    received = []

    class BarMod(Module):
        service_name = "test.barmod"
        cpu_core = None

        def on_start(self):
            self.subscribe("EQUITY.NYSE.AAPL.BAR.M5")

        def on_bar(self, topic: str, bar, interval):
            received.append((bar, interval))

    m = BarMod(nexus_address=NEXUS, bus_xsub=XSUB, bus_xpub=XPUB)
    threading.Thread(target=m.run, daemon=True).start()
    time.sleep(0.2)

    bar = tyche_core.PyBar(1, 100.0, 105.0, 99.0, 103.0, 500.0,
                           tyche_core.BarInterval.M5, 0)
    payload = bytes(tyche_core.serialize_bar(bar))
    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    pub.connect(XSUB)
    time.sleep(0.05)
    pub.send_multipart([b"EQUITY.NYSE.AAPL.BAR.M5", (0).to_bytes(8, 'big'), payload])
    time.sleep(0.2)

    assert len(received) >= 1
    recv_bar, recv_interval = received[0]
    assert recv_interval == tyche_core.BarInterval.M5
    assert abs(recv_bar.close - 103.0) < 0.001
    pub.close(); ctx.term(); m.stop()
```

Run: `pytest tests/integration/test_module_e2e.py -v`
Expected: 3 FAILs

- [ ] **Step 2: Implement module.py with typed dispatch and PAIR socket**

```python
# tyche/core/module.py
import time, threading
import zmq
from abc import ABC
import tyche_core
from tyche.utils.logging import StructuredLogger
from tyche.utils.topics import TopicValidator, suffix_to_bar_interval

PROTOCOL = b"TYCHE"
_REG_TIMEOUT_MS = 500
_REG_MAX_RETRIES = 20
_PAIR_INPROC_PREFIX = "inproc://tyche-rust-"

# Map from topic data-type suffix to (deserialize_fn, handler_attr_name)
_MARKET_DISPATCH = {
    "TICK":        ("deserialize_tick",         "on_tick"),
    "QUOTE":       ("deserialize_quote",        "on_quote"),
    "TRADE":       ("deserialize_trade",        "on_trade"),
}

_INTERNAL_DISPATCH = {
    "ORDER":       ("deserialize_order",        "on_order"),
    "ORDER_EVENT": ("deserialize_order_event",  "on_order_event"),
    "ACK":         ("deserialize_ack",          "on_ack"),
    "POSITION":    ("deserialize_position",     "on_position"),
    "RISK_UPDATE": ("deserialize_risk",         "on_risk"),
    "VOL_SURFACE": ("deserialize_model",        "on_model"),
}


class Module(ABC):
    service_name: str = "module.base"
    cpu_core: int | None = None

    def __init__(self, nexus_address: str, bus_xsub: str, bus_xpub: str):
        self._nexus_address = nexus_address
        self._bus_xsub = bus_xsub
        self._bus_xpub = bus_xpub
        self._stop_event = threading.Event()
        self._log = StructuredLogger(self.service_name)
        self._correlation_id = 0
        self._ctx: zmq.Context | None = None
        self._pub_sock: zmq.Socket | None = None
        self._sub_sock: zmq.Socket | None = None
        self._pair_sock: zmq.Socket | None = None
        # No self._ffi_bridge handle — FFI bridge is accessed via module-level
        # tyche_core.take_pending(service_name, topic).

    # ── Lifecycle hooks ────────────────────────────────────────────────────────
    def on_start(self): pass
    def on_stop(self): pass
    def on_reconfigure(self, cfg: dict): pass

    # ── Typed data handlers (override in subclass) ─────────────────────────────
    def on_tick(self, topic: str, tick): pass
    def on_quote(self, topic: str, quote): pass
    def on_trade(self, topic: str, trade): pass
    def on_bar(self, topic: str, bar, interval): pass
    def on_order(self, topic: str, order): pass
    def on_order_event(self, topic: str, event): pass
    def on_ack(self, topic: str, ack): pass
    def on_position(self, topic: str, position): pass
    def on_risk(self, topic: str, risk): pass
    def on_model(self, topic: str, model): pass
    def on_raw(self, topic: str, payload: bytes): pass

    def on_command(self, command: str, payload: dict) -> dict:
        # Default: unknown command — subclass overrides for custom commands.
        self._log.warn("Unknown command", command=command)
        return {"status": "UNKNOWN_COMMAND", "command": command}

    # ── Publish ────────────────────────────────────────────────────────────────
    # Maps Python class name → tyche_core serializer function name.
    # Per spec §6.2: tyche_core registered types use the Rust serializer;
    # plain dicts/scalars fall back to msgpack.
    _TYCHE_SERIALIZE = {
        "PyQuote":      "serialize_quote",
        "PyTick":       "serialize_tick",
        "PyTrade":      "serialize_trade",
        "PyBar":        "serialize_bar",
        "PyOrder":      "serialize_order",
        "PyOrderEvent": "serialize_order_event",
        "PyAck":        "serialize_ack",
        "PyPosition":   "serialize_position",
        "PyRisk":       "serialize_risk",
        "PyModel":      "serialize_model",
    }

    def publish(self, topic: str, payload) -> None:
        TopicValidator.validate(topic)
        if self._pub_sock is None:
            raise RuntimeError("Module not started — call run() first")
        ts = time.time_ns().to_bytes(8, 'big')
        if isinstance(payload, bytes):
            raw = payload
        else:
            ser_fn = self._TYCHE_SERIALIZE.get(type(payload).__name__)
            if ser_fn is not None:
                raw = bytes(getattr(tyche_core, ser_fn)(payload))
            else:
                import msgpack
                raw = msgpack.packb(payload, use_bin_type=True)
        self._pub_sock.send_multipart([topic.encode(), ts, raw])

    def subscribe(self, topic: str) -> None:
        TopicValidator.validate(topic)
        if self._sub_sock:
            self._sub_sock.setsockopt_string(zmq.SUBSCRIBE, topic)

    def unsubscribe(self, topic: str) -> None:
        if self._sub_sock:
            self._sub_sock.setsockopt_string(zmq.UNSUBSCRIBE, topic)

    def stop(self):
        self._stop_event.set()

    # ── Run loop ───────────────────────────────────────────────────────────────
    def run(self):
        self._pin_cpu()
        self._ctx = zmq.Context()

        # Nexus DEALER
        dealer = self._ctx.socket(zmq.DEALER)
        dealer.setsockopt_string(zmq.IDENTITY, self.service_name)
        dealer.connect(self._nexus_address)

        # Bus PUB + SUB
        self._pub_sock = self._ctx.socket(zmq.PUB)
        self._pub_sock.connect(self._bus_xsub)
        self._sub_sock = self._ctx.socket(zmq.SUB)
        self._sub_sock.connect(self._bus_xpub)

        # Internal PAIR socket for Rust FFI bridge.
        # Python binds first; Rust connects via init_ffi_bridge().
        pair_addr = f"{_PAIR_INPROC_PREFIX}{self.service_name}"
        self._pair_sock = self._ctx.socket(zmq.PAIR)
        self._pair_sock.bind(pair_addr)
        # Register service in the global AtomicPtr slot registry.
        # No handle returned — FFI bridge state is global.
        tyche_core.init_ffi_bridge(self.service_name)

        # Register with Nexus
        self._register(dealer)
        self.on_start()

        poller = zmq.Poller()
        poller.register(dealer, zmq.POLLIN)
        poller.register(self._sub_sock, zmq.POLLIN)
        poller.register(self._pair_sock, zmq.POLLIN)

        next_hb = time.time() + 1.0

        while not self._stop_event.is_set():
            events = dict(poller.poll(timeout=200))

            if dealer in events:
                self._handle_nexus(dealer, dealer.recv_multipart())

            if self._sub_sock in events:
                frames = self._sub_sock.recv_multipart()
                if len(frames) >= 3:
                    self._dispatch(frames[0].decode(), frames[2])

            if self._pair_sock in events:
                self._handle_pair(self._pair_sock.recv())

            if time.time() >= next_hb:
                dealer.send_multipart([PROTOCOL, b"HB", str(time.time_ns()).encode()])
                next_hb = time.time() + 1.0

        self.on_stop()
        dealer.send_multipart([PROTOCOL, b"DISCO", b"shutdown"])
        for s in (dealer, self._pub_sock, self._sub_sock, self._pair_sock):
            s.close()
        self._ctx.term()

    # ── Internal helpers ───────────────────────────────────────────────────────
    def _register(self, dealer):
        for attempt in range(_REG_MAX_RETRIES):
            self._correlation_id += 1
            dealer.send_multipart([
                PROTOCOL, b"READY",
                str(self._correlation_id).encode(),
                self.service_name.encode(),
                str(self.cpu_core or 0).encode(),
            ])
            poller = zmq.Poller()
            poller.register(dealer, zmq.POLLIN)
            if dict(poller.poll(timeout=_REG_TIMEOUT_MS)).get(dealer):
                frames = dealer.recv_multipart()
                # Per spec §4.3: only accept READY_ACK whose correlation_id
                # matches the one we sent; stale ACKs from previous attempts
                # are discarded so the retry loop continues.
                if (len(frames) >= 3 and frames[1] == b"READY_ACK"
                        and frames[2].decode() == str(self._correlation_id)):
                    self._log.info("Registered with Nexus", attempt=attempt + 1)
                    return
                self._log.warn("Ignored stale or unexpected frame",
                               frames=[f.decode(errors='replace') for f in frames])
        raise RuntimeError(f"Registration failed for '{self.service_name}' after {_REG_MAX_RETRIES} retries")

    def _handle_nexus(self, dealer, frames):
        # DEALER receives: [b"TYCHE", verb, ...]
        if len(frames) < 2 or frames[0] != PROTOCOL:
            return
        verb = frames[1]
        if verb == b"CMD" and len(frames) >= 4:
            import msgpack
            import os as _os
            command = frames[2].decode()
            payload = msgpack.unpackb(frames[3], raw=False) if frames[3] else {}

            # Lifecycle commands (spec §4.2) are handled internally before
            # delegating custom commands to on_command().
            # CMD frame carries no correlation_id; REPLY uses b"0" as placeholder.
            if command == "STOP":
                result = {"status": "OK"}
                dealer.send_multipart([PROTOCOL, b"REPLY", b"0",
                                       b"OK", msgpack.packb(result, use_bin_type=True)])
                self._stop_event.set()  # run loop exits → on_stop() + DISCO
                return
            elif command == "RECONFIGURE":
                self.on_reconfigure(payload)
                result = {"status": "OK"}
            elif command == "STATUS":
                result = {"status": "RUNNING", "pid": _os.getpid()}
            elif command == "START":
                result = {"status": "OK"}  # Already running; idempotent
            else:
                result = self.on_command(command, payload)

            dealer.send_multipart([PROTOCOL, b"REPLY", b"0",
                                   b"OK", msgpack.packb(result, use_bin_type=True)])

    def _handle_pair(self, raw: bytes):
        """Handle a signal from the Rust FFI bridge."""
        if not raw:
            return
        signal_type = raw[0]
        if signal_type == 0x01:  # DATA_READY
            topic = raw[1:].decode()
            item = tyche_core.take_pending(self.service_name, topic)
            if item is not None:
                self._dispatch(topic, bytes(item))
        elif signal_type == 0x02:  # SHUTDOWN
            self._stop_event.set()
        elif signal_type == 0x03:  # ERROR
            self._log.error("Rust FFI error", detail=raw[1:].decode())

    def _dispatch(self, topic: str, payload: bytes):
        """Deserialize payload and call the appropriate typed handler."""
        parts = topic.split(".")

        # INTERNAL topics: INTERNAL.SUBSYSTEM.EVENT
        if parts[0] == "INTERNAL" and len(parts) >= 3:
            event = parts[2]
            if event in _INTERNAL_DISPATCH:
                deser_name, handler_name = _INTERNAL_DISPATCH[event]
                try:
                    obj = getattr(tyche_core, deser_name)(payload)
                    getattr(self, handler_name)(topic, obj)
                except Exception as e:
                    self._log.warn("Internal dispatch failed", event=event, error=str(e))
            else:
                self.on_raw(topic, payload)
            return

        # Market data topics: ASSET_CLASS.VENUE.SYMBOL.DTYPE[.INTERVAL]
        if len(parts) < 4:
            self.on_raw(topic, payload)
            return

        dtype = parts[3]

        # BAR topics have an extra interval suffix: ...BAR.M5
        if dtype == "BAR" and len(parts) >= 5:
            try:
                bar = tyche_core.deserialize_bar(payload)
                interval = suffix_to_bar_interval(parts[4])
                self.on_bar(topic, bar, interval)
            except Exception as e:
                self._log.warn("Bar dispatch failed", error=str(e))
            return

        if dtype in _MARKET_DISPATCH:
            deser_name, handler_name = _MARKET_DISPATCH[dtype]
            try:
                obj = getattr(tyche_core, deser_name)(payload)
                getattr(self, handler_name)(topic, obj)
            except Exception as e:
                self._log.warn("Market dispatch failed", dtype=dtype, error=str(e))
        else:
            self.on_raw(topic, payload)

    def _pin_cpu(self):
        if self.cpu_core is None:
            return
        try:
            import os
            os.sched_setaffinity(0, {self.cpu_core})
        except AttributeError:
            import ctypes
            h = ctypes.windll.kernel32.GetCurrentThread()
            ctypes.windll.kernel32.SetThreadAffinityMask(h, 1 << self.cpu_core)
```

- [ ] **Step 3: Run integration tests**

Run: `pytest tests/integration/test_module_e2e.py -v`
Expected: 3 tests pass

- [ ] **Step 4: Commit**

```bash
git add tyche/core/module.py tests/integration/test_module_e2e.py
git commit -m "feat(python): add Module base class — typed dispatch, PAIR socket, READY_ACK registration"
```

---

## Task 15: Final Validation + Implementation Log

- [ ] **Step 1: Run full test suite from clean build**

```bash
make clean && make test
```

Expected:
```
running 22 tests    ← Rust unit tests (enums: 4, instrument: 4, types: 6, clock: 3, serialization: 1, ffi_bridge: 4)
test result: ok. 22 passed

========================= 39 passed in N.Ns =====  ← Python tests (bindings: 5, instrument: 4, types: 4, topics: 11, config: 3, clock: 4, bus: 2, nexus: 3, module e2e: 3)
```

- [ ] **Step 2: Verify full Python smoke test**

```bash
python3 -c "
import tyche_core
from tyche.core.config import EngineConfig, NexusPolicy
from tyche.core.clock import LiveClock
from tyche.utils.topics import TopicBuilder, suffix_to_bar_interval
from tyche.model.enums import BarInterval

print('All imports OK')
print('M5 suffix:', BarInterval.M5.topic_suffix)
print('Topic:', TopicBuilder.bar('EQUITY', 'NYSE', 'AAPL', BarInterval.M5))
print('Interval eq:', suffix_to_bar_interval('M5') == BarInterval.M5)
print('Clock:', LiveClock().now_ns())
print('Config:', EngineConfig.from_file('config/engine.toml').nexus.address)
"
```

Expected: all lines print without errors.

- [ ] **Step 3: Write implementation log**

Create `docs/impl/core_engine_implement_v1.md` with: date, tasks completed, any spec deviations, known limitations for subsequent sub-projects.

- [ ] **Step 4: Final commit**

```bash
git add docs/impl/core_engine_implement_v1.md
git commit -m "docs: add core engine implementation log v1"
```

---

*Total: 15 tasks, ~85 steps. Rust unit tests: 22. Python tests: 39.*
