# Coding Conventions

*Generated: 2026-04-21*

## Style & Linting

- **Formatter/Linter:** Ruff (replaces flake8, black, isort)
- **Line length:** 100 characters (`tool.ruff.line-length = 100`)
- **Selected rules:** E, F, I, W
- **Ignored rules:** E501 (line too long — handled by formatter)
- **Type checking:** mypy with `disallow_untyped_defs = true`

## Code Patterns

### Imports

Standard library first, third-party next, local last. Ruff handles sorting automatically.

Example from `src/tyche/engine.py`:
```python
import logging
import queue
import threading
import time
from typing import Dict, List, Optional, Tuple

import zmq

from tyche.heartbeat import HeartbeatManager
from tyche.message import Message, deserialize, serialize
```

### Type Hints

- All function signatures use type hints (enforced by mypy)
- `Optional[X]` for nullable values
- `Dict[str, Any]` for payload dictionaries
- `list[str]` used in newer code (Python 3.9+), `List[str]` in older files

### Error Handling

- ZMQ timeout loops use `zmq.error.Again` exception for non-blocking recv
- Graceful shutdown checks `self._running` before logging errors
- Context managers used sparingly; explicit `try/finally` for socket cleanup

Example pattern:
```python
while self._running:
    try:
        frames = socket.recv_multipart()
        self._process(socket, frames)
    except zmq.error.Again:
        continue
    except Exception as e:
        if self._running:
            logger.error("Worker error: %s", e)
```

### Threading

- All modules use `threading.Thread` with `daemon=True`
- `threading.Event` used for stop signals (`_stop_event`)
- `threading.Lock` for shared state protection
- Thread join timeouts: 2.0s for module threads, 5.0s for dispatcher/reconnect

### Dataclasses

Heavy use of `@dataclass` for models:
```python
@dataclass
class Order:
    instrument_id: str
    side: Side
    order_type: OrderType
    quantity: Decimal
    ...
```

All model dataclasses implement `to_dict()` and `from_dict()` for serialization.

### Decimal Handling

Financial quantities use `Decimal` (not float). Custom msgpack encoder/decoder preserves Decimal precision via `{"__decimal__": str(value)}` wrapper.

### Enum Usage

Extensive enums for type safety:
- `OrderStatus`, `OrderType`, `Side`, `TimeInForce` — trading domain
- `ConnectionState` — gateway connection lifecycle
- `InterfacePattern`, `MessageType`, `DurabilityLevel` — engine messaging
- `VenueType`, `AssetClass` — classification

### Logging

- Module-level `logger = logging.getLogger(__name__)`
- Gateway logs prefix with `[MD]`, `[TD]`, `[CTP]` for context
- Format: `'[%(asctime)s] %(name)s - %(levelname)s - %(message)s'` in examples

### SPI Callback Naming

CTP SPI inner classes use CTP's original `PascalCase` method names with `# noqa: N802` to suppress PEP8 method naming rules. Example: `OnFrontConnected`, `OnRspUserLogin`, `OnRtnDepthMarketData`.

### Safe Field Extraction

Utility functions for handling CTP's C-struct fields:
- `_safe_str(value)` — decode bytes, strip null padding
- `_safe_float(value, default=0.0)` — convert numeric, treat DBL_MAX as zero
