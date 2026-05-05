# Codebase Structure

**Analysis Date:** 2026-04-28

## Directory Layout

```
TycheEngine/
├── src/
│   ├── tyche/                    # Core engine framework (ZMQ broker + module base)
│   │   ├── engine.py             # TycheEngine central broker
│   │   ├── engine_main.py        # CLI entry point for engine process
│   │   ├── module.py             # TycheModule base class
│   │   ├── module_base.py        # Abstract ModuleBase with interface discovery
│   │   ├── example_module.py     # Reference module implementation (standalone runnable)
│   │   ├── message.py            # MessagePack serialization (Message, Envelope)
│   │   ├── heartbeat.py          # Paranoid Pirate heartbeat (Monitor, Sender, Manager)
│   │   └── types.py              # Core types (Endpoint, Interface, ModuleId, etc.)
│   └── modules/
│       └── trading/              # Trading domain modules
│           ├── events.py         # Event name constants and helpers
│           ├── models/           # Pure data models (no ZMQ dependency)
│           │   ├── __init__.py   # Re-exports all models
│           │   ├── enums.py      # Trading enumerations
│           │   ├── instrument.py # InstrumentId, Instrument
│           │   ├── order.py      # Order, Fill, OrderUpdate
│           │   ├── position.py   # Position
│           │   ├── tick.py       # Quote, Trade, Bar, OrderBook
│           │   └── account.py    # Account, Balance
│           ├── gateway/          # Exchange gateway modules
│           │   ├── base.py       # GatewayModule abstract base
│           │   ├── simulated.py  # Simulated/mock gateway
│           │   └── ctp/          # CTP (China futures) gateway
│           │       ├── gateway.py       # CtpGateway base class
│           │       ├── live.py          # CtpLiveGateway (real broker)
│           │       ├── sim.py           # CtpSimGateway (OpenCTP sim)
│           │       ├── state_machine.py # Connection state machine
│           │       ├── config.py        # CTP configuration
│           │       └── gateway_main.py  # CLI entry point
│           ├── oms/              # Order Management System
│           │   ├── module.py     # OMSModule
│           │   └── order_store.py # In-memory order state machine
│           ├── risk/             # Pre-trade risk management
│           │   ├── module.py     # RiskModule
│           │   └── rules.py      # RiskRule engine and concrete rules
│           ├── portfolio/        # Position tracking and P&L
│           │   └── module.py     # PortfolioModule
│           ├── strategy/         # Strategy framework
│           │   ├── base.py       # StrategyModule abstract base
│           │   ├── context.py    # StrategyContext (market state + order ops)
│           │   └── example_ma_cross.py # Example strategy
│           ├── persistence/      # Event storage backends
│           │   ├── backend.py    # PersistenceBackend abstract base
│           │   ├── clickhouse_backend.py
│           │   ├── jsonl_backend.py
│           │   └── schema.py     # ClickHouse DDL
│           ├── store/            # Recording and replay
│           │   ├── recorder.py   # DataRecorderModule
│           │   └── replay.py     # ReplayModule (backtesting)
│           └── clock/            # Time synchronization
│               └── clock.py      # LiveClockModule, SimulatedClock
├── tests/
│   ├── conftest.py               # pytest config (adds src/ to sys.path)
│   ├── unit/                     # Unit tests (>=80% coverage target)
│   │   ├── test_engine.py
│   │   ├── test_engine_main.py
│   │   ├── test_engine_threading.py
│   │   ├── test_module.py
│   │   ├── test_module_base.py
│   │   ├── test_example_module.py
│   │   ├── test_message.py
│   │   ├── test_types.py
│   │   ├── test_heartbeat.py
│   │   ├── test_heartbeat_protocol.py
│   │   ├── test_gateway_main.py
│   │   ├── test_simulated_gateway.py
│   │   ├── test_ctp_gateway.py
│   │   ├── test_ctp_gateway_enhanced.py
│   │   ├── test_ctp_state_machine.py
│   │   ├── test_ctp_config.py
│   │   ├── test_oms_module.py
│   │   ├── test_order_store.py
│   │   ├── test_portfolio_module.py
│   │   ├── test_risk_rules.py
│   │   ├── test_strategy_context.py
│   │   ├── test_data_recorder.py
│   │   ├── test_backend.py
│   │   ├── test_clickhouse_backend_unit.py
│   │   ├── test_jsonl_backend.py
│   │   ├── test_schema.py
│   │   └── test_signal_handling.py
│   └── integration/              # Integration tests
│       ├── test_engine_module.py
│       ├── test_multiprocess.py
│       ├── test_trading_pipeline.py
│       ├── test_clickhouse_backend.py
│       └── test_message_queue_perf.py
├── docs/
│   ├── design/                   # Design specifications
│   ├── plan/                     # Implementation plans
│   ├── review/                   # Review logs
│   └── impl/                     # Implementation logs
├── examples/                     # Usage examples
├── docker/                       # Docker configurations
├── resources/                    # Static resources (logo, etc.)
├── pyproject.toml                # Project config, dependencies, tool settings
├── README.md                     # Project documentation
└── .planning/                    # Planning artifacts
    └── codebase/                 # Codebase analysis documents
```

## Directory Purposes

**`src/tyche/`: Core Framework**
- Purpose: The engine broker and module base classes
- Contains: ZMQ socket management, message serialization, heartbeat protocol, type definitions
- Key files:
  - `src/tyche/engine.py`: Central broker with 6 worker threads
  - `src/tyche/module.py`: Module base with PUB/SUB/DEALER sockets
  - `src/tyche/message.py`: MessagePack serialization with Decimal support
  - `src/tyche/types.py`: All core dataclasses and enums
- This directory has NO trading-domain knowledge

**`src/modules/trading/`: Trading Domain**
- Purpose: All trading-specific business logic
- Contains: Models, gateways, OMS, risk, portfolio, strategy, persistence, clock
- Key files:
  - `src/modules/trading/events.py`: Event naming convention constants
  - `src/modules/trading/models/`: Pure data models (serializable, no ZMQ)
  - `src/modules/trading/gateway/`: Exchange connectivity
  - `src/modules/trading/oms/`: Order lifecycle management
  - `src/modules/trading/risk/`: Pre-trade risk validation
  - `src/modules/trading/portfolio/`: Position tracking
  - `src/modules/trading/strategy/`: Strategy framework
  - `src/modules/trading/persistence/`: Event storage
  - `src/modules/trading/store/`: Recording and replay
  - `src/modules/trading/clock/`: Time synchronization

**`tests/unit/`: Unit Tests**
- Purpose: Fast, isolated tests with mocked dependencies
- Contains: 29 test files covering all major components
- Target: >=80% line coverage, run in <5 seconds per the project spec
- No `__init__.py` files (pytest handles discovery)

**`tests/integration/`: Integration Tests**
- Purpose: Cross-component tests with real ZeroMQ sockets
- Contains: 5 test files for engine+module interaction, trading pipeline, message queue performance
- May use real ZeroMQ sockets per the project spec

## Key File Locations

**Entry Points:**
- `src/tyche/engine_main.py`: Start the central broker process
- `examples/run_module.py`: Start a module process (uses ExampleModule)
- `src/modules/trading/gateway/ctp/gateway_main.py`: Start a CTP gateway process

**Configuration:**
- `pyproject.toml`: Project metadata, dependencies, pytest/mypy/ruff/coverage settings
- `src/modules/trading/gateway/ctp/config.py`: CTP-specific configuration

**Core Logic:**
- `src/tyche/engine.py`: Message broker, module registry, event proxy
- `src/tyche/module.py`: Module lifecycle, socket management, event dispatch
- `src/modules/trading/oms/module.py`: Order routing and fill processing
- `src/modules/trading/risk/module.py`: Pre-trade risk gate
- `src/modules/trading/portfolio/module.py`: Position tracking

**Testing:**
- `tests/conftest.py`: pytest configuration (adds `src/` to `sys.path`)
- `tests/unit/test_engine.py`: Engine unit tests
- `tests/integration/test_trading_pipeline.py`: End-to-end trading flow tests

## Naming Conventions

**Files:**
- Module files: `module.py` (when directory is the module name)
- Base classes: `base.py`
- Entry points: `{module}_main.py`
- Tests: `test_{module}.py`

**Directories:**
- Framework: `tyche/` (lowercase, no prefix)
- Domain modules: `modules/trading/{domain}/` (kebab-case would be used if needed)
- Tests mirror source structure by component name, not by path

**Classes:**
- Engine/broker: `TycheEngine`
- Module base: `TycheModule` / `ModuleBase`
- Domain modules: `{Domain}Module` (e.g., `OMSModule`, `RiskModule`, `PortfolioModule`)
- Models: Noun form (e.g., `Order`, `Fill`, `Position`, `Quote`)
- Abstract bases: `{Name}Module` or `{Name}Backend`

**Event Topics:**
- Market data: `quote.{instrument_id}`, `trade.{instrument_id}`, `bar.{instrument_id}.{timeframe}`
- Order flow: `order.submit`, `order.approved`, `order.rejected`, `order.execute`, `order.cancel`, `order.update`
- Fills: `fill.{instrument_id}`
- Portfolio: `position.update`, `account.update`
- Risk: `risk.alert`
- System: `system.clock`, `system.shutdown`

## Where to Add New Code

**New Trading Module (e.g., new risk type, new strategy):**
- Implementation: `src/modules/trading/{domain}/module.py`
- Base class: `src/modules/trading/{domain}/base.py` (if needed)
- Tests: `tests/unit/test_{domain}_module.py`

**New Gateway (e.g., Binance, IB):**
- Implementation: `src/modules/trading/gateway/{venue}/gateway.py`
- Inherit from: `src/modules/trading/gateway/base.py` (`GatewayModule`)
- Config: `src/modules/trading/gateway/{venue}/config.py`
- Tests: `tests/unit/test_{venue}_gateway.py`

**New Domain Model:**
- Implementation: `src/modules/trading/models/{model_name}.py`
- Export: Add to `src/modules/trading/models/__init__.py`
- Tests: `tests/unit/test_{model_name}.py` or add to existing model test

**New Persistence Backend:**
- Implementation: `src/modules/trading/persistence/{backend_name}_backend.py`
- Inherit from: `src/modules/trading/persistence/backend.py` (`PersistenceBackend`)
- Tests: `tests/unit/test_{backend_name}_backend.py`

**New Risk Rule:**
- Implementation: `src/modules/trading/risk/rules.py` (add class inheriting `RiskRule`)
- Tests: `tests/unit/test_risk_rules.py`

**New Strategy:**
- Implementation: `src/modules/trading/strategy/{strategy_name}.py`
- Inherit from: `src/modules/trading/strategy/base.py` (`StrategyModule`)
- Tests: `tests/unit/test_{strategy_name}.py`

**Utilities/Helpers:**
- Shared helpers: Add to the relevant domain directory or create `src/modules/trading/utils/` if cross-cutting

## Special Directories

**`.planning/`: Planning Artifacts**
- Purpose: Contains codebase analysis and phase planning documents
- Generated: No (manually maintained)
- Committed: Yes

**`docs/`: Project Documentation**
- Purpose: Design specs, implementation plans, review logs
- Subdirectories: `design/`, `plan/`, `review/`, `impl/`
- Generated: No (manually maintained per the project process)
- Committed: Yes

**`examples/`: Usage Examples**
- Purpose: Standalone example scripts demonstrating engine usage
- Generated: No
- Committed: Yes

**`docker/`: Container Configurations**
- Purpose: Dockerfiles and compose files for deployment
- Generated: No
- Committed: Yes

---

*Structure analysis: 2026-04-28*
