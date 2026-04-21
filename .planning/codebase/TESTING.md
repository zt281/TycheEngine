# Testing

*Generated: 2026-04-21*

## Test Framework

- **Runner:** pytest
- **Async:** pytest-asyncio (auto mode)
- **Timeout:** pytest-timeout (30s default)
- **Coverage:** pytest-cov (targets `src/tyche`, `src/modules`)

## Configuration (`pyproject.toml`)

```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
python_files = ["test_*.py"]
python_classes = ["Test*"]
python_functions = ["test_*"]
addopts = "-v --tb=short"
asyncio_mode = "auto"
timeout = 30
```

No `__init__.py` in `tests/` or subdirectories — pytest handles discovery natively.

## Test Categories

| Category | Location | Count | Notes |
|----------|----------|-------|-------|
| Unit tests | `tests/unit/` | 19 files | Mock external deps, fast (<5s each) |
| Integration tests | `tests/integration/` | 2 files | Full stack minus external venues |
| Performance tests | `tests/perf/` | 0 | Directory exists, no tests yet |
| Property tests | `tests/property/` | 0 | Directory exists, no tests yet |

## Unit Test Files

| File | Coverage Target |
|------|----------------|
| `test_engine.py` | `TycheEngine` core |
| `test_engine_main.py` | Engine entry point |
| `test_engine_threading.py` | Threading and concurrency |
| `test_example_module.py` | `ExampleModule` |
| `test_heartbeat.py` | `HeartbeatManager`, `HeartbeatMonitor` |
| `test_heartbeat_protocol.py` | Heartbeat wire protocol |
| `test_message.py` | Message serialization/deserialization |
| `test_module.py` | `TycheModule` registration and events |
| `test_module_base.py` | `ModuleBase` lifecycle |
| `test_module_main.py` | Module entry point |
| `test_signal_handling.py` | OS signal handling |
| `test_types.py` | Core types and enums |
| `test_ctp_gateway.py` | CTP gateway base class |
| `test_ctp_gateway_enhanced.py` | Gateway enhancements (reconnect, state) |
| `test_ctp_state_machine.py` | `ConnectionStateMachine` |
| `test_ctp_config.py` | Config loader |
| `test_gateway_main.py` | Standalone gateway runner |

## CTP Gateway Testing Pattern

CTP tests mock `openctp_ctp` before import to avoid requiring the native library:

```python
import sys
from unittest.mock import MagicMock

_mock_mdapi = MagicMock()
_mock_tdapi = MagicMock()
_mock_ctp = MagicMock()
_mock_ctp.mdapi = _mock_mdapi
_mock_ctp.tdapi = _mock_tdapi
sys.modules["openctp_ctp"] = _mock_ctp
sys.modules["openctp_ctp.mdapi"] = _mock_mdapi
sys.modules["openctp_ctp.tdapi"] = _mock_tdapi

# Provide real base classes for SPI inner classes
_mock_mdapi.CThostFtdcMdSpi = object
_mock_tdapi.CThostFtdcTraderSpi = object
```

This pattern appears in `tests/unit/test_ctp_gateway.py` and related files.

## CI Pipeline

1. **Lint job:** ruff check + mypy type check (Ubuntu, Python 3.11)
2. **Test job:** pytest unit tests with coverage
   - Matrix: Ubuntu + Windows x Python 3.9/3.10/3.11/3.12
   - Timeout: 5 minutes per job
   - Coverage uploaded to Codecov (Ubuntu + Python 3.11 only)

## Coverage Requirements

- Minimum: 80% line coverage for unit tests
- New code: >=90% coverage
- Regression >2% blocks commit
- Excluded: `if __name__ == "__main__":` blocks, type-checking imports
