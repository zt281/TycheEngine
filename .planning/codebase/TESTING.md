# Testing Patterns

**Analysis Date:** 2026-04-28

## Test Framework

**Runner:**
- pytest >=7.4.0
- Config: `pyproject.toml` (`[tool.pytest.ini_options]`)

**Plugins:**
- `pytest-asyncio>=0.21.0` — async test support (auto mode)
- `pytest-timeout>=2.2.0` — 30s default timeout per test
- `pytest-cov>=4.1.0` — coverage reporting

**Run Commands:**
```bash
pytest tests/ -v                    # Run all tests
pytest tests/unit/ -v               # Run unit tests only
pytest tests/integration/ -v        # Run integration tests only
pytest tests/unit/ -v --timeout=30 --cov=src/tyche --cov-report=term   # With coverage
pytest tests/ -v -m "not slow"      # Exclude slow tests
pytest tests/ -v -m slow            # Run only slow tests
```

## Test File Organization

**Location:**
- Unit tests: `tests/unit/`
- Integration tests: `tests/integration/`
- Performance tests: `tests/perf/` (directory exists, empty)
- Property tests: `tests/property/` (directory exists, empty)

**Naming:**
- Test files: `test_{module_name}.py`
- Test classes: `Test{Feature}`
- Test functions: `test_{description}`

**Structure:**
```
tests/
├── conftest.py              # Shared pytest config (sys.path setup)
├── unit/
│   ├── test_engine.py
│   ├── test_module.py
│   ├── test_message.py
│   ├── test_types.py
│   ├── test_order_store.py
│   ├── test_risk_rules.py
│   ├── test_ctp_gateway.py
│   ├── test_simulated_gateway.py
│   ├── test_clickhouse_backend_unit.py
│   ├── test_jsonl_backend.py
│   ├── test_schema.py
│   ├── test_backend.py
│   ├── test_oms_module.py
│   ├── test_portfolio_module.py
│   ├── test_strategy_context.py
│   ├── test_data_recorder.py
│   ├── test_heartbeat.py
│   ├── test_heartbeat_protocol.py
│   ├── test_signal_handling.py
│   ├── test_engine_threading.py
│   ├── test_engine_main.py
│   ├── test_module_main.py
│   ├── test_gateway_main.py
│   ├── test_example_module.py
│   ├── test_module_base.py
│   ├── test_ctp_config.py
│   ├── test_ctp_state_machine.py
│   └── test_ctp_gateway_enhanced.py
└── integration/
    ├── test_engine_module.py
    ├── test_trading_pipeline.py
    ├── test_message_queue_perf.py
    ├── test_multiprocess.py
    └── test_clickhouse_backend.py
```

**No `__init__.py` in tests/ or subdirectories** — pytest handles discovery without it.

## Test Structure

**Suite Organization:**
```python
class TestMaxPositionSizeRule:
    """Tests for MaxPositionSizeRule."""

    def test_passes_when_under_limit(self, order, context):
        rule = MaxPositionSizeRule(max_size=Decimal("1000"))
        result = rule.check(order, context)
        assert result.passed is True
        assert result.rule_name == "max_position_size"

    def test_fails_when_projected_exceeds_limit(self, order, context):
        context.positions["BTC-USD"] = Position(
            instrument_id="BTC-USD",
            quantity=Decimal("998"),
        )
        rule = MaxPositionSizeRule(max_size=Decimal("1000"))
        result = rule.check(order, context)
        assert result.passed is False
        assert "exceed max size" in result.reason
```

**Patterns:**
- Use `pytest.fixture` for shared test data (fixtures defined at module or class level)
- Use `tmp_path` fixture for filesystem tests (temporary directories)
- Use `caplog` fixture for log assertion tests
- Group related tests in classes with descriptive docstrings

## Mocking

**Framework:** `unittest.mock` (standard library)

**Patterns:**
```python
# Mock external dependency before import
import sys
from unittest.mock import MagicMock

_mock_ctp = MagicMock()
sys.modules["openctp_ctp"] = _mock_ctp

# Mock ZMQ context to avoid real socket creation
with patch("tyche.module.zmq.Context"):
    module = OMSModule(engine_endpoint=endpoint)

# Mock methods on instance
gw.publish_quote = MagicMock()
gw.publish_trade = MagicMock()

# Patch module-level functions
with patch("modules.trading.gateway.simulated.random.random", return_value=0.0):
    with patch("modules.trading.gateway.simulated.time.sleep"):
        result = gateway.submit_order(order)

# Mock send_event to capture events instead of using ZMQ
def capture(event: str, payload: Dict[str, Any]) -> None:
    captured_events.append({"event": event, "payload": payload})
module.send_event = capture
```

**What to Mock:**
- ZMQ sockets and contexts (all unit tests)
- External exchange APIs (CTP, ClickHouse)
- `random` and `time` for deterministic behavior
- File I/O using `tmp_path` fixture

**What NOT to Mock:**
- Internal dataclass operations (test directly)
- State machine transitions (test directly)
- Serialization round-trips (test directly)

## Fixtures and Factories

**Test Data:**
```python
# Factory function for orders
def _make_order(
    instrument_id: str = "BTC.binance.crypto",
    side: Side = Side.BUY,
    status: OrderStatus = OrderStatus.NEW,
    quantity: Decimal = Decimal("10"),
    strategy_id: str = "strat_01",
    price: Decimal = Decimal("50000"),
) -> Order:
    return Order(
        instrument_id=instrument_id,
        side=side,
        order_type=OrderType.LIMIT,
        quantity=quantity,
        price=price,
        status=status,
        strategy_id=strategy_id,
        created_at=time.time(),
        updated_at=time.time(),
    )

# Factory function for fills
def _make_fill(
    order_id: str,
    quantity: Decimal = Decimal("5"),
    price: Decimal = Decimal("51000"),
) -> Fill:
    return Fill(
        order_id=order_id,
        instrument_id="BTC.binance.crypto",
        side=Side.BUY,
        price=price,
        quantity=quantity,
        timestamp=time.time(),
    )
```

**Location:** Factory functions are defined at module level in each test file.

**pytest Fixtures:**
```python
@pytest.fixture
def order():
    return Order(
        instrument_id="BTC-USD",
        side=Side.BUY,
        order_type=OrderType.LIMIT,
        quantity=Decimal("5"),
        price=Decimal("100"),
    )

@pytest.fixture
def context():
    return RiskContext()

@pytest.fixture
def recorder(tmp_path: Path) -> DataRecorderModule:
    endpoint = Endpoint(host="127.0.0.1", port=5555)
    return DataRecorderModule(
        engine_endpoint=endpoint,
        data_dir=str(tmp_path / "recorded"),
        instrument_ids=["BTCUSDT.simulated.crypto"],
    )
```

## Coverage

**Requirements:**
- Minimum line coverage: **80%** for unit tests
- New code must have **>=90%** coverage
- Coverage regression >2% blocks commit
- Excluded: `if __name__ == "__main__":` blocks, type-checking imports

**Configuration (`pyproject.toml`):**
```toml
[tool.coverage.run]
source = ["src/tyche", "src/modules"]
omit = ["*/tests/*"]

[tool.coverage.report]
exclude_lines = [
    "if __name__ == .__main__.:",
    "pragma: no cover",
]
```

**View Coverage:**
```bash
pytest tests/unit/ -v --cov=src/tyche --cov-report=term
pytest tests/unit/ -v --cov=src/tyche --cov-report=xml
```

## Test Types

**Unit Tests:**
- Scope: Individual classes/functions in isolation
- External deps mocked (ZMQ, databases, exchange APIs)
- Fast execution (<5 seconds per file)
- 28 test files in `tests/unit/`

**Integration Tests:**
- Scope: Full stack minus external venues
- Real ZeroMQ sockets used for engine-module communication
- Docker ClickHouse required for `test_clickhouse_backend.py`
- 5 test files in `tests/integration/`

**Performance Tests:**
- Scope: Message queue throughput and latency
- Located in `tests/integration/test_message_queue_perf.py`
- Marked with `@pytest.mark.slow`
- Assertions on throughput (>=1000 msg/s) and latency (<50ms avg)

**Property Tests:**
- Not currently implemented (directory `tests/property/` exists but empty)
- CLAUDE.md specifies using `hypothesis` for serialization round-trips

## CTP Gateway Testing Pattern

CTP tests mock `openctp_ctp` **before** importing gateway modules to avoid requiring the native library:

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

# Assign real string values to CTP constants
_mock_tdapi.THOST_FTDC_OPT_LimitPrice = "2"
_mock_tdapi.THOST_FTDC_D_Buy = "0"
# ... etc

import pytest  # noqa: E402
from modules.trading.gateway.ctp.gateway import (  # noqa: E402
    CTP_STATUS_MAP, EXCHANGE_MAP, _extract_symbol, _safe_str,
)
```

This pattern appears in:
- `tests/unit/test_ctp_gateway.py`
- `tests/unit/test_ctp_gateway_enhanced.py`

## CI Pipeline

**GitHub Actions** (`.github/workflows/ci.yml`):

1. **Lint job:**
   - `ruff check src tests`
   - `mypy src`
   - Runs on Ubuntu with Python 3.11

2. **Test job:**
   - Runs after lint job succeeds
   - Matrix: Ubuntu + Windows x Python 3.9/3.10/3.11/3.12
   - Timeout: 5 minutes per job
   - Command: `pytest tests/unit/ -v --timeout=30 --cov=src/tyche --cov-report=xml --cov-report=term`
   - Coverage uploaded to Codecov (Ubuntu + Python 3.11 only)

## Common Patterns

**Async Testing:**
- `pytest-asyncio` configured with `asyncio_mode = "auto"`
- Not heavily used; most code is synchronous threading

**Error Testing:**
```python
def test_ensure_schema_catches_exception():
    client = MagicMock()
    client.command.side_effect = Exception("connection refused")
    manager = SchemaManager()
    result = manager.ensure_schema(client)
    assert result is False
```

**Thread Safety Testing:**
```python
def test_concurrent_add_and_update_no_crash(self):
    store = OrderStore()
    orders = [_make_order(status=OrderStatus.NEW) for _ in range(100)]

    def add_orders():
        for o in orders:
            store.add_order(o)

    def update_orders():
        for o in orders:
            store.update_status(o.order_id, OrderStatus.PENDING_SUBMIT)

    t1 = threading.Thread(target=add_orders)
    t2 = threading.Thread(target=update_orders)
    t1.start(); t2.start()
    t1.join(); t2.join()
    assert store.total_count == 100
```

**Serialization Round-trip Testing:**
```python
def test_decimal_precision_preserved():
    msg = Message(
        msg_type=MessageType.EVENT,
        sender="test",
        event="price",
        payload={"price": Decimal("123.456789012345")},
    )
    data = serialize(msg)
    restored = deserialize(data)
    assert isinstance(restored.payload["price"], Decimal)
    assert restored.payload["price"] == Decimal("123.456789012345")
```

**Log Assertion Testing:**
```python
def test_unknown_fill_logs_warning(self, oms_module, caplog):
    fill_payload = _make_fill("unknown_order")
    with caplog.at_level("WARNING", logger="modules.trading.oms.module"):
        oms_module._handle_fill(fill_payload)
    assert "unknown order" in caplog.text.lower()
```

## Testing Gaps

**Missing test categories:**
- `tests/perf/` — directory exists but contains no tests
- `tests/property/` — directory exists but contains no tests (CLAUDE.md specifies hypothesis for serialization round-trips)

**Slow test isolation:**
- Performance tests in `test_message_queue_perf.py` are marked `@pytest.mark.slow`
- Integration tests use real ZMQ sockets with `time.sleep()` for synchronization
- These can be flaky on slow CI runners

**External dependency tests:**
- ClickHouse integration tests require Docker (`docker compose -f docker/clickhouse-compose.yml up -d`)
- Tests skip gracefully when ClickHouse is unavailable

---

*Testing analysis: 2026-04-28*
