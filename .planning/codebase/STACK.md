# Technology Stack

*Generated: 2026-04-21*

## Language & Runtime

| Component | Technology | Version |
|-----------|-----------|---------|
| Language | Python | >=3.9 |
| Build system | Hatchling | (latest) |
| Package format | PEP 621 (`pyproject.toml`) | — |

## Core Dependencies

| Package | Purpose | Version |
|---------|---------|---------|
| `pyzmq` | ZeroMQ bindings for Python | >=25.0.0 |
| `msgpack` | MessagePack serialization | >=1.0.5 |
| `openctp-ctp` | CTP futures trading API bindings | >=6.7.0 (optional, `ctp` extra) |

## Development Dependencies

| Package | Purpose | Version |
|---------|---------|---------|
| `pytest` | Test runner | >=7.4.0 |
| `pytest-asyncio` | Async test support | >=0.21.0 |
| `pytest-timeout` | Test timeout enforcement | >=2.2.0 |
| `pytest-cov` | Coverage reporting | >=4.1.0 |
| `mypy` | Static type checking | >=1.5.0 |
| `ruff` | Linter and formatter | >=0.0.280 |

## Frontend / TUI

| Component | Technology |
|-----------|-----------|
| TUI dashboard | TypeScript / React (in `tui/` directory) |
| Package manager | npm |
| Config | `tui/tsconfig.json`, `tui/package.json` |

## Configuration Files

- `pyproject.toml` — Project metadata, dependencies, tool config (pytest, mypy, ruff, coverage, hatch)
- `.vscode/settings.json` — VS Code workspace settings
- `tui/tsconfig.json` — TypeScript compiler config
- `tui/package.json` — npm dependencies for TUI

## Build & Package

- Wheel build target: `src/tyche` and `src/modules` packages
- Install with CTP support: `pip install -e ".[ctp,dev]"`
