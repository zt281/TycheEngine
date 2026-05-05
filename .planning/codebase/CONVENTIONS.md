# Coding Conventions

**Analysis Date:** 2026-04-28

## Naming Patterns

**Files:**
- Module files use `snake_case.py`: `gateway.py`, `order_store.py`, `clickhouse_backend.py`
- Test files use `test_{module_name}.py`: `test_order_store.py`, `test_ctp_gateway.py`
- Entry point scripts use `{module}_main.py`: `engine_main.py`, `gateway_main.py`

**Classes:**
- Use `PascalCase` for all class names
- Abstract bases end in `Base` or are prefixed: `ModuleBase`, `PersistenceBackend`, `GatewayModule`, `RiskRule`
- Concrete implementations are descriptive: `TycheEngine`, `TycheModule`, `ClickHouseBackend`, `OrderStore`, `SimulatedGateway`
- Exception types use suffix `Error` or `Exception` (standard Python)

**Functions and Methods:**
- Use `snake_case` for all functions and methods
- Private methods prefixed with single underscore: `_handle_fill`, `_extract_venue`, `_get_client`, `_broadcast_ping`
- Internal helpers at module level prefixed with underscore: `_encode_decimal`, `_infer_exchange`, `_generate_order_id`
- Property getters use `@property` decorator: `module_id`, `active_count`, `total_count`, `remaining_quantity`

**Variables:**
- Use `snake_case` for local variables and instance attributes
- Constants at module level use `UPPER_SNAKE_CASE`: `HEARTBEAT_INTERVAL`, `EXCHANGE_MAP`, `CTP_STATUS_MAP`
- Type variables use standard conventions: `T`, `K`, `V` when generic
- Enum members use `UPPER_SNAKE_CASE`: `BUY`, `SELL`, `MARKET`, `LIMIT`, `FILLED`

**Types:**
- All type hints use the `typing` module for Python 3.9+ compatibility
- Use `Optional[T]` for nullable values, not `T | None`
- Use `List[T]`, `Dict[K, V]` instead of built-in generics (`list[T]`, `dict[K, V]`)
- Use `Any` sparingly; prefer explicit types

## Code Style

**Formatting:**
- Tool: `ruff` (configured in `pyproject.toml`)
- Line length: 100 characters (`line-length = 100`)
- Ruff ignores `E501` (line too long) since the 100-char limit is the target

**Linting:**
- Tool: `ruff check src tests`
- Selected rules: `E` (pycodestyle errors), `F` (Pyflakes), `I` (isort), `W` (pycodestyle warnings)
- CI runs linting before tests (`.github/workflows/ci.yml`)

**Type Checking:**
- Tool: `mypy src`
- Config in `pyproject.toml`:
  - `python_version = "3.9"`
  - `disallow_untyped_defs = true` (all defs must have type annotations)
  - `warn_return_any = true`
  - `ignore_missing_imports = true` (for third-party libs without stubs)

## Import Organization

**Order:**
1. Standard library imports
2. Third-party imports (e.g., `zmq`, `msgpack`, `pytest`)
3. Internal package imports (e.g., `from tyche.types import ...`, `from modules.trading.models.order import ...`)

**Path Aliases:**
- Core engine: `tyche.{module}` (e.g., `tyche.engine`, `tyche.module`, `tyche.types`)
- Trading modules: `modules.trading.{submodule}` (e.g., `modules.trading.models.order`)
- `sys.path` is adjusted in `tests/conftest.py` to include `src/`

**Example:**
```python
import logging
import threading
import time
from typing import Any, Dict, List, Optional

import zmq

from tyche.message import Message, deserialize, serialize
from tyche.types import HEARTBEAT_INTERVAL, Endpoint, Interface, MessageType
```

## Error Handling

**Patterns:**
- Use `logging` module with module-level logger: `logger = logging.getLogger(__name__)`
- Log at appropriate levels: `logger.warning()` for recoverable issues, `logger.error()` for failures
- Return `None` or sentinel values for expected failure cases (e.g., `get_order()` returns `None` if not found)
- Use exceptions for truly exceptional conditions (invalid state transitions, connection failures)
- Risk rule engine catches exceptions per-rule and converts to failed results:
  ```python
  try:
      result = rule.check(order, context)
  except Exception as e:
      logger.error("Risk rule %s raised exception: %s", rule.name, e)
      results.append(RiskCheckResult(passed=False, rule_name=rule.name, reason=f"Exception: {e}"))
  ```

**State Machine Validation:**
- Invalid transitions are logged and return `None` rather than raising:
  ```python
  valid_next = _VALID_TRANSITIONS.get(order.status, [])
  if new_status not in valid_next:
      logger.warning("Invalid state transition for order %s: %s -> %s", ...)
      return None
  ```

## Logging

**Framework:** Python standard `logging`

**Patterns:**
- Every module defines: `logger = logging.getLogger(__name__)`
- Log messages use `%s` formatting (not f-strings) for lazy evaluation:
  ```python
  logger.info("Gateway %s executing order: %s %s %s @ %s", self.venue_name, ...)
  ```
- Tests verify log output using `caplog` fixture:
  ```python
  with caplog.at_level("WARNING", logger="modules.trading.oms.module"):
      oms_module._handle_fill(fill_payload)
  assert "unknown order" in caplog.text.lower()
  ```

## Docstrings

**Style:** Google-style docstrings

**Patterns:**
- Module-level docstrings describe the module's purpose
- Class docstrings describe responsibilities and usage
- Method docstrings describe args, returns, and behavior
- Type hints are preferred over docstring type annotations

**Example:**
```python
class OrderStore:
    """Thread-safe in-memory order store with state machine enforcement.

    Tracks all orders and validates state transitions. Provides
    query methods for active/completed orders.
    """

    def get_order(self, order_id: str) -> Optional[Order]:
        """Get an order by ID."""
        ...
```

## Function Design

**Size:** Functions are generally small (< 30 lines). Complex operations are decomposed.

**Parameters:**
- Use keyword-only arguments for optional config: `def __init__(self, ..., **kwargs: Any)`
- Use `Optional[T] = None` for optional parameters
- Dataclasses are preferred for parameter grouping (e.g., `RiskContext`, `ReconnectConfig`)

**Return Values:**
- Return explicit result types (dataclasses) rather than raw dicts
- Use `Optional[T]` when a result may not exist
- Properties for computed values: `remaining_quantity`, `is_active`, `is_terminal`

## Module Design

**Exports:**
- `__init__.py` files re-export public symbols
- Trading modules expose public API through `__init__.py` (e.g., `modules.trading.events`)

**Barrel Files:**
- `modules/trading/__init__.py` exports event constants
- `modules/trading/models/__init__.py` re-exports model classes

**Abstract Base Classes:**
- `ModuleBase` (`src/tyche/module_base.py`): Abstract base for all modules
- `PersistenceBackend` (`src/modules/trading/persistence/backend.py`): Abstract base for storage backends
- `RiskRule` (`src/modules/trading/risk/rules.py`): Abstract base for risk rules
- `GatewayModule` (`src/modules/trading/gateway/base.py`): Abstract base for exchange gateways

## Data Model Patterns

**Dataclasses:**
- All domain models use `@dataclass`: `Order`, `Fill`, `OrderUpdate`, `Position`, `Quote`, `Trade`
- Include `to_dict()` and `from_dict()` methods for serialization round-trips
- Use `Decimal` for all monetary values (price, quantity, P&L)
- Use `secrets.token_hex()` for ID generation (cryptographically secure)

**Enums:**
- All categorical types use `Enum`: `Side`, `OrderType`, `OrderStatus`, `TimeInForce`, `Offset`, `PositionSide`
- Enum values use `auto()` for internal types, string values for serialization types

**State Machines:**
- Explicit transition tables: `_VALID_TRANSITIONS` dict in `OrderStore`
- State machine classes for complex state: `ConnectionStateMachine` for CTP gateway

## Thread Safety

**Patterns:**
- Use `threading.Lock()` for shared mutable state
- Lock held for minimal duration (just the dict operation)
- Queue-based bridging between threads (CTP SPI callbacks -> module dispatcher)

**Example:**
```python
class OrderStore:
    def __init__(self) -> None:
        self._orders: Dict[str, Order] = {}
        self._lock = threading.Lock()

    def add_order(self, order: Order) -> None:
        with self._lock:
            self._orders[order.order_id] = order
```

## Decimal Handling

- All financial calculations use `Decimal` from the `decimal` module
- Custom MessagePack encoder/decoder preserves `Decimal` precision:
  ```python
  def _encode_decimal(obj: Any) -> Any:
      if isinstance(obj, Decimal):
          return {"__decimal__": str(obj)}
      ...
  ```
- String conversion in `to_dict()` / `from_dict()` for JSON compatibility

---

*Convention analysis: 2026-04-28*
