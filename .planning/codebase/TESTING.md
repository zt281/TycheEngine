# Testing Strategy and Quality Assessment

## Test Organization

```
tests/
├── conftest.py              # Shared fixtures
├── integration/             # Full stack integration tests
│   ├── test_clickhouse_backend.py
│   ├── test_engine_module.py
│   ├── test_event_chaining.py
│   ├── test_job_pattern.py
│   ├── test_message_queue_perf.py
│   ├── test_multiprocess.py
│   └── test_trading_pipeline.py
├── unit/                    # Unit tests (mocked external deps)
│   ├── test_backend.py
│   ├── test_clickhouse_backend_unit.py
│   ├── test_cpp_example_module.py
│   ├── test_ctp_config.py
│   ├── test_ctp_gateway.py
│   ├── test_ctp_gateway_enhanced.py
│   ├── test_ctp_state_machine.py
│   ├── test_data_recorder.py
│   ├── test_engine.py
│   ├── test_engine_main.py
│   ├── test_engine_threading.py
│   ├── test_example_module.py
│   ├── test_gateway_main.py
│   ├── test_heartbeat.py
│   ├── test_heartbeat_protocol.py
│   ├── test_jsonl_backend.py
│   ├── test_message.py
│   ├── test_module.py
│   ├── test_module_base.py
│   ├── test_oms_module.py
│   ├── test_order_store.py
│   ├── test_portfolio_module.py
│   ├── test_risk_rules.py
│   ├── test_rust_example_module.py
│   ├── test_schema.py
│   ├── test_signal_handling.py
│   ├── test_simulated_gateway.py
│   ├── test_strategy_context.py
│   └── test_types.py
└── (no __init__.py files — pytest discovery without them)
```

## Test Framework Configuration

| Setting | Value | Source |
|---------|-------|--------|
| Framework | pytest | `pyproject.toml` |
| Test paths | `tests/` | `pyproject.toml` |
| Timeout | 30s per test | `pyproject.toml` |
| Async mode | auto | `pyproject.toml` |
| Coverage source | `src/tyche`, `src/modules` | `pyproject.toml` |
| Coverage omit | `*/tests/*` | `pyproject.toml` |
| Slow marker | `@pytest.mark.slow` | `pyproject.toml` |

## CI Configuration

- **Lint job**: ruff + mypy on Ubuntu with Python 3.11
- **Test job**: Matrix of OS (ubuntu, windows) x Python (3.9, 3.10, 3.11, 3.12)
- **Coverage**: Uploaded to Codecov on ubuntu-latest + Python 3.11
- **Timeout**: 5 minutes per CI job

## Test Categories

### Unit Tests
- Mock external dependencies (ZMQ contexts, ClickHouse connections)
- Focus on single component behavior
- Expected to run in <5 seconds
- Coverage target: >=80% line coverage

### Integration Tests
- Full stack minus external venues
- Real ZeroMQ sockets (inproc/tcp)
- Multi-process scenarios
- ClickHouse backend with real connection (docker-compose available)

### Performance Tests
- `test_message_queue_perf.py` — queue throughput benchmarks
- Target: p99 latency < 10us for dispatch path

### Property Tests
- Serialization/deserialization round-trips
- Decimal precision preservation through encode/decode

## Test Quality Assessment

### Strengths
- Good coverage of core engine components (`test_engine.py`, `test_module.py`)
- Heartbeat protocol thoroughly tested (`test_heartbeat.py`, `test_heartbeat_protocol.py`)
- Message serialization round-trip coverage (`test_message.py`)
- Multi-process integration tests present
- CTP gateway has dedicated test suites

### Gaps
- **No property-based tests** using hypothesis (mentioned in design spec but not implemented)
- **No dedicated performance benchmarks** in CI
- **Limited coverage** of error paths in engine workers
- **Missing tests** for admin query endpoints (STATUS, MODULES, QUEUES, STATS)
- **Job routing** integration tests may be incomplete (job pattern is new)
- **C++ module** tests only cover example module (`test_cpp_example_module.py`)
- **Rust module** tests only cover example module (`test_rust_example_module.py`)

## Test Patterns

### Fixture Usage
- `conftest.py` provides shared fixtures for ZMQ contexts and engine instances
- Tests use temporary ports to avoid conflicts
- Engine instances started with `start_nonblocking()` for testability

### Mocking Strategy
- ZMQ sockets mocked where possible
- ClickHouse backend mocked in unit tests; real connection in integration
- Time-based tests use `time.time()` directly (no freezegun visible)

### TDD Evidence
- RED/GREEN cycle documented in impl logs (`docs/impl/`)
- Test files precede implementation commits per `CLAUDE.md` TDD rules
- `test_types.py` has been modified recently (git status)
