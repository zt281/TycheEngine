# Pure Python Architecture Implementation Plan v2

**Date:** 2026-03-29
**Status:** Draft
**Based on:** `docs/design/pure_python_architecture_design_v1.md`

---

## Project State at Plan Time

The design spec for the pure Python architecture has been completed. No implementation exists yet. The project structure needs to be created from scratch, including three Python packages (`tyche-core`, `tyche-client`, `tyche-launcher`) and their associated tests, configs, and documentation.

---

## Task 1: Create project directory structure

**What needs to be done?** Create the directory layout for the project including package directories, test directories, and config directories.

**What problem does it resolve?** Establishes the project structure so subsequent tasks have locations to place files.

**Expected result?** All directories from Appendix B of the design spec exist (empty).

**Files:**
- Create directories: `tyche-core/tyche_core/`, `tyche-client/tyche_client/`, `tyche-launcher/tyche_launcher/`, `tests/unit/`, `tests/integration/`, `config/modules/`, `strategies/`

- [ ] **Step 1: Create directories**

```bash
mkdir -p tyche-core/tyche_core
mkdir -p tyche-client/tyche_client
mkdir -p tyche-launcher/tyche_launcher
mkdir -p tests/unit tests/integration
mkdir -p config/modules
mkdir -p strategies
```

- [ ] **Step 2: Commit**

```bash
git add .
git commit -m "chore: create project directory structure"
```

---

## Task 2: Create tyche-client package skeleton

**What needs to be done?** Create the `tyche-client` Python package with `pyproject.toml` and `__init__.py`, including dependency on `msgpack`.

**What problem does it resolve?** The client library package must be installable before we can implement the types and serialization modules.

**Expected result?** `pip install -e tyche-client/` succeeds.

**Files:**
- Create: `tyche-client/pyproject.toml`
- Create: `tyche-client/tyche_client/__init__.py`

- [ ] **Step 1: Create pyproject.toml**

  Package metadata per design spec section 3.2:
  - Name: `tyche-client`
  - Version: `1.0.0`
  - Dependencies: `pyzmq>=25.0`, `msgpack>=1.0`
  - Dev dependencies: `pytest>=7.0`, `ruff>=0.1.0`

- [ ] **Step 2: Create package init**

  Export `__version__` and make package importable.

- [ ] **Step 3: Commit package skeleton**

---

## Task 3: Implement protocol constants (TDD)

**What needs to be done?** Create `protocol.py` with wire protocol constants (READY, ACK, HB, CMD, etc.) per Appendix A of design spec.

**What problem does it resolve?** Both client and core need these constants for the wire protocol.

**Expected result?** `from tyche_client.protocol import READY, ACK` works and values are bytes.

**Files:**
- Create: `tyche-client/tyche_client/protocol.py`
- Create: `tests/unit/test_protocol.py`

- [ ] **Step 1: Write failing test**

  Test that all protocol constants exist and have correct types/values:
  - READY, ACK, HB, CMD, REPLY, DISCO are bytes
  - CMD_START, CMD_STOP, CMD_RECONFIGURE, CMD_STATUS are bytes
  - STATUS_OK, STATUS_ERROR are bytes
  - PROTOCOL_VERSION is int equal to 1
  - DEFAULT_HEARTBEAT_INTERVAL_MS, DEFAULT_REGISTRATION_TIMEOUT_MS are ints
  - HEARTBEAT_TIMEOUT_MULTIPLIER is int equal to 3

- [ ] **Step 2: Run test to verify it fails**

  Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_client.protocol'"

- [ ] **Step 3: Implement protocol module**

  Add all constants from Appendix A of design spec.

- [ ] **Step 4: Run test to verify it passes**

  Expected: All protocol constant tests pass.

- [ ] **Step 5: Commit**

---

## Task 4: Implement socket address helper (TDD)

**What needs to be done?** Create `transport.py` with `get_socket_address()` function that returns IPC endpoints for Linux and Windows per section 2.2 of design spec.

**What problem does it resolve?** Provides single source of truth for socket addresses, handling platform differences between Linux (Unix domain sockets) and Windows (named pipes).

**Expected result?** `get_socket_address("nexus")` returns correct endpoint for current platform.

**Files:**
- Create: `tyche-client/tyche_client/transport.py`
- Create: `tests/unit/test_transport.py`

- [ ] **Step 1: Write failing test**

  Test cases:
  - `get_socket_address("nexus")` returns Linux endpoint on Linux
  - `get_socket_address("nexus")` returns Windows endpoint on Windows
  - Same for "bus_xsub" and "bus_xpub"
  - Raises ValueError for unknown socket name

- [ ] **Step 2: Run test to verify it fails**

  Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_client.transport'"

- [ ] **Step 3: Implement transport module**

  Implement per design spec section 2.2:
  - Linux endpoints: `ipc:///tmp/tyche/{name}.sock`
  - Windows endpoints: `ipc://tyche-{name}` (with underscore to hyphen conversion)

- [ ] **Step 4: Run test to verify it passes**

  Expected: 4 tests pass (nexus, bus_xsub, bus_xpub, unknown).

- [ ] **Step 5: Commit**

---

## Task 5: Implement types module (TDD)

**What needs to be done?** Create `types.py` with all dataclasses (Tick, Quote, Trade, Bar, Order, OrderEvent, Ack, Position, Risk) per section 5.1 of design spec.

**What problem does it resolve?** These dataclasses are the fundamental data structures used throughout the system for market data and orders.

**Expected result?** All 9 dataclasses can be imported and instantiated with required fields.

**Files:**
- Create: `tyche-client/tyche_client/types.py`
- Create: `tests/unit/test_types.py`

- [ ] **Step 1: Write failing test**

  Test that all types exist with correct fields:
  - Tick with fields: instrument_id, price, size, side, timestamp_ns
  - Quote with fields: instrument_id, bid_price, bid_size, ask_price, ask_size, timestamp_ns
  - Trade with fields: instrument_id, price, size, aggressor_side, timestamp_ns
  - Bar with fields: instrument_id, open, high, low, close, volume, interval, timestamp_ns
  - Order with fields: instrument_id, client_order_id, price, qty, side, order_type, tif, timestamp_ns
  - OrderEvent with fields: instrument_id, client_order_id, exchange_order_id, fill_price, fill_qty, kind, timestamp_ns
  - Ack with fields: client_order_id, exchange_order_id, status, sent_ns, acked_ns
  - Position with fields: instrument_id, net_qty, avg_cost, timestamp_ns
  - Risk with fields: instrument_id, delta, gamma, vega, theta, dv01, notional, margin, timestamp_ns

  Test that dataclasses are frozen and have slots.

- [ ] **Step 2: Run test to verify it fails**

  Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_client.types'"

- [ ] **Step 3: Implement types module**

  Implement all 9 dataclasses per design spec section 5.1 using `@dataclass(frozen=True, slots=True)`.

- [ ] **Step 4: Run test to verify it passes**

  Expected: 5+ tests pass (type creation, frozen, slots, field values).

- [ ] **Step 5: Commit**

---

## Task 6: Implement serialization module (TDD)

**What needs to be done?** Create `encode()` and `decode()` functions using MessagePack with a `"_type"` discriminator field per section 5.2 of design spec.

**What problem does it resolve?** IPC requires efficient binary serialization; MessagePack with type discrimination enables automatic type reconstruction on the receiving end.

**Expected result?** `encode(tick)` returns MessagePack bytes with `"_type": "Tick"`; `decode(data)` returns the original Tick object.

**Files:**
- Create: `tyche-client/tyche_client/serialization.py`
- Create: `tests/unit/test_serialization.py`

- [ ] **Step 1: Write failing test**

  Test cases:
  - `encode(tick)` returns bytes with `_type: "Tick"` field
  - `decode(data)` returns Tick instance with correct field values
  - Roundtrip: `decode(encode(quote)) == quote`
  - Unknown type raises ValueError with "Unknown type" message
  - `TYPE_MAP` contains all 9 type names

- [ ] **Step 2: Run test to verify it fails**

  Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_client.serialization'"

- [ ] **Step 3: Implement serialization module**

  Implement per design spec section 5.2:
  - `encode(obj)` uses `dataclasses.asdict()` and adds `_type` field, packs with msgpack
  - `decode(data)` unpacks msgpack, extracts `_type`, looks up in TYPE_MAP, instantiates
  - `TYPE_MAP` maps type names to dataclass constructors

- [ ] **Step 4: Run test to verify it passes**

  Expected: 5 tests pass.

- [ ] **Step 5: Commit**

---

## Task 7: Create tyche-core package skeleton

**What needs to be done?** Create the `tyche-core` Python package with `pyproject.toml` and `__init__.py` for the core Nexus + Bus services.

**What problem does it resolve?** The core services (Nexus for registration, Bus for pub/sub) need their own installable package separate from the client library.

**Expected result?** Package installs successfully.

**Files:**
- Create: `tyche-core/pyproject.toml`
- Create: `tyche-core/tyche_core/__init__.py`

- [ ] **Step 1: Write pyproject.toml**

  Package metadata per design spec section 3.1:
  - Name: `tyche-core`
  - Version: `1.0.0`
  - Dependencies: `pyzmq>=25.0`, `msgpack>=1.0`
  - Console script: `tyche-core = tyche_core.__main__:main`

- [ ] **Step 2: Create package init**

  Export `__version__`.

- [ ] **Step 3: Commit package skeleton**

---

## Task 8: Implement Bus service with HWM configuration (TDD)

**What needs to be done?** Create the `Bus` class implementing an XPUB/XSUB proxy with configurable high-water-mark (HWM) and dropped message counter per section 3.1 of design spec.

**What problem does it resolve?** The Bus is the central pub/sub message broker; HWM prevents memory exhaustion under backpressure, and the dropped counter provides observability.

**Expected result?** Bus starts in a thread, forwards messages from publishers to subscribers, respects HWM limits, tracks dropped messages.

**Files:**
- Create: `tyche-core/tyche_core/bus.py`
- Create: `tests/unit/test_bus.py`

- [ ] **Step 1: Write failing test**

  Test cases:
  - `Bus(xsub_endpoint, xpub_endpoint)` creates instance with correct endpoints
  - `high_water_mark` attribute is configurable (default 10000)
  - `get_dropped_messages()` returns 0 initially
  - `start()` starts proxy in background thread
  - `stop()` stops proxy and cleans up
  - Messages published to XSUB are received by XPUB subscriber

- [ ] **Step 2: Run test to verify it fails**

  Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_core.bus'"

- [ ] **Step 3: Implement Bus module**

  Implement per design spec section 3.1:
  - `__init__` stores endpoints, HWM (default 10000), initializes counters
  - `start()` creates XSUB and XPUB sockets, sets HWM options, binds endpoints, runs `zmq.proxy` in daemon thread
  - `stop()` sets running flag to False, terminates context, joins thread
  - `get_dropped_messages()` returns current dropped count (thread-safe)
  - `_set_cpu_affinity()` sets CPU affinity on Linux (sched_setaffinity) and Windows (SetThreadAffinityMask)

- [ ] **Step 4: Run test to verify it passes**

  Expected: 5 tests pass.

- [ ] **Step 5: Commit**

---

## Task 9: Add protocol constants to tyche-core

**What needs to be done?** Create `protocol.py` in tyche-core with message type constants that mirror tyche-client.protocol per Appendix A of design spec.

**What problem does it resolve?** Both packages need the same wire protocol constants; this avoids cross-imports between core and client.

**Expected result?** `from tyche_core.protocol import READY, ACK` works and matches client constants.

**Files:**
- Create: `tyche-core/tyche_core/protocol.py`

- [ ] **Step 1: Create protocol constants**

  Copy all constants from design spec Appendix A:
  - Message types: READY, ACK, HB, CMD, REPLY, DISCO
  - Command types: CMD_START, CMD_STOP, CMD_RECONFIGURE, CMD_STATUS
  - Status codes: STATUS_OK, STATUS_ERROR
  - Protocol version and default timeouts

- [ ] **Step 2: Commit**

---

## Task 10: Implement Nexus service with exponential backoff (TDD)

**What needs to be done?** Create the `Nexus` class with ROUTER socket, module registration, heartbeat tracking, command dispatch, and exponential backoff retry calculation per section 3.1 of design spec.

**What problem does it resolve?** Nexus is the lifecycle manager for modules; backoff prevents thundering herd during recovery, heartbeats detect dead modules.

**Expected result?** Modules can register, receive ACK with assigned ID, send/receive heartbeats, receive commands (START/STOP/RECONFIGURE/STATUS).

**Files:**
- Create: `tyche-core/tyche_core/nexus.py`
- Create: `tests/unit/test_nexus.py`

- [ ] **Step 1: Write failing test**

  Test cases:
  - `Nexus(endpoint)` creates instance with correct endpoint
  - `calculate_backoff(retry_count)` returns correct exponential backoff with jitter and cap
  - Module can send READY and receive ACK with correlation_id, assigned_id, heartbeat_interval
  - Heartbeat sent by module updates last_heartbeat_ns in Nexus
  - `get_modules()` returns registered modules

- [ ] **Step 2: Run test to verify it fails**

  Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_core.nexus'"

- [ ] **Step 3: Implement Nexus module**

  Implement per design spec section 3.1 and 4.2:
  - `calculate_backoff(retry_count, base_ms, max_ms)` returns exponential delay with ±20% jitter, capped at max_ms
  - `ModuleDescriptor` dataclass stores registration info
  - `Nexus` class:
    - `__init__` sets endpoint, CPU core, timeouts, initializes module registry
    - `start()` creates ROUTER socket, binds endpoint, starts polling thread
    - `stop()` sets flag, terminates context, joins thread
    - `_run()` polls socket, handles messages, checks heartbeat timeouts every 100ms
    - `_handle_message()` dispatches by message type
    - `_handle_ready()` parses JSON descriptor, generates correlation_id and assigned_id, stores descriptor, sends ACK
    - `_handle_heartbeat()` updates last_heartbeat_ns
    - `_check_timeouts()` removes modules with missed heartbeats (3× interval)
    - `send_command(assigned_id, command, payload)` sends CMD to specific module
    - `broadcast_command(command, payload)` sends CMD to all modules
    - `get_modules()` returns copy of registry

- [ ] **Step 4: Run test to verify it passes**

  Expected: 4+ tests pass.

- [ ] **Step 5: Commit**

---

## Task 11: Implement tyche-core config loader (TDD)

**What needs to be done?** Create `config.py` with `load_config()` and `load_config_with_defaults()` functions for loading JSON configuration with defaults for Nexus and Bus settings per section 6.1 of design spec.

**What problem does it resolve?** Core services need configurable endpoints, CPU affinity, HWM values; defaults ensure minimal config files work.

**Expected result?** Config loads from JSON, missing keys use defaults (e.g., `high_water_mark=10000`).

**Files:**
- Create: `tyche-core/tyche_core/config.py`
- Create: `tests/unit/test_core_config.py`

- [ ] **Step 1: Write failing test**

  Test cases:
  - `load_config(path)` loads valid JSON and returns dict
  - `load_config(path)` raises FileNotFoundError for missing file
  - `load_config_with_defaults(path)` merges user config with DEFAULT_CONFIG
  - Missing nested values use defaults (e.g., bus.high_water_mark defaults to 10000)

- [ ] **Step 2: Run test to verify it fails**

  Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_core.config'"

- [ ] **Step 3: Implement config module**

  Implement per design spec section 6.1:
  - `DEFAULT_CONFIG` dict with nested defaults for nexus, bus, launcher sections
  - `load_config(path)` opens file, parses JSON, returns dict
  - `load_config_with_defaults(path)` loads config, deep merges with defaults (user values override defaults)
  - `_deep_merge(base, override)` recursively merges nested dicts

- [ ] **Step 4: Run test to verify it passes**

  Expected: 3+ tests pass.

- [ ] **Step 5: Commit**

---

## Task 12: Implement tyche-core main entry point (TDD)

**What needs to be done?** Create `__main__.py` with argument parsing, logging setup, signal handling, and orchestration of Nexus and Bus services per section 3.1 of design spec.

**What problem does it resolve?** The core service needs a runnable entry point that loads config, starts services, and handles graceful shutdown.

**Expected result?** `python -m tyche_core --config config/core-config.json` starts Nexus and Bus, Ctrl+C shuts down gracefully.

**Files:**
- Create: `tyche-core/tyche_core/__main__.py`
- Create: `config/core-config.json`

- [ ] **Step 1: Write main entry point**

  Implement `main()` function:
  - Parse arguments: `--config` (default: config/core-config.json), `--log-level` (default: INFO)
  - Setup logging with format: `%(asctime)s - %(name)s - %(levelname)s - %(message)s`
  - `ensure_socket_dir(endpoint)` creates `/tmp/tyche/` directory if needed
  - Load config with `load_config_with_defaults()`
  - Create `Nexus` and `Bus` instances from config values
  - Register signal handlers for SIGINT/SIGTERM that stop services
  - Start Bus, then Nexus
  - Keep main thread alive with sleep loop
  - On shutdown, stop Nexus then Bus

- [ ] **Step 2: Create default config**

  Create `config/core-config.json` per design spec section 6.1 with:
  - nexus endpoint, cpu_core, heartbeat_interval_ms, heartbeat_timeout_ms
  - bus endpoints, cpu_core, high_water_mark
  - launcher enabled flag and config_path

- [ ] **Step 3: Test the entry point**

  ```bash
  cd tyche-core
  pip install -e .
  python -m tyche_core --help
  ```

  Expected: Help message displayed successfully.

- [ ] **Step 4: Commit**

---

## Task 13a: Implement Module base class - Core structure (TDD)

**What needs to be done?** Create the `Module` ABC with constructor, config loading, encode/decode helpers, and abstract lifecycle methods per section 7 of design spec.

**What problem does it resolve?** Modules need a common base class that handles configuration and provides the interface for lifecycle callbacks.

**Expected result?** TestModule can be instantiated, loads config, encode/decode roundtrips work.

**Files:**
- Create: `tyche-client/tyche_client/module.py` (core structure only)
- Create: `tests/unit/test_module.py`

- [ ] **Step 1: Write failing test**

  Test cases:
  - TestModule (subclass) can be instantiated with required endpoints
  - `service_name` class attribute is accessible
  - `_load_config()` loads JSON from config_path
  - `_encode(tick)` returns MessagePack bytes
  - `_decode(data)` returns Tick instance

- [ ] **Step 2: Run test to verify it fails**

  Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_client.module'"

- [ ] **Step 3: Implement Module base class (core structure)**

  Implement per design spec section 7:
  - `Module` ABC with class attributes: `service_name`, `service_version`
  - `__init__` parameters: nexus_endpoint, bus_xsub_endpoint, bus_xpub_endpoint, config_path, metrics_enabled, metrics_buffer_size
  - Instance attributes for config dict, correlation_id, assigned_id, running flag, initialized flag
  - ZMQ context and socket placeholders (None initially)
  - Logger named by service_name
  - `_load_config()` reads JSON from config_path if provided
  - `_encode(obj)` calls serialization.encode
  - `_decode(data)` calls serialization.decode
  - `_handlers` dict mapping type names to handler methods
  - Abstract methods: `on_init()`, `on_start()`, `on_stop()`
  - Default implementations: `on_reconfigure(new_config)`, `on_status()`, `on_tick(tick)`, `on_quote(quote)`, `on_trade(trade)`, `on_bar(bar)`, `on_order_event(event)`

- [ ] **Step 4: Run test to verify it passes**

  Expected: 3+ tests pass.

- [ ] **Step 5: Commit**

---

## Task 13b: Implement Module base class - Lifecycle and dispatch (TDD)

**What needs to be done?** Add registration with exponential backoff, heartbeat handling, command dispatch, message dispatch with corrupt payload handling, and the main run loop per section 7 of design spec.

**What problem does it resolve?** Modules need to register with Nexus, handle lifecycle commands, receive and dispatch Bus messages, and gracefully handle corrupt payloads.

**Expected result?** Module can register with Nexus, responds to START/STOP commands, dispatches incoming messages, handles corrupt payloads without crashing.

**Files:**
- Modify: `tyche-client/tyche_client/module.py` (add lifecycle methods)

- [ ] **Step 1: Write failing test for corrupt payload handling**

  Test case:
  - `_dispatch(topic, corrupt_data)` with invalid MessagePack bytes does not raise
  - Module remains operational after corrupt payload
  - Dropped message counter increments

- [ ] **Step 2: Run test to verify it fails**

  Expected: FAIL with AttributeError (method not found)

- [ ] **Step 3: Implement lifecycle and dispatch methods**

  Implement per design spec section 7:
  - `_register()` implements exponential backoff retry (max 20 attempts):
    - Send READY with JSON descriptor
    - Wait for ACK with 5 second timeout
    - Verify correlation_id matches to reject stale ACKs
    - On timeout, calculate backoff delay, sleep, retry
    - Return True on success, False on max retries exceeded
  - `_send_heartbeat()` sends HB with current timestamp_ns and correlation_id
  - `_handle_command(cmd_type, payload)` dispatches:
    - CMD_START: call on_start(), send REPLY OK
    - CMD_STOP: send REPLY OK, set running=False
    - CMD_RECONFIGURE: parse JSON, call on_reconfigure(), send REPLY OK/ERROR
    - CMD_STATUS: call on_status(), send REPLY OK
  - `_send_reply(status, message)` sends REPLY frame with correlation_id
  - `_handle_nexus_message(frames)` extracts CMD and dispatches
  - `_dispatch(topic, payload)` decodes MessagePack, looks up handler by type name, calls handler; on any exception logs error and increments dropped counter
  - `subscribe(topic_pattern)` sets SUB socket subscription
  - `publish(topic, obj)` encodes object and sends multipart message
  - `send_order(order)` publishes to "INTERNAL.OMS.ORDER" topic
  - `run()` main loop:
    - Load config
    - Create and connect DEALER (Nexus), PUB (Bus XSUB), SUB (Bus XPUB) sockets
    - Register with Nexus (return early if fails)
    - Set initialized flag, call on_init()
    - Set running flag, register sockets with poller
    - Poll loop: handle Nexus messages (commands), handle Bus messages (dispatch), send heartbeat at interval
    - On KeyboardInterrupt or stop, cleanup
  - `_cleanup()` sends DISCO, closes sockets, terminates context

- [ ] **Step 4: Run test to verify it passes**

  Expected: 4+ tests pass (including corrupt payload test).

- [ ] **Step 5: Commit**

---

## Task 14: Create example strategy

**What needs to be done?** Create a `momentum.py` strategy that extends `Module` and implements EMA crossover trading logic with configurable lookback and threshold per section 8 of design spec.

**What problem does it resolve?** Provides a working example demonstrating how to write a strategy using the Module base class.

**Expected result?** Running `python strategies/momentum.py --help` shows usage; strategy can be started and responds to market data.

**Files:**
- Create: `strategies/momentum.py`
- Create: `config/modules/momentum-config.json`

- [ ] **Step 1: Write example strategy**

  Implement per design spec section 8:
  - `MomentumStrategy(Module)` class:
    - `service_name = "strategy.momentum"`
    - Track fast_ma, slow_ma, position state
    - `on_init()`: subscribe to EQUITY.NYSE.*.Tick and Quote, load config for lookback and threshold
    - `on_start()`: log startup
    - `on_stop()`: log shutdown
    - `on_tick(tick)`: update EMAs with alpha=2/(period+1), generate signals when fast crosses slow ± threshold
    - `on_quote(quote)`: no-op (can be extended)
    - `_place_order(tick, side, qty)`: create Order and call send_order()
  - `main()` function:
    - Parse args: --nexus, --bus-xsub, --bus-xpub, --config, --log-level
    - Setup logging
    - Create strategy instance and call run()

- [ ] **Step 2: Create strategy config**

  Create `config/modules/momentum-config.json` per design spec section 6.2:
  - strategy.name, lookback_period, threshold
  - logging.level, logging.file

- [ ] **Step 3: Commit**

---

## Task 15: Integration test - Nexus registration

**What needs to be done?** Create integration tests verifying that a test module can register with Nexus, receive START command, and respond to STOP command per section 11 of design spec.

**What problem does it resolve?** End-to-end verification that the Nexus registration protocol and command dispatching work correctly.

**Expected result?** 3 tests pass: registration, START command receipt, STOP command receipt.

**Files:**
- Create: `tests/integration/test_nexus_registration.py`

- [ ] **Step 1: Write integration test**

  Create pytest module with:
  - `endpoints` fixture generating unique inproc endpoints per test
  - `core_services` fixture starting Nexus and Bus, yielding them, then stopping
  - `TestModule` class extending Module with flags for init_called, start_called, stop_called
  - `test_module_registers_with_nexus`: start TestModule in thread, assert it appears in nexus.get_modules()
  - `test_module_receives_start_command`: start module, get assigned_id, send START command, assert start_called
  - `test_module_receives_stop_command`: start module, get assigned_id, send STOP command, assert stop_called

- [ ] **Step 2: Run integration test**

  ```bash
  cd tyche-core && pip install -e .
  cd ../tyche-client && pip install -e .
  cd ..
  python -m pytest tests/integration/test_nexus_registration.py -v
  ```

  Expected: 3 PASSED

- [ ] **Step 3: Commit**

---

## Task 16: Integration test - Bus pub/sub

**What needs to be done?** Create integration tests verifying that messages flow correctly from publisher to subscriber through the Bus, including topic filtering per section 11 of design spec.

**What problem does it resolve?** End-to-end verification that the Bus XPUB/XSUB proxy forwards messages correctly and that subscribers receive only matching topics.

**Expected result?** 2 tests pass: message flow through Bus and topic filtering work correctly.

**Files:**
- Create: `tests/integration/test_bus_pubsub.py`

- [ ] **Step 1: Write integration test**

  Create pytest module with:
  - `endpoints` fixture generating unique inproc endpoints
  - `bus_service` fixture starting Bus, yielding it, then stopping
  - `test_pub_sub_message_flow`: create PUB and SUB sockets, connect to Bus, publish Tick, receive and verify
  - `test_topic_filtering`: create subscriber with AAPL filter, publish AAPL and MSFT ticks, verify only AAPL received

- [ ] **Step 2: Run integration test**

  ```bash
  python -m pytest tests/integration/test_bus_pubsub.py -v
  ```

  Expected: 2 PASSED

- [ ] **Step 3: Commit**

---

## Task 17: Create Makefile

**What needs to be done?** Create a Makefile with common development tasks: build, install, test, lint, format, clean, and run commands.

**What problem does it resolve?** Provides a consistent interface for common development operations across different developer environments.

**Expected result?** `make test` runs all tests, `make lint` checks code style, `make run-core` starts the core service.

**Files:**
- Create: `Makefile`

- [ ] **Step 1: Create Makefile**

  Add targets per design spec expectations:
  - `all` / `build` — install both packages
  - `build-core` / `build-client` — install individual packages
  - `test` / `test-unit` / `test-integration` — run pytest
  - `lint` / `lint-fix` — run ruff
  - `format` — run ruff format
  - `clean` — remove __pycache__, .pyc, egg-info
  - `run-core` — start core service with default config
  - `run-momentum` — start momentum strategy with core endpoints

- [ ] **Step 2: Commit**

---

## Task 18: Implement tyche-launcher package skeleton

**What needs to be done?** Create the `tyche-launcher` Python package with `pyproject.toml`, `__init__.py`, and a config loader for managing module lifecycle per section 3.3 of design spec.

**What problem does it resolve?** The launcher is a separate tool that manages module processes (start, monitor, restart) and needs its own installable package.

**Expected result?** Package installs successfully, config loader can parse launcher configuration files.

**Files:**
- Create: `tyche-launcher/pyproject.toml`
- Create: `tyche-launcher/tyche_launcher/__init__.py`
- Create: `tyche-launcher/tyche_launcher/config.py`

- [ ] **Step 1: Write pyproject.toml**

  Package metadata per design spec section 3.3:
  - Name: `tyche-launcher`
  - Version: `1.0.0`
  - Dependencies: `pyzmq>=25.0`, `msgpack>=1.0`, `tyche-core`, `tyche-client`
  - Console script: `tyche-launcher = tyche_launcher.__main__:main`

- [ ] **Step 2: Create config module**

  Implement per design spec section 3.3 and 6.3:
  - `ModuleConfig` dataclass: name, command (list), restart_policy, max_restarts, restart_window_seconds, cpu_core, environment
  - `LauncherConfig` dataclass: nexus_endpoint, poll_interval_ms, modules (list)
  - `load_launcher_config(path)` → LauncherConfig: load JSON, parse modules list, return config

- [ ] **Step 3: Commit**

---

## Task 19: Implement launcher monitor with circuit breaker (TDD)

**What needs to be done?** Create the `ProcessMonitor` and `CircuitBreaker` classes for tracking process state and preventing restart storms per section 3.3 of design spec.

**What problem does it resolve?** Modules may crash repeatedly due to configuration errors; the circuit breaker stops restart attempts after 3 failures in 60 seconds to prevent resource exhaustion.

**Expected result?** Circuit breaker opens after max failures, resets after window expires; ProcessMonitor tracks starts, exits, and restart counts.

**Files:**
- Create: `tyche-launcher/tyche_launcher/monitor.py`
- Create: `tests/unit/test_monitor.py`

- [ ] **Step 1: Write failing test**

  Test cases:
  - `CircuitBreaker(max_failures=3, window_seconds=60)` allows execution initially
  - `can_execute()` returns False after 3 failures recorded
  - `can_execute()` returns True after window expires
  - `ProcessMonitor(name)` tracks name and initial state
  - `record_start()` increments start_count
  - `record_exit(code)` tracks exit code and increments restart_count on subsequent starts

- [ ] **Step 2: Run test to verify it fails**

  Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_launcher.monitor'"

- [ ] **Step 3: Implement monitor module**

  Implement per design spec section 3.3:
  - `CircuitBreaker`:
    - `__init__` stores max_failures, window_seconds, initializes empty deque for failures
    - `can_execute()` cleans old failures, returns True if count < max_failures
    - `record_failure()` appends current timestamp
    - `record_success()` clears failure deque
    - `_cleanup_old_failures()` removes timestamps outside window
  - `ProcessMonitor`:
    - `__init__` stores name, restart_policy, max_restarts, window, initializes state
    - `record_start()` increments start_count, sets pid, updates last_start_time
    - `record_exit(code)` stores exit code, records failure if non-zero, success if zero
    - `is_healthy()` returns True if pid is not None
    - `should_restart()` applies policy: never/always/on-failure with circuit breaker check
    - `get_status()` returns dict with all state fields

- [ ] **Step 4: Run test to verify it passes**

  Expected: 5 tests pass.

- [ ] **Step 5: Commit**

---

## Task 20: Implement launcher process management (TDD)

**What needs to be done?** Create the `Launcher` class with process spawning, monitoring, restart policies, and the main entry point per section 3.3 of design spec.

**What problem does it resolve?** Provides complete module lifecycle management: starting processes, monitoring their health, applying restart policies, and graceful shutdown.

**Expected result?** Launcher can start configured modules, restart failed ones based on policy, and shut down all processes on SIGTERM.

**Files:**
- Create: `tyche-launcher/tyche_launcher/launcher.py`
- Create: `tyche-launcher/tyche_launcher/__main__.py`
- Create: `tests/unit/test_launcher.py`
- Create: `config/launcher-config.json`

- [ ] **Step 1: Write failing test**

  Test cases:
  - `Launcher(config)` creates instance with monitors for each module in config
  - `start()` starts all modules as subprocesses
  - `stop()` sends SIGTERM and waits for processes to exit
  - `poll()` detects exited processes and handles restarts per policy
  - `get_status()` returns status dict for all monitors

- [ ] **Step 2: Run test to verify it fails**

  Expected: FAIL with "ModuleNotFoundError: No module named 'tyche_launcher.launcher'"

- [ ] **Step 3: Implement launcher module**

  Implement per design spec section 3.3:
  - `Launcher`:
    - `__init__` stores config, creates ProcessMonitor for each module config
    - `start()` sets running flag, calls `_start_module()` for each config
    - `stop()` clears running flag, calls `_stop_module()` for each process
    - `_start_module(mod_config)` checks circuit breaker, creates subprocess.Popen with command/env, stores process, updates monitor
    - `_stop_module(name, process)` sends SIGTERM, waits 5s, kills if needed
    - `poll()` iterates processes, checks poll() status, records exit, handles restart if policy allows
    - `get_status()` returns dict of monitor statuses
    - `run()` calls start(), polls in loop until interrupted, calls stop()

- [ ] **Step 4: Create entry point**

  Create `__main__.py`:
  - `main()` parses --config and --log-level args
  - Setup logging
  - Load config with load_launcher_config()
  - Create Launcher and call run()
  - Return 0 on success, 1 on config error

- [ ] **Step 5: Create launcher config**

  Create `config/launcher-config.json` per design spec section 6.3:
  - nexus_endpoint, poll_interval_ms
  - modules list with momentum strategy configuration

- [ ] **Step 6: Run tests**

  ```bash
  cd tyche-launcher
  pip install -e .
  python -m pytest ../tests/unit/test_launcher.py -v
  ```

  Expected: 2+ PASSED

- [ ] **Step 7: Commit**

---

## Task 21: Final verification

**What needs to be done?** Run all unit tests, integration tests, and linting to verify the complete implementation is working correctly.

**What problem does it resolve?** Catches any regressions or integration issues before considering the implementation complete.

**Expected result?** All tests pass, linting shows no errors, all three packages (tyche-core, tyche-client, tyche-launcher) are installable and functional.

- [ ] **Step 1: Run all unit tests**

  ```bash
  python -m pytest tests/unit/ -v
  ```

  Expected: All tests pass

- [ ] **Step 2: Run all integration tests**

  ```bash
  python -m pytest tests/integration/ -v
  ```

  Expected: All tests pass

- [ ] **Step 3: Run linting**

  ```bash
  make lint
  ```

  Expected: No errors (or only minor warnings)

- [ ] **Step 4: Commit any fixes**

  ```bash
  git add -A
  git commit -m "fix: address linting issues" || echo "No fixes needed"
  ```

---

## Summary

This plan implements the complete pure-Python architecture for TycheEngine:

1. **tyche-core**: Nexus (ROUTER) + Bus (XPUB/XSUB) services with HWM configuration
2. **tyche-client**: Client library with types, serialization, Module base class, and socket helper
3. **tyche-launcher**: Process lifecycle manager with restart policies and circuit breaker
4. **IPC transport**: ZeroMQ over Unix domain sockets / named pipes with documented security considerations
5. **Protocol**: Binary wire protocol with MessagePack serialization and exponential backoff retry
6. **Example**: Momentum strategy demonstrating the API
7. **Tests**: Unit and integration tests for all major components

### Changes from original plan (incorporating eng review):

1. **Renamed `tyche-cli` → `tyche-client`** - Clearer distinction between library and CLI
2. **Added centralized socket address helper** - Single source of truth for IPC paths
3. **Added HWM configuration to Bus** - Configurable high-water-mark with overflow handling
4. **Added exponential backoff to Nexus registration** - Prevents thundering herd
5. **Added dropped message counter to Bus** - Observable backpressure metric
6. **Documented IPC security risk** - Phase 2 will add permission hardening
7. **Require context managers for ZMQ sockets** - Cleaner resource management
8. **Added corrupt payload test** - Graceful handling of malformed messages
9. **Added circuit breaker to launcher** - Prevents restart storms (3 failures in 60s → stop)
10. **Made LatencyStats buffer configurable** - `metrics_buffer_size` parameter
11. **Added Tasks 18-20 for launcher implementation** - Complete lifecycle management

### Task Size Compliance

All tasks are designed to be under 300 lines of code changes (excluding tests):
- Task 12 (Module base class) split into 12a (core structure) and 12b (lifecycle)
- Each task answers the three questions: What, Why, Expected result

After completing all tasks:
- `tyche-core` can be installed and run as a service
- `tyche-client` provides the base class for writing modules
- `tyche-launcher` manages module lifecycle with configurable restart policies
- Modules are completely separate processes with no shared code
- The architecture supports future evolution to native modules
