# Core Engine Implementation Log v1

**Date:** 2026-03-21
**Branch:** core-engine/implementation
**Approved Plan:** docs/plan/core_engine_plan_v2.md (commit 521da46)
**Approved Spec:** docs/design/core_engine_design_v3.md

---

## Project State at Impl Time

Source tree was empty (only docs/ and LICENSE). All source files are being created from scratch. The approved plan covers 15 tasks building the Rust crate (tyche-core), PyO3 bindings, Python package (tyche/), Bus, Nexus, Module base class, and full test suite. No prior implementation exists; no CRITICAL items carry over from previous cycles.

---

## CRITICAL

_(none)_

---

## Task Log

### Task 1: Project Scaffold

**RED:** N/A — scaffold task, no test file (all test files are created in their respective task's RED step per the plan).

**GREEN:** Cargo check passes.

**Commit:** 5c34869 — "feat: project scaffold — workspace, pyproject.toml, config, package skeleton"

**Files created:**
- Cargo.toml (workspace)
- tyche-core/Cargo.toml
- tyche-core/src/lib.rs
- tyche-core/src/python.rs (minimal stub)
- tyche-core/src/{enums,instrument,types,clock,serialization,ffi_bridge}.rs (empty stubs)
- pyproject.toml (no python-source key, as required)
- Makefile
- config/engine.toml, config/modules/{nexus,bus,example_strategy}.toml
- tyche/__init__.py, tyche/core/__init__.py, tyche/model/__init__.py, tyche/utils/__init__.py
- 11 Python source stubs

**Verification:** `cargo check --manifest-path tyche-core/Cargo.toml` → 0 errors, 0 warnings

---

<!-- Subsequent tasks will append their RED/GREEN evidence below -->

### Task 2: Rust Enums

**RED:** `cargo test --manifest-path tyche-core/Cargo.toml enums`
Output:
```
error[E0433]: failed to resolve: use of undeclared type `BarInterval`
error[E0433]: failed to resolve: use of undeclared type `BarInterval`
error[E0433]: failed to resolve: use of undeclared type `BarInterval`
error[E0433]: failed to resolve: use of undeclared type `BarInterval`
error[E0433]: failed to resolve: use of undeclared type `BarInterval`
error[E0433]: failed to resolve: use of undeclared type `Side`
error[E0433]: failed to resolve: use of undeclared type `Side`
error[E0433]: failed to resolve: use of undeclared type `ModelKind`
error: could not compile `tyche-core` (lib test) due to 8 previous errors; 1 warning emitted
```

**GREEN:** `cargo test --manifest-path tyche-core/Cargo.toml enums`
Output:
```
running 4 tests
test enums::tests::bar_interval_discriminants_are_stable ... ok
test enums::tests::bar_interval_topic_suffix_matches_variant ... ok
test enums::tests::model_kind_custom_is_255 ... ok
test enums::tests::side_discriminants ... ok

test result: ok. 4 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
```

**Commit:** da881bd — "feat(rust): add BarInterval, ModelKind, Side, OrderType, TIF, AssetClass enums"

---

### Task 3: Rust InstrumentId

**RED:** `cargo test --manifest-path tyche-core/Cargo.toml instrument`
Output:
```
error[E0433]: failed to resolve: use of undeclared type `InstrumentId`
 --> tyche-core\src\instrument.rs:9:18
error[E0433]: failed to resolve: use of undeclared type `InstrumentId`
  --> tyche-core\src\instrument.rs:17:17
error[E0433]: failed to resolve: use of undeclared type `InstrumentId`
  --> tyche-core\src\instrument.rs:18:17
error[E0433]: failed to resolve: use of undeclared type `InstrumentId`
  --> tyche-core\src\instrument.rs:23:18
error[E0433]: failed to resolve: use of undeclared type `InstrumentId`
  --> tyche-core\src\instrument.rs:32:18
error: could not compile `tyche-core` (lib test) due to 5 previous errors; 1 warning emitted
```

**GREEN:** `cargo test --manifest-path tyche-core/Cargo.toml instrument`
Output:
```
running 4 tests
test instrument::tests::all_fields_max_values_fit ... ok
test instrument::tests::invalid_asset_class_bits_return_err ... ok
test instrument::tests::raw_value_is_deterministic ... ok
test instrument::tests::encode_decode_roundtrip ... ok

test result: ok. 4 passed; 0 failed; 0 ignored; 0 measured; 4 filtered out; finished in 0.00s
```

**Commit:** e3d5294 — "feat(rust): add InstrumentId with 64-bit packed fields and safe asset_class decoding"
