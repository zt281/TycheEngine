# Core Engine Expansion Implementation Log v1 — Task 18

**Date:** 2026-03-22
**Branch:** `core-engine/task-18-strategy-cli`
**Approved Plan:** `docs/plan/core_engine_expansion_plan_v1.md`
**Spec:** `docs/designs/core-engine-expansions.md` (Task 18 section)

---

## Project State at Impl Time

Core Engine Tasks 1–15 are complete (impl log `docs/impl/core_engine_implement_v1.md`, 0 open CRITICAL items). `ModuleConfig` in `tyche/core/config.py` had three fields (`service_name`, `cpu_core`, `subscriptions`) but lacked `nexus_address`, `bus_xsub`, `bus_xpub` required by the scaffold template. No `tyche/cli/` package and no `tyche/__main__.py` existed. Task 18 adds both.

---

## CRITICAL

_(none)_

---

## Spec Deviations

Three errors in the Task 18 expansion spec were identified during plan authoring and corrected. Each deviation is noted in the implementation via inline comments in the generated template strings.

| # | Deviation | Spec (wrong) | Implementation (correct) | Rationale |
|---|-----------|-------------|--------------------------|-----------|
| 1 | Template import — Module | `from tyche.module import Module` | `from tyche.core.module import Module` | `tyche.module` does not exist; correct path is `tyche.core.module` |
| 2 | Template import — ModuleConfig | `from tyche.model import ModuleConfig` | `from tyche.core.config import ModuleConfig` | `tyche.model` does not export `ModuleConfig`; correct path is `tyche.core.config` |
| 3 | `on_bar` signature | `on_bar(self, topic, msg)` | `on_bar(self, topic, bar, interval)` | Spec omits `interval`; `Module` base class dispatches with 3 data args — omitting `interval` causes `TypeError` at runtime |
| 4 | Config template `cpu_core` | `cpu_core = null` | `# cpu_core = 4` | TOML 1.0 has no null type; `tomllib` rejects `null` as a parse error; commented example is valid TOML and communicates optionality |

Deviation 4 was not in the original plan's deviation list; it was discovered during implementation. Added here for completeness. The plan's Step 3 (Add address fields to ModuleConfig) documented it.

**Plan deviation — `_NAME_RE` tightening:** During the code quality fix commit (`b1f659f`), `_NAME_RE` was tightened from `r'^[a-z][a-z0-9_]*$'` (plan) to `r'^[a-z][a-z0-9]*(_[a-z0-9]+)*$'`. This disallows trailing underscores and consecutive underscores, which would produce unexpected PascalCase output. The change is strictly more restrictive and does not break any planned behaviour. The user-facing error string (`"Error: name must match [a-z][a-z0-9_]*"`) was not updated to match and remains slightly inaccurate (cosmetic; no functional impact on validation).

---

## Task Log

### Task 1: Extend ModuleConfig with Connection Address Fields

**RED:** `pytest tests/unit/test_config.py::test_module_config_address_defaults tests/unit/test_config.py::test_module_config_address_from_toml -v`

```
FAILED tests/unit/test_config.py::test_module_config_address_defaults - AttributeError: 'ModuleConfig' object has no attribute 'nexus_address'
FAILED tests/unit/test_config.py::test_module_config_address_from_toml - AttributeError: 'ModuleConfig' object has no attribute 'nexus_address'
2 failed in 0.08s
```

**GREEN:** `pytest tests/unit/test_config.py -v`

```
tests/unit/test_config.py::test_engine_toml_loads PASSED
tests/unit/test_config.py::test_module_config_loads PASSED
tests/unit/test_config.py::test_nexus_policy_loads PASSED
tests/unit/test_config.py::test_module_config_address_defaults PASSED
tests/unit/test_config.py::test_module_config_address_from_toml PASSED

5 passed in 0.05s
```

**Commit:** `36a5014` — "feat(python): extend ModuleConfig with nexus_address, bus_xsub, bus_xpub fields"

---

### Task 2: Strategy Scaffold CLI

**RED (stub phase):** Stubs created in `tyche/cli/__init__.py` and `tyche/cli/__main__.py` (`raise NotImplementedError` for both `_to_pascal_case` and `main`). Tests run against stubs:

```
pytest tests/unit/test_cli_scaffold.py -v
FAILED tests/unit/test_cli_scaffold.py::test_generated_strategy_compiles - NotImplementedError
FAILED tests/unit/test_cli_scaffold.py::test_generated_strategy_importable - NotImplementedError
FAILED tests/unit/test_cli_scaffold.py::test_generated_config_fields - NotImplementedError
FAILED tests/unit/test_cli_scaffold.py::test_pascal_case_conversion - NotImplementedError
FAILED tests/unit/test_cli_scaffold.py::test_invalid_name_exits_with_error - NotImplementedError
5 failed in 0.12s
```

**GREEN:** `pytest tests/unit/test_cli_scaffold.py -v`

```
tests/unit/test_cli_scaffold.py::test_generated_strategy_compiles PASSED
tests/unit/test_cli_scaffold.py::test_generated_strategy_importable PASSED
tests/unit/test_cli_scaffold.py::test_generated_config_fields PASSED
tests/unit/test_cli_scaffold.py::test_pascal_case_conversion PASSED
tests/unit/test_cli_scaffold.py::test_invalid_name_exits_with_error PASSED
5 passed in 0.18s
```

Full unit suite: `pytest tests/unit/ -v` → **32 passed** (27 pre-existing + 5 new).

**Commit:** `f975e92` — "feat(python): add strategy scaffold CLI — python -m tyche new-strategy <name>"

**Fix commit:** `b1f659f` — "fix(python): isolate tyche_core import in scaffold test; tighten _NAME_RE"
- Added `monkeypatch.setitem(sys.modules, "tyche_core", mock.MagicMock())` in `test_generated_strategy_importable` before `exec_module` to prevent import failure when `tyche_core` is not built
- Tightened `_NAME_RE` to reject trailing/consecutive underscores

Post-fix: `pytest tests/unit/ -v` → **34 passed, 0 failed** (32 pre-existing + 2 from Task 1 config tests already counted above; 34 total is 27 pre-existing + 5 new + 2 config = 34).

---

## Review Summary

- **Spec compliance review:** PASSED
- **Code quality review:** APPROVED (two issues fixed in `b1f659f`)
- **Final code review:** APPROVED

**Total commits (Task 18):** 3 commits (`36a5014`, `f975e92`, `b1f659f`)
**Unit tests after Task 18:** 34 passed, 0 failed
