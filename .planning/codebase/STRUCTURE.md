# Directory Structure

*Generated: 2026-04-21*

```
D:\dev\TycheEngine
├── src/
│   ├── tyche/                    # Core engine framework
│   │   ├── __init__.py           # Package exports
│   │   ├── engine.py             # TycheEngine central broker
│   │   ├── engine_main.py        # Engine standalone entry point
│   │   ├── module.py             # TycheModule base class
│   │   ├── module_base.py        # Minimal ModuleBase
│   │   ├── module_main.py        # Module standalone entry point
│   │   ├── message.py            # MessagePack serialization
│   │   ├── heartbeat.py          # Paranoid Pirate heartbeat
│   │   ├── types.py              # Core types, enums, dataclasses
│   │   └── example_module.py     # Example module implementation
│   └── modules/                  # Domain-specific modules
│       ├── __init__.py
│       └── trading/              # Trading domain
│           ├── __init__.py
│           ├── events.py         # Event name constants & helpers
│           ├── clock/            # Time abstraction
│           │   ├── __init__.py
│           │   └── clock.py
│           ├── gateway/          # Exchange connectivity
│           │   ├── __init__.py
│           │   ├── base.py       # GatewayModule abstract base
│           │   ├── simulated.py  # Simulated exchange gateway
│           │   └── ctp/          # CTP futures gateway
│           │       ├── __init__.py
│           │       ├── gateway.py       # Base CTP gateway
│           │       ├── live.py          # Live broker gateway
│           │       ├── sim.py           # OpenCTP sim gateway
│           │       ├── config.py        # Config loader
│           │       ├── state_machine.py # Connection state machine
│           │       └── gateway_main.py  # Standalone runner
│           ├── models/           # Trading data models
│           │   ├── __init__.py
│           │   ├── enums.py      # Order/position enums
│           │   ├── order.py      # Order, Fill, OrderUpdate
│           │   ├── tick.py       # Quote, Trade, Bar
│           │   ├── position.py   # Position
│           │   ├── account.py    # Account, Balance
│           │   └── instrument.py # InstrumentId
│           ├── oms/              # Order Management System
│           │   ├── __init__.py
│           │   ├── module.py
│           │   └── order_store.py
│           ├── portfolio/        # Portfolio tracking
│           │   ├── __init__.py
│           │   └── module.py
│           ├── risk/             # Risk engine
│           │   ├── __init__.py
│           │   ├── module.py
│           │   └── rules.py
│           ├── store/            # Recording & replay
│           │   ├── __init__.py
│           │   ├── recorder.py
│           │   └── replay.py
│           └── strategy/         # Strategy framework
│               ├── __init__.py
│               ├── base.py       # StrategyModule abstract base
│               ├── context.py    # StrategyContext (order mgmt)
│               └── example_ma_cross.py
│
├── tests/
│   ├── conftest.py               # pytest path setup
│   ├── unit/                     # Unit tests (mock external deps)
│   │   ├── test_engine.py
│   │   ├── test_engine_main.py
│   │   ├── test_engine_threading.py
│   │   ├── test_example_module.py
│   │   ├── test_heartbeat.py
│   │   ├── test_heartbeat_protocol.py
│   │   ├── test_message.py
│   │   ├── test_module.py
│   │   ├── test_module_base.py
│   │   ├── test_module_main.py
│   │   ├── test_signal_handling.py
│   │   ├── test_types.py
│   │   ├── test_ctp_gateway.py
│   │   ├── test_ctp_gateway_enhanced.py
│   │   ├── test_ctp_state_machine.py
│   │   ├── test_ctp_config.py
│   │   └── test_gateway_main.py
│   ├── integration/              # Integration tests
│   │   ├── test_engine_module.py
│   │   └── test_multiprocess.py
│   ├── perf/                     # Performance tests (placeholder)
│   └── property/                 # Property tests (placeholder)
│
├── examples/                     # Usage examples & entry points
│   ├── run_engine.py
│   ├── run_module.py
│   ├── run_strategy.py
│   ├── run_gateway.py
│   ├── run_ctp_gateway.py
│   ├── run_trading_services.py
│   └── run_trading_system.py
│
├── tui/                          # TypeScript/React dashboard
│   ├── package.json
│   ├── tsconfig.json
│   └── README.md
│
├── docs/
│   ├── design/                   # Design specs
│   │   ├── tyche_engine_design_v1.md
│   │   └── openctp_gateway_design_v1.md
│   ├── plan/                     # Implementation plans
│   │   ├── tyche_engine_plan_v1.md
│   │   └── tyche_engine_plan_v2.md
│   ├── impl/                     # Implementation logs
│   │   ├── tyche_engine_implement_v2.md
│   │   └── openctp_gateway_implement_v1.md
│   └── review/                   # Review logs
│
├── data/recorded/                # Recorded market data
├── ctp_flow/                     # CTP API flow files (md/, td/)
├── resources/logo/               # Project logo assets
├── .github/workflows/            # CI/CD
│   ├── ci.yml
│   └── wiki-sync.yml
├── pyproject.toml                # Project config
├── README.md
└── CLAUDE.md                     # Agent cooperation guide
```

## Key Entry Points

| File | Purpose |
|------|---------|
| `src/tyche/engine_main.py` | Standalone engine process |
| `src/tyche/module_main.py` | Standalone module process |
| `examples/run_ctp_gateway.py` | CLI for running CTP gateway (sim or live) |
| `src/modules/trading/gateway/ctp/gateway_main.py` | Gateway builder from config file |

## Naming Conventions

- Core framework: `tyche.{component}` (e.g., `tyche.engine`)
- Trading modules: `modules.trading.{domain}` (e.g., `modules.trading.gateway`)
- Tests: `test_{module}.py` mirroring source structure
- Design docs: `{spec}_design_v{N}.md`
- Plans: `{spec}_plan_v{N}.md`
- Impl logs: `{spec}_implement_v{N}.md`
