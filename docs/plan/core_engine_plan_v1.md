# Core Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the TycheEngine core engine — the shared Rust type library, PyO3 bindings, ZeroMQ Bus/Nexus hub processes, and Python Module base class that all subsequent sub-projects depend on.

**Architecture:** A Rust crate (`tyche-core`) defines all hot-path data types as `#[repr(C)]` structs and `#[repr(u8)]` enums, exposed to Python via PyO3 bindings built with maturin. Two Python hub processes (Nexus: ROUTER/DEALER lifecycle broker; Bus: XPUB/XSUB data proxy) run as independent OS processes pinned to CPU cores 0 and 1 respectively. All trading modules inherit from a Python `Module` base class that connects to both hubs and dispatches typed messages to handler methods.

**Tech Stack:** Rust 1.78+ (edition 2021), PyO3 0.22.x, maturin 1.5+, rmp-serde 1.3.x, Python 3.11+, pyzmq 25+, core_affinity 0.8.x

**Spec:** `docs/design/core_engine_design_v3.md`

**Platform note:** Development on Windows 11; production target is Linux. Commands show Linux syntax; Windows equivalents noted where they differ. Use `python` or `py` on Windows where `python3` is shown.

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
| `tyche-core/src/ffi_bridge.rs` | Per-topic `AtomicPtr` pending slots, `take_pending`, signal types |
| `tyche-core/src/python.rs` | PyO3 module; exposes all types, `init_ffi_bridge`, `take_pending`, `serialize`, `deserialize` |

### Build system
| File | Responsibility |
|------|---------------|
| `Cargo.toml` | Workspace root; pins workspace-level dependency versions |
| `pyproject.toml` | maturin build config; Python package metadata |
| `Makefile` | `build`, `test`, `lint`, `clean` targets |

### Python package — `tyche/`
| File | Responsibility |
|------|---------------|
| `tyche/__init__.py` | Package root |
| `tyche/model/__init__.py` | Re-exports all model types |
| `tyche/model/instrument.py` | `Instrument` Python wrapper + `AssetClass`, `Venue` helpers |
| `tyche/model/types.py` | Re-exports all `tyche_core` data types |
| `tyche/model/enums.py` | Re-exports all `tyche_core` enums |
| `tyche/utils/__init__.py` | Utils package root |
| `tyche/utils/topics.py` | Topic builder, parser, validator; symbol normalisation |
| `tyche/utils/serialization.py` | MessagePack helpers wrapping `tyche_core.serialize/deserialize` |
| `tyche/utils/logging.py` | Structured JSON logger |
| `tyche/core/__init__.py` | Core package root |
| `tyche/core/clock.py` | `LiveClock`, `SimClock` Python wrappers around `tyche_core` |
| `tyche/core/config.py` | `NexusConfig`, `BusConfig`, `ModuleConfig`; TOML loading |
| `tyche/core/bus.py` | `Bus` process: XPUB/XSUB proxy with CPU pinning |
| `tyche/core/nexus.py` | `Nexus` process: ROUTER/DEALER Majordomo broker |
| `tyche/core/module.py` | `Module` abstract base class with run loop and typed handlers |

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
| `tests/__init__.py` | Test root |
| `tests/unit/__init__.py` | Unit test package |
| `tests/unit/test_instrument.py` | InstrumentId encode/decode, field extraction |
| `tests/unit/test_types.py` | Construction and field access for all data types |
| `tests/unit/test_topics.py` | Topic building, parsing, validation, normalisation |
| `tests/unit/test_config.py` | TOML config loading and validation |
| `tests/unit/test_clock.py` | LiveClock monotonicity, SimClock advance |
| `tests/integration/__init__.py` | Integration test package |
| `tests/integration/test_bus_pubsub.py` | Bus process: publish/subscribe, topic prefix matching, gap detection |
| `tests/integration/test_nexus_lifecycle.py` | Nexus: registration, READY_ACK, heartbeat, STOP command |
| `tests/integration/test_module_e2e.py` | Full end-to-end: module registers, subscribes, receives typed data |

---

## Task 1: Project Scaffold

**Files:**
- Create: `Cargo.toml`
- Create: `tyche-core/Cargo.toml`
- Create: `tyche-core/src/lib.rs`
- Create: `pyproject.toml`
- Create: `Makefile`
- Create: `config/engine.toml`, `config/modules/nexus.toml`, `config/modules/bus.toml`, `config/modules/example_strategy.toml`
- Create: all `__init__.py` files and empty source stubs

- [ ] **Step 1: Create workspace Cargo.toml**

```toml
# Cargo.toml
[workspace]
members = ["tyche-core"]
resolver = "2"

[workspace.dependencies]
pyo3 = { version = "0.22", features = ["extension-module"] }
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
]

[tool.maturin]
module-name = "tyche_core"
python-source = "."
manifest-path = "tyche-core/Cargo.toml"
```

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
```

```toml
# config/modules/nexus.toml
[nexus]
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

Create empty `__init__.py` in: `tyche/`, `tyche/core/`, `tyche/model/`, `tyche/utils/`, `tests/`, `tests/unit/`, `tests/integration/`

Create empty stub files (just `# TODO` comment):
`tyche/core/clock.py`, `tyche/core/config.py`, `tyche/core/bus.py`, `tyche/core/nexus.py`, `tyche/core/module.py`
`tyche/model/instrument.py`, `tyche/model/types.py`, `tyche/model/enums.py`
`tyche/utils/topics.py`, `tyche/utils/serialization.py`, `tyche/utils/logging.py`

- [ ] **Step 8: Verify workspace compiles (empty crate)**

Create a minimal `tyche-core/src/python.rs`:
```rust
// tyche-core/src/python.rs
use pyo3::prelude::*;

pub fn register(_m: &Bound<'_, PyModule>) -> PyResult<()> {
    Ok(())
}
```

Create empty module stubs in Rust:
```rust
// tyche-core/src/enums.rs — empty for now
// tyche-core/src/instrument.rs — empty for now
// tyche-core/src/types.rs — empty for now
// tyche-core/src/clock.rs — empty for now
// tyche-core/src/serialization.rs — empty for now
// tyche-core/src/ffi_bridge.rs — empty for now
```

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

- [ ] **Step 1: Write Rust tests for enums**

Add to `tyche-core/src/enums.rs`:

```rust
use serde::{Deserialize, Serialize};

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum BarInterval {
    M1 = 0, M3 = 1, M5 = 2, M15 = 3, M30 = 4,
    H1 = 5, H4 = 6, D1 = 7, W1 = 8,
}

impl BarInterval {
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
pub enum ModelKind {
    VolSurface = 0, FairValue = 1, Signal = 2, RiskFactor = 3, Custom = 255,
}

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Side { Buy = 0, Sell = 1 }

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum OrderType { Market = 0, Limit = 1, Stop = 2, StopLimit = 3 }

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum TIF { GTC = 0, IOC = 1, FOK = 2, GTD = 3, Day = 4 }

#[repr(u8)]
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum AssetClass {
    Equity = 0, EquityOption = 1, Future = 2, FutureOption = 3,
    CryptoSpot = 4, CryptoPerp = 5, CryptoFuture = 6, FxSpot = 7, Bond = 8,
}

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

- [ ] **Step 2: Run tests (should pass — tests and impl written together)**

Run: `cargo test --manifest-path tyche-core/Cargo.toml enums`
Expected: `test enums::tests::bar_interval_topic_suffix_matches_variant ... ok` (3 tests pass)

- [ ] **Step 3: Commit**

```bash
git add tyche-core/src/enums.rs
git commit -m "feat(rust): add BarInterval, ModelKind, Side, OrderType, TIF, AssetClass enums"
```

---

## Task 3: Rust InstrumentId

**Files:**
- Modify: `tyche-core/src/instrument.rs`

- [ ] **Step 1: Write failing Rust test first**

```rust
// tyche-core/src/instrument.rs — tests first
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn encode_decode_roundtrip() {
        let id = InstrumentId::new(AssetClass::Equity, 1, 42, 0);
        assert_eq!(id.asset_class(), AssetClass::Equity);
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
}
```

Run: `cargo test --manifest-path tyche-core/Cargo.toml instrument`
Expected: FAIL — `InstrumentId` not defined

- [ ] **Step 2: Implement InstrumentId**

```rust
// tyche-core/src/instrument.rs
use crate::enums::AssetClass;
use serde::{Deserialize, Serialize};

/// 64-bit packed instrument identifier.
/// Bit layout: [63..60] AssetClass (4 bits) | [59..48] Venue (12 bits)
///             | [47..24] Symbol (24 bits)   | [23..0] Expiry/Strike (24 bits)
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

    pub fn raw(&self) -> u64 { self.0 }
    pub fn asset_class(&self) -> AssetClass {
        let bits = (self.0 >> 60) as u8;
        // SAFETY: AssetClass values 0-8 are the only valid discriminants.
        // Caller is responsible for constructing valid IDs via InstrumentId::new.
        unsafe { std::mem::transmute(bits) }
    }
    pub fn venue(&self) -> u16 { ((self.0 >> 48) & 0xFFF) as u16 }
    pub fn symbol(&self) -> u32 { ((self.0 >> 24) & 0xFFFFFF) as u32 }
    pub fn expiry_strike(&self) -> u32 { (self.0 & 0xFFFFFF) as u32 }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn encode_decode_roundtrip() {
        let id = InstrumentId::new(AssetClass::Equity, 1, 42, 0);
        assert_eq!(id.asset_class(), AssetClass::Equity);
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
}
```

- [ ] **Step 3: Run tests**

Run: `cargo test --manifest-path tyche-core/Cargo.toml instrument`
Expected: 3 tests pass

- [ ] **Step 4: Commit**

```bash
git add tyche-core/src/instrument.rs
git commit -m "feat(rust): add InstrumentId with 64-bit packed field encoding"
```

---

## Task 4: Rust Data Types

**Files:**
- Modify: `tyche-core/src/types.rs`

- [ ] **Step 1: Write failing tests**

```rust
// tyche-core/src/types.rs — tests block first
#[cfg(test)]
mod tests {
    use super::*;
    use crate::enums::*;

    #[test]
    fn tick_is_repr_c_sized() {
        // Tick: instrument_id(8) + price(8) + size(8) + side(1) + _pad(7) + seq(8) + ts(8) = 48
        // Accept any size >= 40 (padding may vary); just ensure it compiles and fields are accessible
        let t = Tick { instrument_id: 1, price: 100.0, size: 10.0, side: Side::Buy, seq: 1, timestamp_ns: 0 };
        assert_eq!(t.price, 100.0);
    }
    #[test]
    fn quote_fields_accessible() {
        let q = Quote { instrument_id: 1, bid_price: 99.0, bid_size: 5.0,
                        ask_price: 100.0, ask_size: 3.0, timestamp_ns: 1000 };
        assert!(q.ask_price > q.bid_price);
    }
    #[test]
    fn bar_has_interval() {
        let b = Bar { instrument_id: 1, open: 100.0, high: 105.0, low: 99.0, close: 103.0,
                      volume: 1000.0, interval: BarInterval::M5, timestamp_ns: 0 };
        assert_eq!(b.interval, BarInterval::M5);
    }
    #[test]
    fn order_has_side_and_type() {
        let o = Order { instrument_id: 1, client_order_id: 42, price: 100.0, qty: 10.0,
                        side: Side::Buy, order_type: OrderType::Limit, tif: TIF::GTC, timestamp_ns: 0 };
        assert_eq!(o.side, Side::Buy);
    }
}
```

Run: `cargo test --manifest-path tyche-core/Cargo.toml types`
Expected: FAIL — types not defined

- [ ] **Step 2: Implement all data types**

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

/// Fixed-capacity parameter map: up to 16 key-value pairs of (u32, f64).
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

pub type Timestamp = u64;  // nanoseconds since Unix epoch

#[cfg(test)]
mod tests {
    use super::*;
    use crate::enums::*;

    #[test]
    fn tick_is_repr_c_sized() {
        let t = Tick { instrument_id: 1, price: 100.0, size: 10.0,
                       side: Side::Buy, _pad: [0; 7], seq: 1, timestamp_ns: 0 };
        assert_eq!(t.price, 100.0);
    }
    #[test]
    fn quote_fields_accessible() {
        let q = Quote { instrument_id: 1, bid_price: 99.0, bid_size: 5.0,
                        ask_price: 100.0, ask_size: 3.0, timestamp_ns: 1000 };
        assert!(q.ask_price > q.bid_price);
    }
    #[test]
    fn bar_has_interval() {
        let b = Bar { instrument_id: 1, open: 100.0, high: 105.0, low: 99.0, close: 103.0,
                      volume: 1000.0, interval: BarInterval::M5, _pad: [0;7], timestamp_ns: 0 };
        assert_eq!(b.interval, BarInterval::M5);
    }
    #[test]
    fn order_has_side_and_type() {
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

- [ ] **Step 3: Run tests**

Run: `cargo test --manifest-path tyche-core/Cargo.toml types`
Expected: 6 tests pass

- [ ] **Step 4: Commit**

```bash
git add tyche-core/src/types.rs
git commit -m "feat(rust): add all core data types (Tick, Quote, Trade, Bar, Order, OrderEvent, Ack, Position, Risk, Model)"
```

---

## Task 5: Rust Clock + Serialization

**Files:**
- Modify: `tyche-core/src/clock.rs`
- Modify: `tyche-core/src/serialization.rs`

- [ ] **Step 1: Write failing clock tests**

```rust
// tyche-core/src/clock.rs — tests first
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn live_clock_is_monotonic() {
        let c = LiveClock;
        let t1 = c.now_ns();
        let t2 = c.now_ns();
        assert!(t2 >= t1);
    }
    #[test]
    fn sim_clock_starts_at_given_time() {
        let c = SimClock::new(1_000_000);
        assert_eq!(c.now_ns(), 1_000_000);
    }
    #[test]
    fn sim_clock_advances() {
        let mut c = SimClock::new(0);
        c.advance(500);
        assert_eq!(c.now_ns(), 500);
    }
}
```

Run: `cargo test --manifest-path tyche-core/Cargo.toml clock`
Expected: FAIL

- [ ] **Step 2: Implement Clock**

```rust
// tyche-core/src/clock.rs
use std::time::{SystemTime, UNIX_EPOCH};
use std::sync::atomic::{AtomicU64, Ordering};

pub trait Clock: Send + Sync {
    fn now_ns(&self) -> u64;
}

pub struct LiveClock;

impl Clock for LiveClock {
    fn now_ns(&self) -> u64 {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .expect("time before epoch")
            .as_nanos() as u64
    }
}

pub struct SimClock {
    current_ns: AtomicU64,
}

impl SimClock {
    pub fn new(start_ns: u64) -> Self {
        Self { current_ns: AtomicU64::new(start_ns) }
    }
    pub fn advance(&self, delta_ns: u64) {
        self.current_ns.fetch_add(delta_ns, Ordering::Relaxed);
    }
}

impl Clock for SimClock {
    fn now_ns(&self) -> u64 {
        self.current_ns.load(Ordering::Relaxed)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn live_clock_is_monotonic() {
        let c = LiveClock;
        let t1 = c.now_ns();
        let t2 = c.now_ns();
        assert!(t2 >= t1);
    }
    #[test]
    fn sim_clock_starts_at_given_time() {
        let c = SimClock::new(1_000_000);
        assert_eq!(c.now_ns(), 1_000_000);
    }
    #[test]
    fn sim_clock_advances() {
        let c = SimClock::new(0);
        c.advance(500);
        assert_eq!(c.now_ns(), 500);
    }
}
```

- [ ] **Step 3: Run clock tests**

Run: `cargo test --manifest-path tyche-core/Cargo.toml clock`
Expected: 3 tests pass

- [ ] **Step 4: Write failing serialization tests**

```rust
// tyche-core/src/serialization.rs — tests first
#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::Quote;
    #[test]
    fn quote_roundtrip() {
        let q = Quote { instrument_id: 42, bid_price: 99.5, bid_size: 10.0,
                        ask_price: 100.0, ask_size: 5.0, timestamp_ns: 123456 };
        let bytes = serialize(&q).unwrap();
        let q2: Quote = deserialize(&bytes).unwrap();
        assert_eq!(q2.instrument_id, q.instrument_id);
        assert_eq!(q2.bid_price, q.bid_price);
    }
}
```

Run: `cargo test --manifest-path tyche-core/Cargo.toml serialization`
Expected: FAIL

- [ ] **Step 5: Implement serialization**

```rust
// tyche-core/src/serialization.rs
use serde::{Deserialize, Serialize};

pub fn serialize<T: Serialize>(value: &T) -> Result<Vec<u8>, rmp_serde::encode::Error> {
    rmp_serde::to_vec(value)
}

pub fn deserialize<'de, T: Deserialize<'de>>(bytes: &'de [u8]) -> Result<T, rmp_serde::decode::Error> {
    rmp_serde::from_slice(bytes)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::types::Quote;
    #[test]
    fn quote_roundtrip() {
        let q = Quote { instrument_id: 42, bid_price: 99.5, bid_size: 10.0,
                        ask_price: 100.0, ask_size: 5.0, timestamp_ns: 123456 };
        let bytes = serialize(&q).unwrap();
        let q2: Quote = deserialize(&bytes).unwrap();
        assert_eq!(q2.instrument_id, q.instrument_id);
        assert_eq!(q2.bid_price, q.bid_price);
    }
}
```

- [ ] **Step 6: Run serialization tests**

Run: `cargo test --manifest-path tyche-core/Cargo.toml serialization`
Expected: 1 test passes

- [ ] **Step 7: Commit**

```bash
git add tyche-core/src/clock.rs tyche-core/src/serialization.rs
git commit -m "feat(rust): add Clock trait (LiveClock, SimClock) and MessagePack serialization"
```

---

## Task 6: Rust FFI Bridge

**Files:**
- Modify: `tyche-core/src/ffi_bridge.rs`

- [ ] **Step 1: Write failing tests**

```rust
// tyche-core/src/ffi_bridge.rs — tests first
#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn take_empty_slot_returns_none() {
        let bridge = FfiBridge::new("test-svc");
        assert!(bridge.take_pending("EQUITY.NYSE.AAPL.TICK").is_none());
    }
    #[test]
    fn write_then_take_returns_signal() {
        let bridge = FfiBridge::new("test-svc");
        let payload = vec![0x01u8, 10, 20, 30];
        bridge.write_pending("EQUITY.NYSE.AAPL.TICK", payload.clone());
        let taken = bridge.take_pending("EQUITY.NYSE.AAPL.TICK");
        assert_eq!(taken, Some(payload));
    }
    #[test]
    fn take_twice_second_is_none() {
        let bridge = FfiBridge::new("test-svc");
        bridge.write_pending("T", vec![1, 2, 3]);
        bridge.take_pending("T");
        assert!(bridge.take_pending("T").is_none());
    }
}
```

Run: `cargo test --manifest-path tyche-core/Cargo.toml ffi_bridge`
Expected: FAIL

- [ ] **Step 2: Implement FFI bridge**

```rust
// tyche-core/src/ffi_bridge.rs
use std::collections::HashMap;
use std::sync::{Arc, Mutex};

/// Signal type byte values sent over the PAIR socket.
pub mod signal {
    pub const DATA_READY: u8 = 0x01;
    pub const SHUTDOWN: u8   = 0x02;
    pub const ERROR: u8      = 0x03;
}

/// Per-service single-slot pending buffer.
/// Each topic maps to at most one buffered payload (last-write-wins).
#[derive(Clone)]
pub struct FfiBridge {
    pub service_name: String,
    slots: Arc<Mutex<HashMap<String, Vec<u8>>>>,
}

impl FfiBridge {
    pub fn new(service_name: &str) -> Self {
        Self {
            service_name: service_name.to_string(),
            slots: Arc::new(Mutex::new(HashMap::new())),
        }
    }

    /// Write a payload into the pending slot for the given topic (overwrites previous).
    pub fn write_pending(&self, topic: &str, payload: Vec<u8>) {
        self.slots.lock().unwrap().insert(topic.to_string(), payload);
    }

    /// Atomically take the pending payload for a topic. Returns None if slot is empty.
    pub fn take_pending(&self, topic: &str) -> Option<Vec<u8>> {
        self.slots.lock().unwrap().remove(topic)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn take_empty_slot_returns_none() {
        let bridge = FfiBridge::new("test-svc");
        assert!(bridge.take_pending("EQUITY.NYSE.AAPL.TICK").is_none());
    }
    #[test]
    fn write_then_take_returns_signal() {
        let bridge = FfiBridge::new("test-svc");
        let payload = vec![0x01u8, 10, 20, 30];
        bridge.write_pending("EQUITY.NYSE.AAPL.TICK", payload.clone());
        let taken = bridge.take_pending("EQUITY.NYSE.AAPL.TICK");
        assert_eq!(taken, Some(payload));
    }
    #[test]
    fn take_twice_second_is_none() {
        let bridge = FfiBridge::new("test-svc");
        bridge.write_pending("T", vec![1, 2, 3]);
        bridge.take_pending("T");
        assert!(bridge.take_pending("T").is_none());
    }
}
```

- [ ] **Step 3: Run tests**

Run: `cargo test --manifest-path tyche-core/Cargo.toml ffi_bridge`
Expected: 3 tests pass

- [ ] **Step 4: Commit**

```bash
git add tyche-core/src/ffi_bridge.rs
git commit -m "feat(rust): add FfiBridge with per-topic pending slots and take_pending"
```

---

## Task 7: Rust PyO3 Bindings + Build Verification

**Files:**
- Modify: `tyche-core/src/python.rs`
- Modify: `tyche-core/src/lib.rs` (add `use` declarations)

- [ ] **Step 1: Implement PyO3 bindings**

```rust
// tyche-core/src/python.rs
use pyo3::prelude::*;
use pyo3::types::PyBytes;
use crate::{enums::*, types::*, ffi_bridge::FfiBridge, serialization};

// Expose enums as Python classes
#[pymethods]
impl BarInterval {
    #[getter] fn topic_suffix(&self) -> &str { BarInterval::topic_suffix(self) }
    fn __repr__(&self) -> String { format!("{:?}", self) }
}

// Expose key types as Python classes (Quote shown as example; pattern repeats for all types)
#[pyclass]
#[derive(Clone)]
pub struct PyQuote { pub inner: Quote }

#[pymethods]
impl PyQuote {
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

// FfiBridge Python wrapper
#[pyclass]
pub struct PyFfiBridge { inner: FfiBridge }

#[pymethods]
impl PyFfiBridge {
    #[new]
    fn new(service_name: &str) -> Self { Self { inner: FfiBridge::new(service_name) } }
    fn write_pending(&self, topic: &str, payload: Vec<u8>) {
        self.inner.write_pending(topic, payload);
    }
    fn take_pending(&self, topic: &str, py: Python<'_>) -> Option<PyObject> {
        self.inner.take_pending(topic).map(|b| PyBytes::new_bound(py, &b).into())
    }
}

// serialize/deserialize helpers (type-tagged dispatch)
#[pyfunction]
fn serialize_quote(q: &PyQuote, py: Python<'_>) -> PyResult<PyObject> {
    let bytes = serialization::serialize(&q.inner)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
    Ok(PyBytes::new_bound(py, &bytes).into())
}

#[pyfunction]
fn deserialize_quote(data: &[u8]) -> PyResult<PyQuote> {
    let inner: Quote = serialization::deserialize(data)
        .map_err(|e| pyo3::exceptions::PyValueError::new_err(e.to_string()))?;
    Ok(PyQuote { inner })
}

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
    m.add_class::<PyFfiBridge>()?;
    // Functions
    m.add_function(wrap_pyfunction!(serialize_quote, m)?)?;
    m.add_function(wrap_pyfunction!(deserialize_quote, m)?)?;
    Ok(())
}
```

**Note:** The pattern above (showing `Quote` / `PyQuote`) must be repeated for `Tick`, `Trade`, `Bar`, `Order`, `OrderEvent`, `Ack`, `Position`, `Risk`, `Model`. Each follows the identical `#[pyclass]` wrapper + `#[pymethods]` getter pattern. Implement all 10 type wrappers before proceeding.

- [ ] **Step 2: Add `#[pyclass]` derive to enums in enums.rs**

Add `use pyo3::prelude::*;` and `#[pyclass]` attribute to each enum in `enums.rs`.

- [ ] **Step 3: Build the crate**

Run: `maturin develop --release`
Expected: compiles cleanly; `tyche_core` importable in Python

- [ ] **Step 4: Verify Python import**

Run:
```bash
python3 -c "import tyche_core; q = tyche_core.PyQuote(1, 99.0, 10.0, 100.0, 5.0, 0); print(q.spread())"
```
Expected: `1.0`

- [ ] **Step 5: Commit**

```bash
git add tyche-core/src/python.rs tyche-core/src/enums.rs tyche-core/src/lib.rs
git commit -m "feat(rust): add PyO3 bindings for all core types and enums"
```

---

## Task 8: Python Model Layer

**Files:**
- Modify: `tyche/model/enums.py`
- Modify: `tyche/model/types.py`
- Modify: `tyche/model/instrument.py`
- Test: `tests/unit/test_types.py`

- [ ] **Step 1: Write failing Python tests**

```python
# tests/unit/test_types.py
import pytest

def test_import_tyche_core():
    import tyche_core
    assert hasattr(tyche_core, "PyQuote")

def test_quote_spread():
    from tyche.model.types import Quote
    q = Quote(instrument_id=1, bid_price=99.0, bid_size=10.0,
              ask_price=100.0, ask_size=5.0, timestamp_ns=0)
    assert q.spread() == pytest.approx(1.0)

def test_bar_interval_suffix():
    from tyche.model.enums import BarInterval
    assert BarInterval.M5.topic_suffix == "M5"
    assert BarInterval.H4.topic_suffix == "H4"

def test_side_values():
    from tyche.model.enums import Side
    assert Side.Buy is not None
    assert Side.Sell is not None
```

Run: `pytest tests/unit/test_types.py -v`
Expected: FAIL — `tyche.model.types` not implemented

- [ ] **Step 2: Implement re-exports**

```python
# tyche/model/enums.py
from tyche_core import BarInterval, ModelKind, Side, OrderType, TIF, AssetClass
__all__ = ["BarInterval", "ModelKind", "Side", "OrderType", "TIF", "AssetClass"]
```

```python
# tyche/model/types.py
from tyche_core import (
    PyQuote as Quote,
    PyTick as Tick,
    PyTrade as Trade,
    PyBar as Bar,
    PyOrder as Order,
    PyOrderEvent as OrderEvent,
    PyAck as Ack,
    PyPosition as Position,
    PyRisk as Risk,
    PyModel as Model,
)
__all__ = ["Quote", "Tick", "Trade", "Bar", "Order", "OrderEvent",
           "Ack", "Position", "Risk", "Model"]
```

```python
# tyche/model/instrument.py
from tyche_core import AssetClass
from dataclasses import dataclass

@dataclass(frozen=True)
class Instrument:
    instrument_id: int
    symbol: str
    asset_class: AssetClass
    venue: str
    description: str = ""
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_types.py -v`
Expected: 4 tests pass

- [ ] **Step 4: Commit**

```bash
git add tyche/model/ tests/unit/test_types.py
git commit -m "feat(python): add model layer — re-exports from tyche_core, Instrument dataclass"
```

---

## Task 9: Python Topics Utility

**Files:**
- Modify: `tyche/utils/topics.py`
- Test: `tests/unit/test_topics.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_topics.py
import pytest
from tyche.utils.topics import TopicBuilder, TopicValidator, normalise_symbol

def test_normalise_fx_removes_slash():
    assert normalise_symbol("EUR/USD") == "EURUSD"

def test_normalise_option_uses_underscore():
    assert normalise_symbol("AAPL 150C 2025-01-17") == "AAPL_150C_20250117"

def test_normalise_future_uses_underscore():
    assert normalise_symbol("ES Z25") == "ES_Z25"

def test_build_tick_topic():
    t = TopicBuilder.tick("CRYPTO_SPOT", "BINANCE", "BTCUSDT")
    assert t == "CRYPTO_SPOT.BINANCE.BTCUSDT.TICK"

def test_build_bar_topic():
    from tyche.model.enums import BarInterval
    t = TopicBuilder.bar("EQUITY", "NYSE", "AAPL", BarInterval.M5)
    assert t == "EQUITY.NYSE.AAPL.BAR.M5"

def test_build_internal_topic():
    t = TopicBuilder.internal("OMS", "ORDER")
    assert t == "INTERNAL.OMS.ORDER"

def test_invalid_topic_raises():
    with pytest.raises(ValueError):
        TopicValidator.validate("INVALID TOPIC WITH SPACES")

def test_valid_topic_passes():
    TopicValidator.validate("EQUITY.NYSE.AAPL.QUOTE")  # should not raise

def test_topic_with_slash_in_symbol_raises():
    with pytest.raises(ValueError):
        TopicValidator.validate("FX_SPOT.EBS.EUR/USD.TICK")
```

Run: `pytest tests/unit/test_topics.py -v`
Expected: 9 FAILs

- [ ] **Step 2: Implement topics.py**

```python
# tyche/utils/topics.py
import re
from tyche.model.enums import BarInterval

_VALID_TOPIC_RE = re.compile(r'^[A-Z0-9_\-]+(\.[A-Z0-9_\-]+)*$')


def normalise_symbol(raw: str) -> str:
    """Normalise a symbol to alphanumeric + hyphen + underscore only.

    Rules:
    - Slashes removed (EUR/USD → EURUSD)
    - Spaces and dashes between words replaced with underscore (AAPL 150C → AAPL_150C)
    - Date separators (-) inside a date component removed (2025-01-17 → 20250117)
    """
    # Remove slashes entirely
    s = raw.replace("/", "")
    # Replace spaces with underscore
    s = s.replace(" ", "_")
    # Remove dashes that are part of dates (between digits)
    s = re.sub(r'(\d)-(\d)', r'\1\2', s)
    return s


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
                f"Invalid topic '{topic}': must match {_VALID_TOPIC_RE.pattern}"
            )
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_topics.py -v`
Expected: 9 tests pass

- [ ] **Step 4: Commit**

```bash
git add tyche/utils/topics.py tests/unit/test_topics.py
git commit -m "feat(python): add topics utility — builder, validator, symbol normalisation"
```

---

## Task 10: Python Utils + Config

**Files:**
- Modify: `tyche/utils/serialization.py`
- Modify: `tyche/utils/logging.py`
- Modify: `tyche/core/config.py`
- Test: `tests/unit/test_config.py`

- [ ] **Step 1: Implement serialization.py**

```python
# tyche/utils/serialization.py
import tyche_core

def serialize(payload) -> bytes:
    """Serialize a tyche_core type or plain dict to MessagePack bytes."""
    if hasattr(payload, '__class__') and payload.__class__.__module__ == 'tyche_core':
        # tyche_core registered type — use Rust serializer
        type_name = type(payload).__name__
        fn = getattr(tyche_core, f"serialize_{type_name.lower().lstrip('py')}", None)
        if fn:
            return bytes(fn(payload))
    # Fallback: plain Python object via msgpack
    import msgpack
    return msgpack.packb(payload, use_bin_type=True)

def deserialize(type_name: str, data: bytes):
    """Deserialize MessagePack bytes to a tyche_core type or plain dict."""
    fn = getattr(tyche_core, f"deserialize_{type_name.lower()}", None)
    if fn:
        return fn(data)
    import msgpack
    return msgpack.unpackb(data, raw=False)
```

- [ ] **Step 2: Implement logging.py**

```python
# tyche/utils/logging.py
import json
import sys
import time

class StructuredLogger:
    def __init__(self, service_name: str):
        self.service_name = service_name

    def _emit(self, level: str, message: str, **kwargs):
        entry = {
            "timestamp_ns": time.time_ns(),
            "service": self.service_name,
            "level": level,
            "message": message,
            **kwargs,
        }
        print(json.dumps(entry), file=sys.stderr, flush=True)

    def info(self, message: str, **kwargs): self._emit("INFO", message, **kwargs)
    def warn(self, message: str, **kwargs): self._emit("WARN", message, **kwargs)
    def error(self, message: str, **kwargs): self._emit("ERROR", message, **kwargs)
    def debug(self, message: str, **kwargs): self._emit("DEBUG", message, **kwargs)
```

- [ ] **Step 3: Write failing config tests**

```python
# tests/unit/test_config.py
import pytest
import tomllib
from pathlib import Path

def test_engine_toml_loads():
    from tyche.core.config import EngineConfig
    cfg = EngineConfig.from_file("config/engine.toml")
    assert cfg.nexus.address == "tcp://127.0.0.1:5555"
    assert cfg.nexus.cpu_core == 0
    assert cfg.bus.xsub_address == "tcp://127.0.0.1:5556"
    assert cfg.bus.xpub_address == "tcp://127.0.0.1:5557"

def test_module_config_loads():
    from tyche.core.config import ModuleConfig
    cfg = ModuleConfig.from_file("config/modules/example_strategy.toml")
    assert cfg.service_name == "strategy.example"
    assert cfg.cpu_core == 4
    assert "EQUITY.NYSE.AAPL.QUOTE" in cfg.subscriptions
```

Run: `pytest tests/unit/test_config.py -v`
Expected: FAIL

- [ ] **Step 4: Implement config.py**

```python
# tyche/core/config.py
import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class NexusConfig:
    address: str
    cpu_core: int
    heartbeat_interval_ms: int = 1000
    missed_heartbeat_limit: int = 3
    registration_timeout_ms: int = 500
    registration_max_retries: int = 20
    restart_policy: str = "alert-only"


@dataclass
class BusConfig:
    xsub_address: str
    xpub_address: str
    cpu_core: int
    sndhwm: int = 10000


@dataclass
class EngineConfig:
    nexus: NexusConfig
    bus: BusConfig

    @classmethod
    def from_file(cls, path: str) -> "EngineConfig":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        nexus = NexusConfig(**data["nexus"])
        bus = BusConfig(**data["bus"])
        return cls(nexus=nexus, bus=bus)


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
        return cls(
            service_name=m["service_name"],
            cpu_core=m["cpu_core"],
            subscriptions=m.get("subscriptions", []),
        )
```

- [ ] **Step 5: Run config tests**

Run: `pytest tests/unit/test_config.py -v`
Expected: 2 tests pass

- [ ] **Step 6: Commit**

```bash
git add tyche/utils/serialization.py tyche/utils/logging.py tyche/core/config.py tests/unit/test_config.py
git commit -m "feat(python): add serialization helpers, structured logger, and TOML config loaders"
```

---

## Task 11: Python Clock

**Files:**
- Modify: `tyche/core/clock.py`
- Test: `tests/unit/test_clock.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/unit/test_clock.py
import time

def test_live_clock_returns_nanoseconds():
    from tyche.core.clock import LiveClock
    c = LiveClock()
    t = c.now_ns()
    assert t > 0
    assert t > 1_700_000_000_000_000_000  # after 2023

def test_live_clock_is_monotonic():
    from tyche.core.clock import LiveClock
    c = LiveClock()
    t1 = c.now_ns()
    t2 = c.now_ns()
    assert t2 >= t1

def test_sim_clock_starts_at_given_time():
    from tyche.core.clock import SimClock
    c = SimClock(start_ns=1_000_000)
    assert c.now_ns() == 1_000_000

def test_sim_clock_can_advance():
    from tyche.core.clock import SimClock
    c = SimClock(start_ns=0)
    c.advance(500)
    assert c.now_ns() == 500
```

Run: `pytest tests/unit/test_clock.py -v`
Expected: 4 FAILs

- [ ] **Step 2: Implement clock.py**

```python
# tyche/core/clock.py
import time
from abc import ABC, abstractmethod


class Clock(ABC):
    @abstractmethod
    def now_ns(self) -> int:
        """Return current time as nanoseconds since Unix epoch."""
        ...


class LiveClock(Clock):
    def now_ns(self) -> int:
        return time.time_ns()


class SimClock(Clock):
    def __init__(self, start_ns: int = 0):
        self._ns = start_ns

    def now_ns(self) -> int:
        return self._ns

    def advance(self, delta_ns: int) -> None:
        self._ns += delta_ns

    def set(self, ns: int) -> None:
        self._ns = ns
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/unit/test_clock.py -v`
Expected: 4 tests pass

- [ ] **Step 4: Commit**

```bash
git add tyche/core/clock.py tests/unit/test_clock.py
git commit -m "feat(python): add LiveClock and SimClock"
```

---

## Task 12: Python Bus Process

**Files:**
- Modify: `tyche/core/bus.py`
- Test: `tests/integration/test_bus_pubsub.py`

- [ ] **Step 1: Write failing integration test**

```python
# tests/integration/test_bus_pubsub.py
import time
import threading
import zmq
import pytest

BUS_XSUB = "tcp://127.0.0.1:15556"  # offset ports for tests
BUS_XPUB = "tcp://127.0.0.1:15557"

@pytest.fixture
def bus_process():
    from tyche.core.bus import Bus
    b = Bus(xsub_address=BUS_XSUB, xpub_address=BUS_XPUB, cpu_core=None)
    t = threading.Thread(target=b.run, daemon=True)
    t.start()
    time.sleep(0.1)  # let proxy start
    yield b
    b.stop()

def test_message_flows_pub_to_sub(bus_process):
    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    pub.connect(BUS_XSUB)
    sub = ctx.socket(zmq.SUB)
    sub.connect(BUS_XPUB)
    sub.setsockopt_string(zmq.SUBSCRIBE, "TEST.TOPIC")
    time.sleep(0.05)  # subscription propagation delay

    pub.send_multipart([b"TEST.TOPIC", b"\x00" * 8, b"hello"])
    sub.setsockopt(zmq.RCVTIMEO, 1000)
    frames = sub.recv_multipart()
    assert frames[0] == b"TEST.TOPIC"
    assert frames[2] == b"hello"
    pub.close(); sub.close(); ctx.term()

def test_prefix_subscription_receives_matching_topics(bus_process):
    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    pub.connect(BUS_XSUB)
    sub = ctx.socket(zmq.SUB)
    sub.connect(BUS_XPUB)
    sub.setsockopt_string(zmq.SUBSCRIBE, "EQUITY.NYSE")
    time.sleep(0.05)

    pub.send_multipart([b"EQUITY.NYSE.AAPL.TICK", b"\x00" * 8, b"data"])
    sub.setsockopt(zmq.RCVTIMEO, 1000)
    frames = sub.recv_multipart()
    assert frames[0] == b"EQUITY.NYSE.AAPL.TICK"
    pub.close(); sub.close(); ctx.term()
```

Run: `pytest tests/integration/test_bus_pubsub.py -v`
Expected: FAIL — `Bus` not implemented

- [ ] **Step 2: Implement bus.py**

```python
# tyche/core/bus.py
import threading
import zmq
from tyche.utils.logging import StructuredLogger


class Bus:
    """XPUB/XSUB proxy — the TycheEngine data highway."""

    def __init__(self, xsub_address: str, xpub_address: str, cpu_core: int | None = 1):
        self.xsub_address = xsub_address
        self.xpub_address = xpub_address
        self.cpu_core = cpu_core
        self._stop_event = threading.Event()
        self._log = StructuredLogger("bus")
        self._ctx: zmq.Context | None = None

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

    def run(self):
        self._pin_cpu()
        self._ctx = zmq.Context()
        xsub = self._ctx.socket(zmq.XSUB)
        xsub.bind(self.xsub_address)
        xpub = self._ctx.socket(zmq.XPUB)
        xpub.bind(self.xpub_address)
        xpub.setsockopt(zmq.SNDHWM, 10000)
        self._log.info("Bus started", xsub=self.xsub_address, xpub=self.xpub_address)
        try:
            # Run proxy until stop socket receives signal
            stop_addr = "inproc://bus-stop"
            stopper = self._ctx.socket(zmq.PAIR)
            stopper.bind(stop_addr)
            self._stopper_addr = stop_addr
            zmq.proxy_steerable(xsub, xpub, None, stopper)
        except zmq.ZMQError:
            pass
        finally:
            xsub.close(); xpub.close()
            self._ctx.term()
            self._log.info("Bus stopped")

    def stop(self):
        if self._ctx:
            try:
                ctrl = self._ctx.socket(zmq.PAIR)
                ctrl.connect(self._stopper_addr)
                ctrl.send(b"TERMINATE")
                ctrl.close()
            except Exception:
                pass
```

- [ ] **Step 3: Run integration tests**

Run: `pytest tests/integration/test_bus_pubsub.py -v`
Expected: 2 tests pass

- [ ] **Step 4: Commit**

```bash
git add tyche/core/bus.py tests/integration/test_bus_pubsub.py
git commit -m "feat(python): add Bus XPUB/XSUB proxy process with CPU pinning and steerable stop"
```

---

## Task 13: Python Nexus Process

**Files:**
- Modify: `tyche/core/nexus.py`
- Test: `tests/integration/test_nexus_lifecycle.py`

- [ ] **Step 1: Write failing integration tests**

```python
# tests/integration/test_nexus_lifecycle.py
import time
import threading
import zmq
import struct
import pytest

NEXUS_ADDR = "tcp://127.0.0.1:15555"
PROTOCOL = "TYCHE"

def send_ready(sock, service_name: str, cpu_core: int, correlation_id: int):
    sock.send_multipart([
        PROTOCOL.encode(), b"READY",
        str(correlation_id).encode(),
        service_name.encode(),
        str(cpu_core).encode(),
    ])

def recv_frame(sock, timeout_ms=2000):
    sock.setsockopt(zmq.RCVTIMEO, timeout_ms)
    return sock.recv_multipart()

@pytest.fixture
def nexus_process():
    from tyche.core.nexus import Nexus
    n = Nexus(address=NEXUS_ADDR, cpu_core=None)
    t = threading.Thread(target=n.run, daemon=True)
    t.start()
    time.sleep(0.1)
    yield n
    n.stop()

def test_module_receives_ready_ack(nexus_process):
    ctx = zmq.Context()
    sock = ctx.socket(zmq.DEALER)
    sock.setsockopt(zmq.IDENTITY, b"test-module-1")
    sock.connect(NEXUS_ADDR)
    send_ready(sock, "test.service", 4, correlation_id=1)
    frames = recv_frame(sock)
    assert b"READY_ACK" in frames
    assert b"1" in frames  # correlation_id echoed
    sock.close(); ctx.term()

def test_unknown_module_not_in_registry_before_ready(nexus_process):
    from tyche.core.nexus import Nexus
    assert "ghost.service" not in nexus_process.registry

def test_module_appears_in_registry_after_ready(nexus_process):
    ctx = zmq.Context()
    sock = ctx.socket(zmq.DEALER)
    sock.setsockopt(zmq.IDENTITY, b"reg-test-module")
    sock.connect(NEXUS_ADDR)
    send_ready(sock, "reg.service", 5, correlation_id=42)
    recv_frame(sock)  # consume ACK
    time.sleep(0.05)
    assert "reg.service" in nexus_process.registry
    sock.close(); ctx.term()
```

Run: `pytest tests/integration/test_nexus_lifecycle.py -v`
Expected: FAIL

- [ ] **Step 2: Implement nexus.py**

```python
# tyche/core/nexus.py
import time
import threading
import zmq
from tyche.utils.logging import StructuredLogger


PROTOCOL = b"TYCHE"

class ModuleDescriptor:
    def __init__(self, service_name: str, identity: bytes, cpu_core: int):
        self.service_name = service_name
        self.identity = identity
        self.cpu_core = cpu_core
        self.last_heartbeat_ns = time.time_ns()
        self.status = "REGISTERED"


class Nexus:
    """ROUTER/DEALER control hub — module lifecycle manager."""

    def __init__(self, address: str, cpu_core: int | None = 0,
                 heartbeat_interval_ms: int = 1000, missed_hb_limit: int = 3):
        self.address = address
        self.cpu_core = cpu_core
        self.heartbeat_interval_ms = heartbeat_interval_ms
        self.missed_hb_limit = missed_hb_limit
        self.registry: dict[str, ModuleDescriptor] = {}
        self._stop_event = threading.Event()
        self._log = StructuredLogger("nexus")

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

    def run(self):
        self._pin_cpu()
        ctx = zmq.Context()
        router = ctx.socket(zmq.ROUTER)
        router.bind(self.address)
        poller = zmq.Poller()
        poller.register(router, zmq.POLLIN)
        self._log.info("Nexus started", address=self.address)

        while not self._stop_event.is_set():
            events = dict(poller.poll(timeout=500))
            if router in events:
                frames = router.recv_multipart()
                self._handle(router, frames)
            self._check_heartbeats()

        router.close(); ctx.term()
        self._log.info("Nexus stopped")

    def _handle(self, router, frames):
        # frames: [identity, protocol, verb, ...args]
        if len(frames) < 3:
            return
        identity, protocol, verb = frames[0], frames[1], frames[2]
        if protocol != PROTOCOL:
            return

        if verb == b"READY":
            correlation_id = frames[3].decode() if len(frames) > 3 else "0"
            service_name = frames[4].decode() if len(frames) > 4 else "unknown"
            cpu_core = int(frames[5].decode()) if len(frames) > 5 else 0
            self.registry[service_name] = ModuleDescriptor(service_name, identity, cpu_core)
            self._log.info("Module registered", service=service_name, cpu_core=cpu_core)
            router.send_multipart([identity, PROTOCOL, b"READY_ACK",
                                   correlation_id.encode(),
                                   str(time.time_ns()).encode()])

        elif verb == b"HB":
            for desc in self.registry.values():
                if desc.identity == identity:
                    desc.last_heartbeat_ns = time.time_ns()
                    break

        elif verb == b"DISCO":
            for name, desc in list(self.registry.items()):
                if desc.identity == identity:
                    del self.registry[name]
                    self._log.info("Module disconnected", service=name)
                    break

    def _check_heartbeats(self):
        now = time.time_ns()
        deadline_ns = self.heartbeat_interval_ms * 1_000_000 * self.missed_hb_limit
        dead = [name for name, d in self.registry.items()
                if (now - d.last_heartbeat_ns) > deadline_ns]
        for name in dead:
            self._log.warn("Module declared dead (HB timeout)", service=name)
            self.registry[name].status = "DEAD"

    def stop(self):
        self._stop_event.set()
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/integration/test_nexus_lifecycle.py -v`
Expected: 3 tests pass

- [ ] **Step 4: Commit**

```bash
git add tyche/core/nexus.py tests/integration/test_nexus_lifecycle.py
git commit -m "feat(python): add Nexus ROUTER/DEALER lifecycle broker with READY_ACK and heartbeat monitoring"
```

---

## Task 14: Python Module Base Class

**Files:**
- Modify: `tyche/core/module.py`
- Test: `tests/integration/test_module_e2e.py`

- [ ] **Step 1: Write failing integration test**

```python
# tests/integration/test_module_e2e.py
import time
import threading
import zmq
import pytest

NEXUS_ADDR = "tcp://127.0.0.1:25555"
BUS_XSUB   = "tcp://127.0.0.1:25556"
BUS_XPUB   = "tcp://127.0.0.1:25557"

@pytest.fixture
def engine():
    from tyche.core.nexus import Nexus
    from tyche.core.bus import Bus
    nexus = Nexus(address=NEXUS_ADDR, cpu_core=None)
    bus   = Bus(xsub_address=BUS_XSUB, xpub_address=BUS_XPUB, cpu_core=None)
    nt = threading.Thread(target=nexus.run, daemon=True)
    bt = threading.Thread(target=bus.run, daemon=True)
    nt.start(); bt.start()
    time.sleep(0.1)
    yield nexus, bus
    nexus.stop(); bus.stop()

def test_module_registers_with_nexus(engine):
    from tyche.core.module import Module

    class TestMod(Module):
        service_name = "test.mod"
        cpu_core = None

        def on_start(self): self.started = True

    m = TestMod(nexus_address=NEXUS_ADDR, bus_xsub=BUS_XSUB, bus_xpub=BUS_XPUB)
    t = threading.Thread(target=m.run, daemon=True)
    t.start()
    time.sleep(0.3)
    nexus, _ = engine
    assert "test.mod" in nexus.registry
    m.stop()

def test_module_receives_published_message(engine):
    from tyche.core.module import Module

    received = []

    class ListenerMod(Module):
        service_name = "test.listener"
        cpu_core = None

        def on_start(self):
            self.subscribe("TEST.DATA.ITEM")

        def on_raw(self, topic: str, payload: bytes):
            received.append((topic, payload))

    m = ListenerMod(nexus_address=NEXUS_ADDR, bus_xsub=BUS_XSUB, bus_xpub=BUS_XPUB)
    t = threading.Thread(target=m.run, daemon=True)
    t.start()
    time.sleep(0.2)

    # external publisher
    ctx = zmq.Context()
    pub = ctx.socket(zmq.PUB)
    pub.connect(BUS_XSUB)
    time.sleep(0.05)
    pub.send_multipart([b"TEST.DATA.ITEM", (0).to_bytes(8, 'big'), b"payload123"])
    time.sleep(0.2)

    assert any(t == b"TEST.DATA.ITEM" for t, _ in received)
    pub.close(); ctx.term(); m.stop()
```

Run: `pytest tests/integration/test_module_e2e.py -v`
Expected: FAIL

- [ ] **Step 2: Implement module.py**

```python
# tyche/core/module.py
import time
import threading
import zmq
from abc import ABC
from tyche.utils.logging import StructuredLogger
from tyche.utils.topics import TopicValidator


PROTOCOL = b"TYCHE"
_NEXUS_REGISTRATION_TIMEOUT_MS = 500
_NEXUS_MAX_RETRIES = 20


class Module(ABC):
    """Base class for all TycheEngine modules."""

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

    # --- Lifecycle hooks (override in subclass) ---
    def on_start(self): pass
    def on_stop(self): pass
    def on_reconfigure(self, cfg: dict): pass

    # --- Typed data handlers (override to receive data) ---
    def on_tick(self, topic: str, payload: bytes): pass
    def on_quote(self, topic: str, payload: bytes): pass
    def on_trade(self, topic: str, payload: bytes): pass
    def on_bar(self, topic: str, payload: bytes, interval_suffix: str): pass
    def on_order(self, topic: str, payload: bytes): pass
    def on_order_event(self, topic: str, payload: bytes): pass
    def on_ack(self, topic: str, payload: bytes): pass
    def on_position(self, topic: str, payload: bytes): pass
    def on_risk(self, topic: str, payload: bytes): pass
    def on_model(self, topic: str, payload: bytes): pass
    def on_raw(self, topic: str, payload: bytes): pass  # fallback for unrecognised topics

    def on_command(self, command: str, payload: dict) -> dict:
        return {"status": "OK"}

    # --- Publish ---
    def publish(self, topic: str, payload) -> None:
        TopicValidator.validate(topic)
        if self._pub_sock is None:
            raise RuntimeError("Module not started")
        ts = time.time_ns().to_bytes(8, 'big')
        if isinstance(payload, bytes):
            raw = payload
        else:
            import msgpack
            raw = msgpack.packb(payload, use_bin_type=True)
        self._pub_sock.send_multipart([topic.encode(), ts, raw])

    # --- Subscriptions ---
    def subscribe(self, topic: str) -> None:
        TopicValidator.validate(topic)
        if self._sub_sock:
            self._sub_sock.setsockopt_string(zmq.SUBSCRIBE, topic)

    def unsubscribe(self, topic: str) -> None:
        if self._sub_sock:
            self._sub_sock.setsockopt_string(zmq.UNSUBSCRIBE, topic)

    # --- Stop ---
    def stop(self):
        self._stop_event.set()

    # --- Run loop ---
    def run(self):
        self._pin_cpu()
        self._ctx = zmq.Context()

        # Nexus DEALER socket
        dealer = self._ctx.socket(zmq.DEALER)
        dealer.setsockopt_string(zmq.IDENTITY, self.service_name)
        dealer.connect(self._nexus_address)

        # Bus PUB socket
        self._pub_sock = self._ctx.socket(zmq.PUB)
        self._pub_sock.connect(self._bus_xsub)

        # Bus SUB socket
        self._sub_sock = self._ctx.socket(zmq.SUB)
        self._sub_sock.connect(self._bus_xpub)

        # Register with Nexus
        self._register(dealer)

        self.on_start()

        poller = zmq.Poller()
        poller.register(dealer, zmq.POLLIN)
        poller.register(self._sub_sock, zmq.POLLIN)

        next_hb = time.time() + 1.0

        while not self._stop_event.is_set():
            events = dict(poller.poll(timeout=200))

            if dealer in events:
                self._handle_nexus(dealer, dealer.recv_multipart())

            if self._sub_sock in events:
                frames = self._sub_sock.recv_multipart()
                if len(frames) >= 3:
                    topic = frames[0].decode()
                    payload = frames[2]
                    self._dispatch(topic, payload)

            if time.time() >= next_hb:
                dealer.send_multipart([PROTOCOL, b"HB",
                                       str(time.time_ns()).encode()])
                next_hb = time.time() + 1.0

        self.on_stop()
        dealer.send_multipart([PROTOCOL, b"DISCO", b"shutdown"])
        dealer.close()
        self._pub_sock.close()
        self._sub_sock.close()
        self._ctx.term()

    def _register(self, dealer):
        for attempt in range(_NEXUS_MAX_RETRIES):
            self._correlation_id += 1
            dealer.send_multipart([
                PROTOCOL, b"READY",
                str(self._correlation_id).encode(),
                self.service_name.encode(),
                str(self.cpu_core or 0).encode(),
            ])
            poller = zmq.Poller()
            poller.register(dealer, zmq.POLLIN)
            events = dict(poller.poll(timeout=_NEXUS_REGISTRATION_TIMEOUT_MS))
            if dealer in events:
                frames = dealer.recv_multipart()
                if len(frames) >= 3 and frames[1] == b"READY_ACK":
                    self._log.info("Registered with Nexus", attempt=attempt + 1)
                    return
        raise RuntimeError(f"Failed to register '{self.service_name}' with Nexus after {_NEXUS_MAX_RETRIES} retries")

    def _handle_nexus(self, dealer, frames):
        if len(frames) < 2:
            return
        verb = frames[1]
        if verb == b"CMD" and len(frames) >= 4:
            command = frames[2].decode()
            import msgpack
            payload = msgpack.unpackb(frames[3], raw=False) if frames[3] else {}
            result = self.on_command(command, payload)
            corr = frames[3] if len(frames) > 4 else b"0"
            dealer.send_multipart([PROTOCOL, b"REPLY", corr,
                                   b"OK", msgpack.packb(result)])

    def _dispatch(self, topic: str, payload: bytes):
        parts = topic.split(".")
        if len(parts) < 3:
            self.on_raw(topic, payload)
            return
        dtype = parts[-1]
        handlers = {
            "TICK": self.on_tick, "QUOTE": self.on_quote, "TRADE": self.on_trade,
            "ORDER": self.on_order, "ORDER_EVENT": self.on_order_event,
            "ACK": self.on_ack, "POSITION": self.on_position,
            "RISK": self.on_risk, "MODEL": self.on_model,
        }
        if dtype == "BAR" and len(parts) >= 5:
            self.on_bar(topic, payload, parts[-1])
        elif dtype in handlers:
            handlers[dtype](topic, payload)
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
Expected: 2 tests pass

- [ ] **Step 4: Run full test suite**

Run: `make test`
Expected: all Rust tests pass, all Python tests pass, no errors

- [ ] **Step 5: Commit**

```bash
git add tyche/core/module.py tests/integration/test_module_e2e.py
git commit -m "feat(python): add Module base class with run loop, typed handlers, Nexus registration, and Bus pub/sub"
```

---

## Task 15: Final Validation + Docs

**Files:**
- Create: `docs/impl/core_engine_implement_v1.md`

- [ ] **Step 1: Run full test suite from clean build**

```bash
make clean
make test
```

Expected output (approximate):
```
running 15 tests  ← Rust unit tests
test enums::tests::... ok
test instrument::tests::... ok
...
15 passed

========================= 20 passed in N.Ns =====  ← Python tests
```

- [ ] **Step 2: Verify maturin build produces importable wheel**

```bash
maturin build --release
python3 -c "
import tyche_core
from tyche.core.config import EngineConfig
from tyche.core.clock import LiveClock
from tyche.utils.topics import TopicBuilder
from tyche.model.enums import BarInterval
print('All imports OK')
print('Bar M5 suffix:', BarInterval.M5.topic_suffix)
print('Topic:', TopicBuilder.bar('EQUITY', 'NYSE', 'AAPL', BarInterval.M5))
print('Clock:', LiveClock().now_ns())
"
```

Expected:
```
All imports OK
Bar M5 suffix: M5
Topic: EQUITY.NYSE.AAPL.BAR.M5
Clock: <nanosecond timestamp>
```

- [ ] **Step 3: Write implementation log**

Create `docs/impl/core_engine_implement_v1.md` documenting:
- Date completed
- What was built (15 tasks)
- Any deviations from spec and why
- Known limitations for subsequent sub-projects

- [ ] **Step 4: Final commit**

```bash
git add docs/impl/core_engine_implement_v1.md
git commit -m "docs: add core engine implementation log v1"
```

---

*Total: 15 tasks, ~75 steps. Rust unit tests: ~15. Python unit tests: ~20. Integration tests: ~7.*
