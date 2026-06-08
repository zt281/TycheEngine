# Testing Patterns

**Analysis Date:** 2026-05-14

## Test Framework

**Runner:**
- **pytest** >=7.4.0 (configured in `pyproject.toml`)
- Config: `[tool.pytest.ini_options]` in `pyproject.toml`
- Test paths: `tests/`
- File pattern: `test_*.py`
- Class pattern: `Test*`
- Function pattern: `test_*`
- Default options: `-v --tb=short`
- Async mode: `auto`
- Timeout: 30 seconds per test (`pytest-timeout`)

**Assertion Library:**
- Standard pytest assertions (`assert` statements)
- No external assertion library (e.g., `unittest.TestCase` not used)

**Additional Plugins:**
- `pytest-asyncio>=0.21.0` — async test support
- `pytest-timeout>=2.2.0` — per-test timeout enforcement
- `pytest-cov>=4.1.0` — coverage reporting

**Run Commands:**
```bash
pytest tests/ -v                    # Run all tests
pytest tests/unit/ -v               # Run unit tests only
pytest tests/integration/ -v        # Run integration tests only
pytest tests/ -v -m "not slow"      # Exclude slow tests
pytest tests/ --cov=src/tyche --cov-report=term   # With coverage
```

## Test File Organization

**Location:**
- Unit tests: `tests/unit/`
- Integration tests: `tests/integration/`
- Performance tests: `tests/integration/test_message_queue_perf.py`
- Property tests: Not currently present

**Naming:**
- Files: `test_{module_name}.py` — `test_types.py`, `test_message.py`, `test_engine.py`
- Functions: `test_{what_is_tested}()` — `test_module_id_format_with_deity()`, `test_decimal_precision_preserved()`
- Descriptive docstrings on every test function explaining the assertion

**Structure:**
```
tests/
├── conftest.py                          # Shared pytest configuration
├── unit/
│   ├── test_types.py                    # Core type tests
│   ├── test_message.py                  # Serialization roundtrips
│   ├── test_heartbeat.py                # HeartbeatMonitor/Sender unit tests
│   ├── test_heartbeat_protocol.py       # Module-engine heartbeat protocol
│   ├── test_engine.py                   # Engine unit tests (mocked ZMQ)
│   ├── test_engine_threading.py         # Engine with real ZMQ sockets
│   ├── test_module.py                   # TycheModule unit tests
│   ├── test_module_base.py              # Protocol compliance tests
│   ├── test_example_module.py           # ExampleModule behavior tests
│   ├── test_cpp_example_module.py       # C++ module parity tests
│   ├── test_rust_example_module.py      # Rust module parity tests
│   ├── test_signal_handling.py          # Thread shutdown tests
│   └── ... (additional trading-specific tests)
└── integration/
    ├── test_engine_module.py            # Full engine+module interaction
    ├── test_event_chaining.py           # Multi-module event flows
    ├── test_job_pattern.py              # Request/response roundtrips
    ├── test_message_queue_perf.py       # Throughput benchmarks
    ├── test_multiprocess.py             # Multi-process scenarios
    └── test_trading_pipeline.py         # End-to-end trading flow
```

**Note:** All test files listed above are tracked in git but currently deleted from the working tree (git status shows `D` for deleted). The `tests/` directory is empty on disk. The test suite was present in the initial commit but has been removed in the current working tree.

## Test Structure

**Suite Organization:**
```python
def test_module_id_format_with_deity():
    """ModuleId.generate with explicit deity produces {deity}{6-hex-chars}."""
    mid = ModuleId.generate("zeus")
    assert mid.startswith("zeus")
    suffix = mid[len("zeus"):]
    assert len(suffix) == 6
    int(suffix, 16)  # Suffix must be valid hex
```

**Patterns:**
- Each test is a standalone function (no class-based test suites in core tests)
- Docstrings describe the expected behavior, not the implementation
- Tests use simple assertions; no complex setup/teardown fixtures
- `conftest.py` only sets `sys.path` for imports; no shared fixtures defined

## Mocking

**Framework:** `unittest.mock` (standard library)

**Patterns:**
```python
from unittest.mock import Mock

# Mocking ZMQ sockets
socket = Mock()
sender = HeartbeatSender(socket, "zeus3f7a9c")
sender.send()
assert socket.send_multipart.called
frames = socket.send_multipart.call_args[0][0]
```

```python
# Mocking module info for engine tests
module_info = Mock()
module_info.module_id = "zeus3f7a9c"
module_info.interfaces = []
engine.register_module(module_info)
```

**What to Mock:**
- ZMQ sockets in unit tests (heartbeat sender, admin query)
- Module info objects for engine registry tests
- External dependencies (not present in core)

**What NOT to Mock:**
- Integration tests use real ZMQ sockets and real `TycheEngine`/`TycheModule` instances
- Message serialization/deserialization is tested with real msgpack encode/decode

## Fixtures and Factories

**Test Data:**
- Inline construction within each test (no shared fixtures)
- Helper functions for common setup:
  ```python
  def _build_engine() -> TycheEngine:
      return TycheEngine(
          registration_endpoint=Endpoint("127.0.0.1", 5555),
          event_endpoint=Endpoint("127.0.0.1", 5556),
          heartbeat_endpoint=Endpoint("127.0.0.1", 5557),
      )
  ```

**Location:**
- No dedicated fixtures directory
- Helper functions defined at module level in test files

## Coverage

**Requirements:**
- Configured in `pyproject.toml` under `[tool.coverage.run]`
- Source directories: `src/tyche`, `src/modules`
- Omit: `*/tests/*`
- Exclude lines: `if __name__ == "__main__":`, `pragma: no cover`

**CI Coverage:**
- CI runs: `pytest tests/unit/ -v --timeout=30 --cov=src/tyche --cov-report=xml --cov-report=term`
- Coverage uploaded to Codecov on Ubuntu + Python 3.11 matrix entry

**View Coverage:**
```bash
pytest tests/unit/ --cov=src/tyche --cov-report=term
pytest tests/unit/ --cov=src/tyche --cov-report=html
```

## Test Types

**Unit Tests:**
- Scope: Individual classes/functions in isolation
- Mock external deps (ZMQ sockets)
- Fast execution (<1 second each)
- Examples:
  - `test_types.py` — ModuleId format, enum values, Endpoint stringification
  - `test_message.py` — Serialization roundtrips, Decimal precision preservation
  - `test_heartbeat.py` — HeartbeatMonitor tick/update, HeartbeatSender timing
  - `test_module_base.py` — Protocol compliance (cannot instantiate abstract base)

**Integration Tests:**
- Scope: Full engine + module interaction with real ZMQ sockets
- Use unique port ranges per test to avoid conflicts
- Include `time.sleep()` calls for ZMQ connection establishment
- Examples:
  - `test_engine_module.py` — Module registration via real REQ/ROUTER
  - `test_event_chaining.py` — Multi-module pub/sub via XPUB/XSUB
  - `test_job_pattern.py` — Request/response roundtrips via DEALER/ROUTER

**Performance Tests:**
- Location: `tests/integration/test_message_queue_perf.py`
- Measures: Event throughput (messages/second), latency
- Assertions: `throughput >= 1000 msg/s`, `len(received) >= msg_count * 0.95`
- Marked with `@pytest.mark.slow`

**E2E Tests:**
- `test_trading_pipeline.py` — Full trading flow simulation
- Not currently present in working tree

## Common Patterns

**Async Testing:**
- No async/await patterns in core codebase
- Thread-based concurrency tested via `threading.Thread` + `join()`:
  ```python
  engine_thread = threading.Thread(target=engine.run)
  engine_thread.start()
  time.sleep(0.3)
  engine.stop()
  engine_thread.join(timeout=3.0)
  assert not engine_thread.is_alive()
  ```

**Error Testing:**
- `pytest.raises` for expected exceptions:
  ```python
  def test_module_base_is_abstract():
      with pytest.raises(TypeError):
          ModuleBase()
  ```

**Slow Test Marking:**
- Tests with `time.sleep()` > 1 second use `@pytest.mark.slow`:
  ```python
  @pytest.mark.slow
  @pytest.mark.timeout(10)
  def test_module_does_not_expire_with_heartbeats():
      # ... 5+ seconds of real-time heartbeat testing
  ```

**Multi-Language Parity Tests:**
- C++ and Rust example modules have parallel test suites:
  ```python
  try:
      from cpp_module.example import CppExampleModule
  except ImportError:
      pytest.skip("C++ module not compiled", allow_module_level=True)
  ```
- Same assertions run against Python, C++, and Rust implementations

**Port Allocation:**
- Each integration test uses a unique port range (e.g., 25000-25099, 25100-25199)
- Prevents conflicts when running tests in parallel
- Documented in test file comments

## CI/Test Runner Config

**GitHub Actions:** `.github/workflows/ci.yml`

**Lint Job:**
- Runs on: `ubuntu-latest`
- Python: 3.11
- Steps: `ruff check src tests`, `mypy src`

**Test Job:**
- Depends on: lint job
- Matrix: Ubuntu + Windows x Python 3.9/3.10/3.11/3.12
- Timeout: 5 minutes
- Command: `pytest tests/unit/ -v --timeout=30 --cov=src/tyche --cov-report=xml --cov-report=term`

## Test Quality Assessment

**Strengths:**
- Comprehensive unit test coverage for core types and serialization
- Integration tests verify real ZMQ socket behavior
- Multi-language parity tests ensure C++/Rust compatibility
- Performance tests with concrete throughput assertions
- Descriptive docstrings on every test

**Gaps:**
- **All test files are deleted from the working tree** (present in git history only)
- No property-based tests (hypothesis) despite CLAUDE.md requirement
- No dedicated `tests/perf/` directory (perf tests mixed with integration)
- No `tests/property/` directory
- Coverage cannot be measured since tests are not present
- `tests/` directory is completely empty

**Reconnection Logic:** Not tested (no tests for Nexus disappearance/reappearance)

**Configuration Validation:** Limited coverage (endpoint/port validation not tested)

**Serialization Round-Trips:** Well-covered in `test_message.py` for Decimal precision

---

*Testing analysis: 2026-05-14*
