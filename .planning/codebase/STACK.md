# Technology Stack

**Analysis Date:** 2026-04-28

## Languages

**Primary:**
- Python 3.9+ - All application code, tests, and tooling

**Secondary:**
- YAML - CI/CD workflows (`.github/workflows/`), Docker Compose (`docker/`)
- JSON - Configuration files for CTP gateway
- Markdown - Documentation (`docs/`, `README.md`)

## Runtime

**Environment:**
- CPython 3.9, 3.10, 3.11, 3.12 (tested in CI matrix)
- Minimum requirement: `>=3.9`

**Package Manager:**
- pip (standard Python packaging)
- Build backend: `hatchling`
- Lockfile: Not present (no `requirements.txt` or `poetry.lock`)

## Frameworks

**Core:**
- ZeroMQ (via `pyzmq>=25.0.0`) - Distributed messaging backbone. All inter-process communication uses ZMQ socket patterns: REQ-ROUTER, XPUB/XSUB, DEALER-ROUTER, PUSH-PULL.
- MessagePack (via `msgpack>=1.0.5`) - Binary serialization for all ZMQ messages. Custom Decimal/Enum encoders in `src/tyche/message.py`.

**Testing:**
- pytest 7.4+ - Test runner
- pytest-asyncio 0.21+ - Async test support
- pytest-timeout 2.2+ - Test timeout enforcement (30s default)
- pytest-cov 4.1+ - Coverage reporting

**Build/Dev:**
- hatchling - PEP 517 build backend for wheel generation
- ruff 0.0.280+ - Linting (E, F, I, W rules; line-length 100)
- mypy 1.5+ - Static type checking (`disallow_untyped_defs=true`)

## Key Dependencies

**Critical (Core Runtime):**
- `pyzmq>=25.0.0` - ZeroMQ Python bindings. Used throughout: `src/tyche/engine.py`, `src/tyche/module.py`, `src/tyche/heartbeat.py`. Core to all IPC.
- `msgpack>=1.0.5` - Message serialization. Used in `src/tyche/message.py` for all event/command encoding.

**Infrastructure (Optional Extras):**
- `openctp-ctp>=6.7.0` - CTP futures trading API bindings. Required for `src/modules/trading/gateway/ctp/`. Imported as `openctp_ctp` (mdapi, tdapi modules).
- `clickhouse-connect>=0.7.0` - ClickHouse database client. Required for `src/modules/trading/persistence/clickhouse_backend.py`.

**Standard Library (Heavy Use):**
- `threading`, `queue` - Engine and module concurrency (`src/tyche/engine.py`, `src/tyche/module.py`)
- `dataclasses` - All model definitions (`src/modules/trading/models/`)
- `decimal.Decimal` - Financial precision throughout trading models
- `enum.Enum` - Type-safe enumerations for trading concepts
- `secrets` - Cryptographic randomness for module IDs and order IDs

## Configuration

**Environment:**
- CTP gateway config loaded from JSON file with env var overrides (`TYCHE_GATEWAY_*` prefix). See `src/modules/trading/gateway/ctp/config.py`.
- Priority: CLI args > environment variables > JSON file > defaults.

**Build:**
- `pyproject.toml` - Single source of truth for project metadata, dependencies, and tool config
- `[tool.pytest.ini_options]` - Test discovery and defaults
- `[tool.mypy]` - Type checking strictness
- `[tool.ruff]` - Linting rules
- `[tool.coverage.run]` - Coverage source paths (`src/tyche`, `src/modules`)

**Docker:**
- `docker/clickhouse-compose.yml` - ClickHouse 24 server for local development/testing

## Platform Requirements

**Development:**
- Python 3.9+
- pip
- Docker + Docker Compose (for ClickHouse local dev)
- CTP SDK (optional, for futures trading gateway)

**Production:**
- Multi-process deployment: TycheEngine broker as one process, each module as separate process
- ZeroMQ TCP transport for cross-machine distribution
- ClickHouse server for persistence (optional, JSONL fallback available)

---

*Stack analysis: 2026-04-28*
