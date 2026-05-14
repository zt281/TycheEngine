# Coding Conventions

**Analysis Date:** 2026-05-14

## Naming Patterns

**Files:**
- Python modules: `snake_case.py` — `engine.py`, `module_base.py`, `heartbeat.py`
- C++ headers: `PascalCase.h` — `types.h`, `module.h`
- C++ implementation: `snake_case.cpp` — `module.cpp`
- Rust modules: `snake_case.rs` — `lib.rs`, `types.rs`, `module.rs`, `message.rs`

**Classes:**
- PascalCase for all classes — `TycheEngine`, `TycheModule`, `HeartbeatManager`, `TopicQueue`, `ModuleBase`
- Dataclasses use same convention — `Message`, `Envelope`, `Endpoint`, `Interface`, `ModuleInfo`
- Protocols use PascalCase — `ModuleBase(Protocol)`

**Functions and Methods:**
- snake_case for all functions — `register_module()`, `send_event()`, `_dispatch()`
- Private methods prefixed with single underscore — `_start_workers()`, `_process_registration()`, `_event_receiver()`
- Static methods for utility functions — `ModuleId.generate()`, `TycheModule._pattern_for_name()`

**Variables:**
- snake_case for variables — `module_id`, `heartbeat_endpoint`, `_topic_queues`
- Private instance variables prefixed with single underscore — `self._lock`, `self._running`, `self._stop_event`
- Module-level logger named `logger` — `logger = logging.getLogger(__name__)`

**Constants:**
- UPPER_SNAKE_CASE for module-level constants — `HEARTBEAT_INTERVAL = 1.0`, `HEARTBEAT_LIVENESS = 3`, `ADMIN_PORT_DEFAULT = 5560`

**Types:**
- Enums use PascalCase with UPPER_SNAKE_CASE members — `EventType.REQUEST`, `DurabilityLevel.SYNC_FLUSH`
- Type aliases use PascalCase — `Payload = serde_json::Value` (Rust)

## Code Style

**Formatting:**
- Tool: **ruff** configured in `pyproject.toml`
- Line length: **100 characters** (`[tool.ruff] line-length = 100`)
- Lint rules: `E`, `F`, `I`, `W` (errors, Pyflakes, isort, warnings)
- E501 (line too long) is explicitly ignored since the 100-char limit is enforced by ruff itself

**Type Checking:**
- Tool: **mypy** configured in `pyproject.toml`
- Python version target: 3.9
- `disallow_untyped_defs = true` — all function definitions must have type annotations
- `warn_return_any = true` — warns on functions returning `Any`
- `warn_unused_configs = true`
- `ignore_missing_imports = true` — for third-party libraries without stubs

## Import Organization

**Order (enforced by ruff isort rules):**
1. Standard library imports — `import logging`, `import threading`, `import time`
2. Third-party imports — `import zmq`, `import msgpack`
3. Internal project imports — `from tyche.types import ...`, `from tyche.message import ...`

**Style:**
- Multiple names from same module on single line: `from typing import Any, Dict, List, Optional`
- No `typing.` prefix usage; all typing imports are explicit
- Internal imports use absolute project paths (not relative): `from tyche.engine import TycheEngine`

**Path Aliases:**
- No custom path aliases configured
- `sys.path.insert(0, ...)` used in `tests/conftest.py` for test discovery

## Error Handling

**Patterns:**
- Broad exception catching inside worker loops with `self._running` guard to distinguish shutdown from real errors:
  ```python
  try:
      frames = socket.recv_multipart()
  except zmq.error.Again:
      continue
  except Exception as e:
      if self._running:
          logger.error("Error: %s", e)
  ```
- `assert` statements used for internal invariants (socket non-null after creation):
  ```python
  assert self.context is not None
  self._registration_socket = self.context.socket(zmq.ROUTER)
  assert self._registration_socket is not None
  ```
- Specific exceptions raised for API contract violations:
  ```python
  raise RuntimeError(f"[{self._module_id}] Cannot request: job socket not connected")
  raise TimeoutError(f"Job request '{event}' timed out after {timeout}s")
  raise TypeError(f"Cannot serialize {type(obj)}")
  ```
- Malformed messages are silently dropped (heartbeat receive worker ignores deserialization errors with `pass`)

**Thread Safety:**
- `threading.Lock()` for shared state — `self._lock`, `self._topic_queues_lock`
- `threading.RLock()` for handler registry (allows reentrant access) — `self._handlers_lock`
- Locks are acquired with `with` statements exclusively

## Logging

**Framework:** Python standard `logging` module

**Patterns:**
- Per-module logger: `logger = logging.getLogger(__name__)`
- Log levels used:
  - `logger.error()` — worker failures, deserialization errors, socket errors
  - `logger.warning()` — malformed frames, no handler for topic, stale responses
  - `logger.info()` — module registration, heartbeat expiration, job router binding
  - `logger.debug()` — dynamic queue creation, job forwarding, topic queue GC
- Log messages include module ID in brackets for module-side logging:
  ```python
  logger.error("[%s] Handler %s raised: %s", self._module_id, topic, e)
  ```
- String formatting uses `%` style (not f-strings) for lazy evaluation:
  ```python
  logger.error("Registration error: %s", e)
  ```

## Comments

**When to Comment:**
- Module-level docstrings describe purpose and architecture
- Section dividers with Unicode box-drawing characters: `# ── Registration ──────────────────────────────────────────────`
- Inline comments explain non-obvious logic (ZMQ frame handling, backpressure)
- Version markers for design iterations: `(v3 unified queue)`, `Per Paranoid Pirate pattern`

**Docstrings:**
- Google-style docstrings for public methods with Args/Returns/Raises sections:
  ```python
  def serialize(message: Message) -> bytes:
      """Serialize a Message to MessagePack bytes.

      Args:
          message: Message to serialize

      Returns:
          MessagePack-encoded bytes
      """
  ```
- Dataclass docstrings document attributes
- All public functions and classes have docstrings

## Function Design

**Size:** Functions range from 5-50 lines. Worker loop methods are longer (80-150 lines) but follow a consistent pattern.

**Parameters:**
- Type annotations required on all function parameters (enforced by mypy `disallow_untyped_defs`)
- Optional parameters use `Optional[T]` with default `None`
- `**kwargs` / `*args` used sparingly (only in test helper modules)

**Return Values:**
- Return type annotations on all functions
- `-> None` explicitly stated for side-effect functions
- `-> Optional[T]` for functions that may return nothing

## Module Design

**Exports:**
- `__init__.py` uses explicit `__all__` list:
  ```python
  __all__ = [
      "__version__",
      "ModuleId",
      "EventType",
      # ...
  ]
  ```

**Barrel Files:**
- `src/tyche/__init__.py` re-exports all public APIs from submodules
- No nested barrel files beyond the package root

**Multi-Language Parity:**
- Python types in `src/tyche/types.py` have C++ mirrors in `src/tyche/cpp/types.h` and Rust mirrors in `src/tyche/rust/src/types.rs`
- Comments explicitly note parity: `Mirrors src/tyche/types.py`
- Enum values are string-matched across languages (e.g., `"on"`, `"send"`, `"hbt"`)

## C++ Conventions

- Namespaces: `tyche` namespace wraps all code
- Private members: leading underscore — `_module_id`, `_handlers_lock`
- PIMPL pattern used for ZMQ socket hiding in `module.h`/`module.cpp`
- `inline` for header-only functions in `types.h`
- `= delete` for copy/move constructors

## Rust Conventions

- Modules organized as `pub mod types; pub mod message; pub mod module;`
- Re-exports at crate root via `pub use`
- Serde derives for serialization: `#[derive(Clone, Debug, Serialize, Deserialize)]`
- `serde(rename = "...")` for wire-format compatibility with Python
- Error handling: `.map_err(|e| e.to_string())` pattern for ZMQ operations

---

*Convention analysis: 2026-05-14*
