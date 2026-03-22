# Core Engine Expansion — Task 18: Strategy Scaffold CLI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `python -m tyche new-strategy <name>` CLI that generates a ready-to-run strategy scaffold (`.py` file + `.toml` config) in the current working directory.

**Architecture:** Two tasks — (1) extend `ModuleConfig` with address fields so the generated scaffold can construct a `Module` from a single config file; (2) implement `tyche/cli/__main__.py` with name validation, PascalCase conversion, and template generation, plus `tyche/__main__.py` as the user-facing entry point.

**Tech Stack:** Python stdlib only (`argparse`, `os`, `re`, `sys`, `tomllib`, `py_compile`, `importlib`). No external deps added.

**Spec:** `docs/designs/core-engine-expansions.md` — Task 18 section only.

---

## Project State at Plan Time

Core Engine Tasks 1–15 are complete (impl log `docs/impl/core_engine_implement_v1.md`, 0 open CRITICAL items). The source tree is fully populated. `ModuleConfig` in `tyche/core/config.py` has three fields: `service_name`, `cpu_core`, and `subscriptions`. It does **not** yet have `nexus_address`, `bus_xsub`, or `bus_xpub` — those are required by the generated scaffold template so it can instantiate a `Module` from a single config file. No `tyche/cli/` package exists. No `tyche/__main__.py` exists.

---

## Spec Deviations (to be flagged in impl log)

The expansion spec (Task 18) contains three errors that this plan corrects. The impl log must record each as a spec deviation:

1. **Imports in strategy template:** Spec shows `from tyche.module import Module` and `from tyche.model import ModuleConfig`. These paths do not exist in the codebase. Correct paths are `from tyche.core.module import Module` and `from tyche.core.config import ModuleConfig`.

2. **`on_bar` signature:** Spec template shows `on_bar(self, topic, msg)` with two parameters. The `Module` base class calls `on_bar(self, topic, bar, interval)` with three data parameters — omitting `interval` causes a `TypeError` at runtime. Correct signature is `on_bar(self, topic, bar, interval)`.

3. **`cpu_core` in config template:** Spec shows `cpu_core = null`. TOML 1.0 has no null type; Python's `tomllib` rejects `null` as a parse error. The template uses `# cpu_core = 4` (commented example) to communicate the field is optional while remaining valid TOML.

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `tyche/core/config.py` | Modify | Add `nexus_address`, `bus_xsub`, `bus_xpub` fields to `ModuleConfig` |
| `tests/unit/test_config.py` | Modify | Add tests for new `ModuleConfig` address fields |
| `tyche/cli/__init__.py` | Create | Empty package init |
| `tyche/cli/__main__.py` | Create | CLI logic: name validation, PascalCase, template generation |
| `tyche/__main__.py` | Create | Entry point delegating to `tyche.cli` — enables `python -m tyche new-strategy` |
| `tests/unit/test_cli_scaffold.py` | Create | 5 tests: compiles, importable, config fields, PascalCase, invalid name |

---

## Task 1: Extend ModuleConfig with Connection Address Fields

The generated scaffold calls `cfg.nexus_address`, `cfg.bus_xsub`, `cfg.bus_xpub` on a `ModuleConfig` loaded from a single `.toml` file. These fields must exist on `ModuleConfig` before the CLI can generate working code. **This task is a prerequisite for Task 2.**

**Files:**
- Modify: `tyche/core/config.py`
- Modify: `tests/unit/test_config.py`

- [ ] **Step 1: Write failing tests for new ModuleConfig fields**

Add to the end of `tests/unit/test_config.py`:

```python
def test_module_config_address_defaults():
    """When address fields are absent from TOML, ModuleConfig uses localhost defaults."""
    from tyche.core.config import ModuleConfig
    # example_strategy.toml has no address fields — defaults must apply
    cfg = ModuleConfig.from_file(str(_ROOT / "config" / "modules" / "example_strategy.toml"))
    assert cfg.nexus_address == "tcp://localhost:5555"
    assert cfg.bus_xsub == "tcp://localhost:5556"
    assert cfg.bus_xpub == "tcp://localhost:5557"

def test_module_config_address_from_toml(tmp_path):
    """When address fields are present in TOML, ModuleConfig reads them."""
    toml_content = """
[module]
service_name = "test.svc"
nexus_address = "tcp://10.0.0.1:5555"
bus_xsub = "tcp://10.0.0.1:5556"
bus_xpub = "tcp://10.0.0.1:5557"
"""
    cfg_path = tmp_path / "m.toml"
    cfg_path.write_text(toml_content)
    from tyche.core.config import ModuleConfig
    cfg = ModuleConfig.from_file(str(cfg_path))
    assert cfg.nexus_address == "tcp://10.0.0.1:5555"
    assert cfg.bus_xsub == "tcp://10.0.0.1:5556"
    assert cfg.bus_xpub == "tcp://10.0.0.1:5557"
```

- [ ] **Step 2: Run tests to confirm FAIL**

```bash
pytest tests/unit/test_config.py::test_module_config_address_defaults tests/unit/test_config.py::test_module_config_address_from_toml -v
```

Expected: `AttributeError: 'ModuleConfig' object has no attribute 'nexus_address'`

- [ ] **Step 3: Add address fields to ModuleConfig**

Replace the `ModuleConfig` class body in `tyche/core/config.py` (keep the `try/except tomllib` import block and all other classes unchanged):

```python
@dataclass
class ModuleConfig:
    service_name: str
    cpu_core: Optional[int] = None
    subscriptions: list = field(default_factory=list)
    nexus_address: str = "tcp://localhost:5555"
    bus_xsub: str = "tcp://localhost:5556"
    bus_xpub: str = "tcp://localhost:5557"

    @classmethod
    def from_file(cls, path: str) -> "ModuleConfig":
        with open(path, "rb") as f:
            data = tomllib.load(f)
        m = data["module"]
        return cls(
            service_name=m["service_name"],
            cpu_core=m.get("cpu_core"),
            subscriptions=m.get("subscriptions", []),
            nexus_address=m.get("nexus_address", "tcp://localhost:5555"),
            bus_xsub=m.get("bus_xsub", "tcp://localhost:5556"),
            bus_xpub=m.get("bus_xpub", "tcp://localhost:5557"),
        )
```

- [ ] **Step 4: Run tests — confirm GREEN**

```bash
pytest tests/unit/test_config.py -v
```

Expected: 5 tests pass (3 pre-existing + 2 new)

- [ ] **Step 5: Commit**

```bash
git add tyche/core/config.py tests/unit/test_config.py
git commit -m "feat(python): extend ModuleConfig with nexus_address, bus_xsub, bus_xpub fields"
```

---

## Task 2: Strategy Scaffold CLI

**Files:**
- Create: `tyche/cli/__init__.py`
- Create: `tyche/cli/__main__.py`
- Create: `tyche/__main__.py`
- Create: `tests/unit/test_cli_scaffold.py`

- [ ] **Step 1: Write failing CLI tests**

Create `tests/unit/test_cli_scaffold.py`:

```python
# tests/unit/test_cli_scaffold.py
import importlib.util
import py_compile
import sys
import tomllib
from io import StringIO
from unittest import mock


def test_generated_strategy_compiles(tmp_path, monkeypatch):
    """Generated .py file is syntactically valid (passes py_compile)."""
    monkeypatch.chdir(tmp_path)
    from tyche.cli.__main__ import main
    with mock.patch("sys.argv", ["tyche", "new-strategy", "alpha_strat"]):
        main()
    strategy_file = tmp_path / "strategies" / "alpha_strat.py"
    assert strategy_file.exists(), f"Expected {strategy_file} to be created"
    py_compile.compile(str(strategy_file), doraise=True)


def test_generated_strategy_importable(tmp_path, monkeypatch):
    """Generated .py imports cleanly and contains the correct PascalCase class."""
    monkeypatch.chdir(tmp_path)
    from tyche.cli.__main__ import main
    with mock.patch("sys.argv", ["tyche", "new-strategy", "my_strat"]):
        main()
    strategy_file = tmp_path / "strategies" / "my_strat.py"
    spec = importlib.util.spec_from_file_location("my_strat", str(strategy_file))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert hasattr(mod, "MyStrat"), "Expected class MyStrat in generated module"


def test_generated_config_fields(tmp_path, monkeypatch):
    """Generated .toml contains all required fields with correct values."""
    monkeypatch.chdir(tmp_path)
    from tyche.cli.__main__ import main
    with mock.patch("sys.argv", ["tyche", "new-strategy", "beta_strat"]):
        main()
    config_file = tmp_path / "config" / "modules" / "beta_strat.toml"
    assert config_file.exists(), f"Expected {config_file} to be created"
    with open(config_file, "rb") as f:
        data = tomllib.load(f)
    m = data["module"]
    assert m["service_name"] == "beta_strat"
    assert m["nexus_address"] == "tcp://localhost:5555"
    assert m["bus_xsub"] == "tcp://localhost:5556"
    assert m["bus_xpub"] == "tcp://localhost:5557"
    assert m["metrics_enabled"] == False


def test_pascal_case_conversion():
    """_to_pascal_case converts snake_case names to PascalCase correctly."""
    from tyche.cli.__main__ import _to_pascal_case
    assert _to_pascal_case("alpha") == "Alpha"
    assert _to_pascal_case("my_strat") == "MyStrat"
    assert _to_pascal_case("my_strategy_name") == "MyStrategyName"
    assert _to_pascal_case("a_b_c") == "ABC"


def test_invalid_name_exits_with_error(tmp_path, monkeypatch, capsys):
    """Invalid name prints error to stderr and exits with code 1."""
    import pytest
    monkeypatch.chdir(tmp_path)
    from tyche.cli.__main__ import main
    with mock.patch("sys.argv", ["tyche", "new-strategy", "Bad-Name"]):
        with pytest.raises(SystemExit) as exc_info:
            main()
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "Error: name must match [a-z][a-z0-9_]*" in captured.err
```

- [ ] **Step 2: Create minimal stubs so RED fails on NotImplementedError (not ImportError)**

Per TDD rules, the RED step must fail with an assertion/NotImplementedError, not an import error from a missing stub. Create the package skeleton first:

Create `tyche/cli/__init__.py`:

```python
# tyche/cli/__init__.py
```

Create `tyche/cli/__main__.py` as a minimal stub:

```python
# tyche/cli/__main__.py — stub (replaced in Step 4)
def _to_pascal_case(name: str) -> str:
    raise NotImplementedError

def main() -> None:
    raise NotImplementedError
```

- [ ] **Step 3: Run tests to confirm FAIL (RED)**

```bash
pytest tests/unit/test_cli_scaffold.py -v
```

Expected: all 5 tests fail with `NotImplementedError` — confirming the stubs are found but unimplemented

- [ ] **Step 4: Implement tyche/cli/__main__.py**

Replace the stub with the full implementation:

Create `tyche/cli/__main__.py`:

```python
# tyche/cli/__main__.py
import argparse
import os
import re
import sys

_NAME_RE = re.compile(r'^[a-z][a-z0-9_]*$')

# NOTE spec deviation: imports corrected to actual package paths.
# Spec shows `from tyche.module import Module` / `from tyche.model import ModuleConfig`
# which do not exist. Correct paths are tyche.core.module and tyche.core.config.
_STRATEGY_TEMPLATE = '''\
from tyche.core.module import Module
from tyche.core.config import ModuleConfig


class {class_name}(Module):
    """Auto-generated strategy scaffold."""

    def on_start(self):
        pass  # subscribe to topics here

    def on_stop(self):
        pass

    def on_quote(self, topic, quote):
        pass

    # NOTE spec deviation: on_bar signature corrected to match Module base class.
    # Spec shows on_bar(self, topic, msg) — omitting interval causes TypeError at runtime.
    def on_bar(self, topic, bar, interval):
        pass


if __name__ == "__main__":
    cfg = ModuleConfig.from_file("config/modules/{name}.toml")
    {class_name}(cfg.nexus_address, cfg.bus_xsub, cfg.bus_xpub).run()
'''

# NOTE spec deviation: spec shows `cpu_core = null` which is invalid TOML (no null type).
# Using commented example `# cpu_core = 4` instead — valid TOML, communicates optionality.
_CONFIG_TEMPLATE = '''\
[module]
service_name = "{name}"
nexus_address = "tcp://localhost:5555"
bus_xsub = "tcp://localhost:5556"
bus_xpub = "tcp://localhost:5557"
# cpu_core = 4
metrics_enabled = false
'''


def _to_pascal_case(name: str) -> str:
    return "".join(word.capitalize() for word in name.split("_"))


def main() -> None:
    parser = argparse.ArgumentParser(prog="tyche")
    subparsers = parser.add_subparsers(dest="command")
    ns_parser = subparsers.add_parser("new-strategy", help="Generate a strategy scaffold")
    ns_parser.add_argument("name", help="Strategy name — must match [a-z][a-z0-9_]*")
    args = parser.parse_args()

    if args.command != "new-strategy":
        parser.print_help()
        sys.exit(1)

    name = args.name
    if not _NAME_RE.match(name):
        print("Error: name must match [a-z][a-z0-9_]*", file=sys.stderr)
        sys.exit(1)

    class_name = _to_pascal_case(name)

    os.makedirs("strategies", exist_ok=True)
    strategy_path = os.path.join("strategies", f"{name}.py")
    with open(strategy_path, "w") as f:
        f.write(_STRATEGY_TEMPLATE.format(name=name, class_name=class_name))

    os.makedirs(os.path.join("config", "modules"), exist_ok=True)
    config_path = os.path.join("config", "modules", f"{name}.toml")
    with open(config_path, "w") as f:
        f.write(_CONFIG_TEMPLATE.format(name=name))

    print(f"Created {strategy_path}")
    print(f"Created {config_path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Create tyche/__main__.py entry point**

Create `tyche/__main__.py`:

```python
# tyche/__main__.py
from tyche.cli.__main__ import main

main()
```

This makes `python -m tyche new-strategy <name>` work in addition to `python -m tyche.cli new-strategy <name>`.

- [ ] **Step 6: Run tests — confirm GREEN**

```bash
pytest tests/unit/test_cli_scaffold.py -v
```

Expected: 5 tests pass

- [ ] **Step 7: Run full unit suite — confirm no regressions**

```bash
pytest tests/unit/ -v
```

Expected: 32 tests pass (27 pre-existing + 5 new)

- [ ] **Step 8: Smoke test the CLI end-to-end**

Run from the project root (files land in a temp dir to avoid polluting the repo):

```bash
cd /tmp && python -m tyche new-strategy smoke_test && cat strategies/smoke_test.py && cat config/modules/smoke_test.toml && cd -
```

Expected output:
```
Created strategies/smoke_test.py
Created config/modules/smoke_test.toml
[strategy file contents with class SmokeTest]
[config file contents with service_name = "smoke_test"]
```

- [ ] **Step 9: Commit**

```bash
git add tyche/cli/__init__.py tyche/cli/__main__.py tyche/__main__.py tests/unit/test_cli_scaffold.py
git commit -m "feat(python): add strategy scaffold CLI — python -m tyche new-strategy <name>"
```

---

## Spec Deviations — impl log entries required

When writing the impl log, the Implementer must record each of these as spec deviations:

| # | Deviation | Rationale |
|---|-----------|-----------|
| 1 | Template imports use `tyche.core.module` / `tyche.core.config` | Spec paths (`tyche.module`, `tyche.model`) don't exist in the codebase |
| 2 | `on_bar` signature is `(self, topic, bar, interval)` | Spec's `(self, topic, msg)` causes `TypeError` at runtime; corrected to match `Module` base class |
| 3 | Config template uses `# cpu_core = 4` | Spec's `cpu_core = null` is invalid TOML; commented example is valid and communicates optionality |
