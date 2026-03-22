# Core Engine Expansion v2 — Implementation Log (Task 17: Dispatch Latency Instrumentation)

## Project State at Impl Time

Tasks 1-15 from `core_engine_plan_v2.md` are fully implemented and committed on `main` (latest: `2c2369d`). This implementation log covers the expansion tasks from `core_engine_plan_v3.md` (Task 16 Step 0 prerequisite + Task 17). All five plan tasks are complete and committed in worktree branch `core-engine/task-17-latency`. The full test suite (Rust + Python) passes with zero failures.

## CRITICAL

_(none)_

## Task Log

### Task 1: Prerequisite — Add `clock` Keyword Argument to `Module.__init__`

**Commit:** `dcf709d`

**RED** — Added `test_module_accepts_clock_kwarg` and `test_module_default_clock_is_live` to `tests/unit/test_clock.py`. Tests failed with `TypeError: __init__() got an unexpected keyword argument 'clock'`.

**GREEN** — Added `from tyche.core.clock import LiveClock` import and updated `__init__` signature to `def __init__(self, nexus_address: str, bus_xsub: str, bus_xpub: str, *, clock=None):` with `self._clock = clock if clock is not None else LiveClock()`. 6 clock tests pass.

---

### Task 2: LatencyStats Ring Buffer

**Commit:** `36f052c` (initial), `a2478e2` (quality fix — remove `_count` private access, add docstring)

**RED** — Created `tests/unit/test_latency_stats.py` with 6 tests. Failed with `ModuleNotFoundError: No module named 'tyche.utils.latency'`.

**GREEN** — Created `tyche/utils/latency.py` with `LatencyStats` class: fixed 8 KB `bytearray` ring buffer, `record()` via `struct.pack_into`, `percentile()` with sort and index formula. All 6 tests pass.

---

### Task 3: ModuleConfig.metrics_enabled

**Commit:** `191636a`

**RED** — Added `test_module_config_metrics_enabled_default` and `test_module_config_metrics_enabled_true` to `tests/unit/test_config.py`. Tests failed with `AttributeError: 'ModuleConfig' object has no attribute 'metrics_enabled'`.

**GREEN** — Added `metrics_enabled: bool = False` field and `metrics_enabled=m.get("metrics_enabled", False)` in `from_file()` to `ModuleConfig` in `tyche/core/config.py`. 5 config tests pass.

---

### Task 4: Instrument `Module._dispatch()` + Extend STATUS Response

**Commit:** `ca097d1` (implementation), `b4810b7` (quality fix — capture `me = self.metrics_enabled`, precise type annotation, rename local vars, fix comment, add exception-path comment)

**RED** — Created `tests/unit/test_dispatch_latency.py` with 5 tests. Tests failed with `AttributeError: '_MetricsMod' object has no attribute '_latency'`.

**GREEN** — Added `from tyche.utils.latency import LatencyStats` import, `metrics_enabled: bool = False` class attribute, `self._latency: dict[str, LatencyStats] = {}` in `__init__`, instrumented `_dispatch()` with per-dtype timing gated on `me = self.metrics_enabled`, and extended STATUS branch in `_handle_nexus()`. 42 tests pass.

---

### Task 5: Final Verification

**Rust:** `cargo test --manifest-path tyche-core/Cargo.toml --offline`

```
running 22 tests
test clock::tests::live_clock_is_monotonic ... ok
test clock::tests::live_clock_returns_positive_ns ... ok
test enums::tests::side_discriminants ... ok
test instrument::tests::invalid_asset_class_bits_return_err ... ok
test ffi_bridge::tests::take_twice_second_is_none ... ok
test ffi_bridge::tests::write_then_take_returns_payload ... ok
test clock::tests::sim_clock_advance_increases_time ... ok
test ffi_bridge::tests::take_empty_slot_returns_none ... ok
test ffi_bridge::tests::write_overwrites_previous_slot ... ok
test instrument::tests::all_fields_max_values_fit ... ok
test instrument::tests::encode_decode_roundtrip ... ok
test enums::tests::model_kind_custom_is_255 ... ok
test instrument::tests::raw_value_is_deterministic ... ok
test serialization::tests::quote_serialize_deserialize_roundtrip ... ok
test enums::tests::bar_interval_discriminants_are_stable ... ok
test enums::tests::bar_interval_topic_suffix_matches_variant ... ok
test types::tests::bar_embeds_interval ... ok
test types::tests::model_param_capacity ... ok
test types::tests::order_side_and_type ... ok
test types::tests::position_net_qty ... ok
test types::tests::quote_spread ... ok
test types::tests::tick_fields_accessible ... ok

test result: ok. 22 passed; 0 failed; 0 ignored; 0 measured; 0 filtered out; finished in 0.00s
```

**Python:** `python -m pytest tests/unit/ -v`

```
============================= test session starts =============================
platform win32 -- Python 3.9.12, pytest-8.4.2, pluggy-1.6.0
collected 42 items

tests/unit/test_bindings.py::test_pyquote_construction PASSED
tests/unit/test_bindings.py::test_bar_interval_eq_int PASSED
tests/unit/test_bindings.py::test_bar_interval_topic_suffix_property PASSED
tests/unit/test_bindings.py::test_init_ffi_bridge_and_take_pending PASSED
tests/unit/test_bindings.py::test_serialize_deserialize_roundtrip PASSED
tests/unit/test_clock.py::test_live_clock_returns_positive_ns PASSED
tests/unit/test_clock.py::test_live_clock_is_monotonic PASSED
tests/unit/test_clock.py::test_sim_clock_advance_increases_time PASSED
tests/unit/test_clock.py::test_sim_clock_start_ns PASSED
tests/unit/test_clock.py::test_module_accepts_clock_kwarg PASSED
tests/unit/test_clock.py::test_module_default_clock_is_live PASSED
tests/unit/test_config.py::test_engine_toml_loads PASSED
tests/unit/test_config.py::test_module_config_loads PASSED
tests/unit/test_config.py::test_nexus_policy_loads PASSED
tests/unit/test_config.py::test_module_config_metrics_enabled_default PASSED
tests/unit/test_config.py::test_module_config_metrics_enabled_true PASSED
tests/unit/test_dispatch_latency.py::test_dispatch_records_quote_latency PASSED
tests/unit/test_dispatch_latency.py::test_dispatch_records_bar_latency PASSED
tests/unit/test_dispatch_latency.py::test_dispatch_no_timing_for_on_raw PASSED
tests/unit/test_dispatch_latency.py::test_dispatch_no_timing_when_disabled PASSED
tests/unit/test_dispatch_latency.py::test_dispatch_latency_accumulates PASSED
tests/unit/test_latency_stats.py::test_latency_stats_empty_returns_zero PASSED
tests/unit/test_latency_stats.py::test_latency_stats_p_gte_one_raises PASSED
tests/unit/test_latency_stats.py::test_latency_stats_single_sample PASSED
tests/unit/test_latency_stats.py::test_latency_stats_n_samples_sorted PASSED
tests/unit/test_latency_stats.py::test_latency_stats_exactly_1024_samples PASSED
tests/unit/test_latency_stats.py::test_latency_stats_overflow_2048_samples PASSED
tests/unit/test_topics.py::test_normalise_fx_removes_slash PASSED
tests/unit/test_topics.py::test_normalise_option_uses_underscore PASSED
tests/unit/test_topics.py::test_normalise_future_uses_underscore PASSED
tests/unit/test_topics.py::test_build_tick_topic PASSED
tests/unit/test_topics.py::test_build_bar_topic PASSED
tests/unit/test_topics.py::test_build_internal_topic PASSED
tests/unit/test_topics.py::test_invalid_topic_raises PASSED
tests/unit/test_topics.py::test_valid_topic_passes PASSED
tests/unit/test_topics.py::test_topic_with_slash_raises PASSED
tests/unit/test_topics.py::test_suffix_to_bar_interval_roundtrip PASSED
tests/unit/test_topics.py::test_suffix_to_bar_interval_invalid_raises PASSED
tests/unit/test_types.py::test_all_types_importable PASSED
tests/unit/test_types.py::test_quote_spread PASSED
tests/unit/test_types.py::test_bar_interval_suffix PASSED
tests/unit/test_types.py::test_side_equality PASSED

======================== 42 passed, 1 warning in 0.15s ========================
```
