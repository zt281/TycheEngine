# Architecture

**Analysis Date:** 2026-04-28

## Pattern Overview

**Overall:** Distributed event-driven architecture with a central message broker (TycheEngine) and pluggable modules communicating via ZeroMQ pub/sub and request/reply patterns.

**Key Characteristics:**
- **Central broker model:** A single `TycheEngine` process acts as the message broker, routing events between modules
- **Multi-process by design:** Each module runs in its own process for fault isolation; the engine runs in a separate process
- **Topic-based pub/sub:** Events are routed by topic string (e.g., `quote.BTCUSDT.binance.crypto`, `order.submit`)
- **Interface pattern discovery:** Modules declare their event handlers using naming conventions (`on_*`, `ack_*`, `whisper_*`, `on_common_*`)
- **Heartbeat-based liveness:** Paranoid Pirate Pattern for detecting and removing dead modules

## Layers

### Engine Layer (Broker)
- **Purpose:** Central message broker, module registry, heartbeat monitor, admin interface
- **Location:** `src/tyche/engine.py`
- **Contains:** `TycheEngine` class
- **Depends on:** ZeroMQ (pyzmq), msgpack, threading
- **Used by:** All modules connect to the engine

**Worker threads in the engine:**
| Thread | Socket Type | Purpose |
|--------|-------------|---------|
| registration | ROUTER | Module registration (REQ/REP handshake) |
| event_proxy | XPUB/XSUB | Event distribution between publishers and subscribers |
| heartbeat | PUB | Broadcast engine heartbeats to all modules |
| hb_recv | ROUTER | Receive heartbeats from modules |
| monitor | (internal) | Check module liveness, unregister expired modules |
| admin | ROUTER | Respond to STATUS/MODULES/STATS queries |

### Module Layer (Base Framework)
- **Purpose:** Base classes and communication primitives for all modules
- **Location:** `src/tyche/`
- **Contains:**
  - `ModuleBase` (`module_base.py`) -- Abstract base with interface discovery via naming convention
  - `TycheModule` (`module.py`) -- Concrete base with ZMQ socket management, registration, event dispatch
  - `Message`/`Envelope` (`message.py`) -- MessagePack serialization with Decimal support
  - `HeartbeatManager`/`HeartbeatMonitor` (`heartbeat.py`) -- Paranoid Pirate pattern implementation
  - `types.py` -- Core types: `ModuleId`, `InterfacePattern`, `DurabilityLevel`, `MessageType`, `Endpoint`, `Interface`, `ModuleInfo`
- **Depends on:** ZeroMQ, msgpack
- **Used by:** All trading modules (Gateway, OMS, Risk, Strategy, Portfolio, etc.)

### Trading Domain Layer
- **Purpose:** Trading-specific models, events, and business logic
- **Location:** `src/modules/trading/`
- **Contains:** Domain models, gateway abstractions, OMS, risk, portfolio, strategy, persistence, clock
- **Depends on:** Module layer (`tyche.*`)
- **Used by:** Application-level modules

### Model Layer (Pure Data)
- **Purpose:** Immutable-ish dataclasses for trading domain entities
- **Location:** `src/modules/trading/models/`
- **Contains:**
  - `InstrumentId`, `Instrument` (`instrument.py`)
  - `Order`, `Fill`, `OrderUpdate` (`order.py`)
  - `Position` (`position.py`)
  - `Quote`, `Trade`, `Bar`, `OrderBook` (`tick.py`)
  - `Account`, `Balance` (`account.py`)
  - Enums: `Side`, `OrderType`, `OrderStatus`, `TimeInForce`, `VenueType`, `AssetClass`, `Offset`, `PositionSide` (`enums.py`)
- **Key pattern:** All models implement `to_dict()` / `from_dict()` for serialization round-trips; `Decimal` is used for all monetary values
- **No ZMQ dependency:** Pure data classes, serializable to dict

### Gateway Layer
- **Purpose:** Bridge external exchange APIs to the internal event system
- **Location:** `src/modules/trading/gateway/`
- **Contains:**
  - `GatewayModule` (`base.py`) -- Abstract base for all exchange gateways
  - `SimulatedGateway` (`simulated.py`) -- Mock gateway for testing
  - `CtpGateway` (`ctp/gateway.py`) -- CTP (China futures) gateway with OpenCTP
  - `ConnectionStateMachine` (`ctp/state_machine.py`) -- Auto-reconnect with exponential backoff
- **Pattern:** Each venue runs in its own process; SPI callbacks from CTP are bridged via `queue.Queue` to the module's event dispatcher thread

### Order Management Layer
- **Purpose:** Order lifecycle management and routing
- **Location:** `src/modules/trading/oms/`
- **Contains:**
  - `OMSModule` (`module.py`) -- Receives approved orders, routes to gateways, processes fills
  - `OrderStore` (`order_store.py`) -- Thread-safe in-memory order store with state machine validation

### Risk Layer
- **Purpose:** Pre-trade risk validation
- **Location:** `src/modules/trading/risk/`
- **Contains:**
  - `RiskModule` (`module.py`) -- Synchronous gate: receives `order.submit`, publishes `order.approved` or `order.rejected`
  - `RiskRuleEngine`, `RiskRule` base, concrete rules (`rules.py`) -- Max position size, max order value, max daily loss, rate limit

### Portfolio Layer
- **Purpose:** Position tracking and P&L calculation
- **Location:** `src/modules/trading/portfolio/`
- **Contains:** `PortfolioModule` (`module.py`) -- Tracks positions from fills, calculates realized/unrealized P&L, broadcasts `position.update`

### Strategy Layer
- **Purpose:** Trading strategy implementation framework
- **Location:** `src/modules/trading/strategy/`
- **Contains:**
  - `StrategyModule` (`base.py`) -- Abstract base with callback hooks (`on_quote`, `on_trade`, `on_bar`, `on_fill`, etc.)
  - `StrategyContext` (`context.py`) -- Runtime context providing market state and order submission
  - `ExampleMACross` (`example_ma_cross.py`) -- Example implementation

### Persistence Layer
- **Purpose:** Event storage and retrieval
- **Location:** `src/modules/trading/persistence/`
- **Contains:**
  - `PersistenceBackend` (`backend.py`) -- Abstract base with `InsertResult`/`QueryResult`
  - `ClickHouseBackend` (`clickhouse_backend.py`) -- ClickHouse persistence
  - `JsonlBackend` (`jsonl_backend.py`) -- JSON Lines file backend
  - `SchemaManager` (`schema.py`) -- ClickHouse DDL and schema versioning

### Store Layer (Recorder/Replay)
- **Purpose:** Data recording for later replay/backtesting
- **Location:** `src/modules/trading/store/`
- **Contains:**
  - `DataRecorderModule` (`recorder.py`) -- Subscribes to events, writes JSONL files
  - `ReplayModule` (`replay.py`) -- Reads JSONL files, replays events with simulated clock

### Clock Layer
- **Purpose:** Time synchronization across modules
- **Location:** `src/modules/trading/clock/`
- **Contains:**
  - `LiveClockModule` (`clock.py`) -- Broadcasts wall-clock time
  - `SimulatedClock` (`clock.py`) -- Deterministic time for backtesting

## Data Flow

### Order Submission Flow

```
StrategyModule
    -> submit_order() via StrategyContext
    -> send_event("order.submit", order_dict)
    -> TycheEngine XPUB/XSUB proxy
    -> RiskModule (ack_order_submit handler)
       -> Evaluates risk rules
       -> If approved: send_event("order.approved", order_dict)
       -> If rejected: send_event("order.rejected", {...})
    -> TycheEngine proxy
    -> OMSModule (on_order_approved handler)
       -> Stores order in OrderStore
       -> Routes to gateway: send_event("ack_order_execute_{venue}", order_dict)
    -> TycheEngine proxy
    -> GatewayModule (ack_order_execute_{venue} handler)
       -> Calls venue API (submit_order)
       -> Publishes fill events or order updates
```

### Market Data Flow

```
GatewayModule (external API)
    -> SPI callback on CTP thread
    -> queue.Queue bridge
    -> _event_dispatcher thread
    -> publish_quote() / publish_trade()
    -> send_event("quote.{instrument_id}", quote_dict)
    -> TycheEngine XPUB/XSUB proxy
    -> StrategyModule (on_quote handler)
    -> DataRecorderModule (on_quote handler - optional)
    -> PortfolioModule (on_quote handler - optional, for mark-to-market)
```

### Fill Processing Flow

```
GatewayModule
    -> OnRtnTrade SPI callback
    -> queue.Queue bridge
    -> publish_fill()
    -> send_event("fill.{instrument_id}", fill_dict)
    -> TycheEngine proxy
    -> OMSModule (on_fill handler)
       -> OrderStore.apply_fill()
       -> _publish_order_update()
    -> PortfolioModule (on_fill handler)
       -> Position.apply_fill()
       -> _publish_position_update()
    -> StrategyModule (on_order_update / on_position_update handlers)
```

## State Management

**No global shared state.** Each module maintains its own state:
- `TycheEngine`: Module registry, interface routing table, heartbeat monitors
- `OrderStore`: In-memory order state machine (thread-safe with `threading.Lock`)
- `PortfolioModule`: Position dictionary
- `StrategyContext`: Latest quotes, bars, positions per instrument
- `RiskModule`: Risk context (positions, daily P&L, order counts)

State is synchronized via events, not shared memory.

## Key Abstractions

### Interface Patterns

Modules declare handlers using naming conventions discovered by `ModuleBase.discover_interfaces()`:

| Pattern | Prefix | Semantics | Example |
|---------|--------|-----------|---------|
| ON | `on_` | Fire-and-forget, load-balanced | `on_quote.BTCUSDT.binance.crypto` |
| ACK | `ack_` | Request-response, must reply | `ack_order_submit` |
| WHISPER | `whisper_` | Direct P2P to target module | `whisper_athena_message` |
| ON_COMMON | `on_common_` | Broadcast to ALL subscribers | `on_common_position.update` |

### Message Durability

`DurabilityLevel` controls persistence guarantees:
- `BEST_EFFORT` (0): No persistence guarantee
- `ASYNC_FLUSH` (1): Async write (default)
- `SYNC_FLUSH` (2): Sync write, confirmed

### Module ID Generation

`ModuleId.generate(deity)` produces IDs like `athena3f2a1b` using Greek deity names + 6-char hex suffix.

### Instrument ID Format

`symbol.venue.asset_class` -- e.g., `BTCUSDT.binance.crypto`, `IF2406.ctp.futures`, `rb2410.ctp.futures`

## Entry Points

### Engine Entry Point
- **Location:** `src/tyche/engine_main.py`
- **Triggers:** CLI invocation (`python -m tyche.engine_main`)
- **Responsibilities:** Parse args, create `TycheEngine`, bind sockets, run event loop, handle SIGINT/SIGTERM

### Module Entry Point
- **Location:** `src/tyche/module_main.py`
- **Triggers:** CLI invocation (`python -m tyche.module_main`)
- **Responsibilities:** Parse args, create `ExampleModule`, connect to engine, run event loop

### CTP Gateway Entry Point
- **Location:** `src/modules/trading/gateway/ctp/gateway_main.py`
- **Triggers:** CLI invocation for CTP-specific gateway process
- **Responsibilities:** Parse CTP config, create `CtpGateway` (live or sim), connect to engine

## Error Handling

**Strategy:** Per-module logging with structured error events for cross-module visibility.

**Patterns:**
- Gateway errors publish `gateway.error` events via the engine
- CTP gateway uses `ConnectionStateMachine` with auto-reconnect and exponential backoff
- Order state transitions are validated in `OrderStore` against `_VALID_TRANSITIONS`
- Risk rule exceptions are caught and treated as rule failures (order rejected)
- All ZMQ socket operations set `LINGER=0` for clean shutdown

## Cross-Cutting Concerns

**Logging:** Standard Python `logging` module. Each module/class creates its own logger.

**Validation:**
- Order state transitions validated in `OrderStore`
- Risk rules evaluated synchronously before order approval
- CTP connection state machine validates state transitions

**Authentication:**
- CTP gateway: Broker ID, user ID, password, optional auth code + app ID
- No engine-level auth; modules trust the local network

**Serialization:**
- MessagePack with custom Decimal encoder/decoder (`message.py`)
- All domain models implement `to_dict()`/`from_dict()`
- Decimal precision preserved through encode/decode round-trips

**Threading:**
- Engine: 6 daemon threads (registration, heartbeat send, heartbeat receive, monitor, event proxy, admin)
- Module: 2 daemon threads (event receiver, heartbeat sender) + registration is one-shot
- CTP gateway: Additional dispatcher thread + SPI callbacks run on CTP internal threads
- All shared state protected with `threading.Lock`

---

*Architecture analysis: 2026-04-28*
