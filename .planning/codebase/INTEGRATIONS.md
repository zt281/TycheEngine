# External Integrations

**Analysis Date:** 2026-05-14

## Messaging & IPC

**ZeroMQ - Primary Transport:**
- All inter-module communication uses ZeroMQ sockets
- Python: `pyzmq` (`src/tyche/engine.py`, `src/tyche/module.py`)
- Rust: `zmq` crate (`src/tyche/rust/src/module.rs`)
- C++: `cppzmq` header library (`src/tyche/cpp/module.cpp`)
- TypeScript: `zeromq` npm package (`tui/src/connection.ts`)
- Socket architecture:
  - `ROUTER` - Module registration (`registration_endpoint`)
  - `XPUB/XSUB` - Event broadcast proxy (`event_endpoint` / `event_sub_endpoint`)
  - `PUB` - Engine heartbeat broadcasts (`heartbeat_endpoint`)
  - `ROUTER` - Module heartbeat reception (`heartbeat_receive_endpoint`)
  - `ROUTER` - Job request/response routing (`job_endpoint`, default port 5564)
  - `ROUTER` - Admin queries (`admin_endpoint`, default port 5560)

**MessagePack - Wire Protocol:**
- Binary serialization for all messages across all language bindings
- Python: `msgpack` with custom `Decimal` encoder/decoder (`src/tyche/message.py`)
- Rust: `rmp-serde` (`src/tyche/rust/src/message.rs`)
- C++: `msgpack-c` (`src/tyche/cpp/module.cpp`)
- TypeScript: `@msgpack/msgpack` (`tui/src/connection.ts`)

## Data Storage

**ClickHouse (Optional):**
- Purpose: Event persistence and time-series analytics
- Docker compose: `docker/clickhouse-compose.yml`
- Python client: `clickhouse-connect>=0.7.0` (optional dependency, extras `persistence`)
- Ports: HTTP 8123, Native 9000
- Default database: `tyche`
- Authentication: default user, no password (development config)
- **Note:** No ClickHouse integration code detected in current source files - compose file is infrastructure-only

**File Storage:**
- Local filesystem only for configuration
- Process config: `tyche-processes.json` (TUI process manager)

**Caching:**
- In-memory topic queues with TTL-based GC (`src/tyche/engine.py`)
- Queue capacity: configurable (default 10,000)
- Backpressure strategies: `DROP_OLDEST`, `DROP_NEWEST`, `BLOCK_PRODUCER`

## Trading Venues

**CTP (China Futures):**
- Package: `openctp-ctp>=6.7.0` (optional extras: `ctp`)
- Research directory: `research/openctp/` (git submodule)
- Contains CTP API bindings for C/C#/Go/Java/Python/Rust
- Gateway implementations: CTP, EMT, FEMAS, IB, OST
- **Note:** No active CTP integration code in `src/` - research/development phase

**Binance (Cryptocurrency):**
- Research directory: `research/binance-connector-python/` and `research/binance-connector-rust/`
- Rust SDK: `binance-sdk` v48.0.1 with tokio/async support
- **Note:** Research dependencies only - not integrated into core engine

## Authentication & Identity

**Module Identity:**
- Custom `ModuleId` generator using Greek deity prefixes + 6-char hex suffix
- Deities: zeus, hera, poseidon, hades, apollo, artemis, ares, aphrodite, hermes, dionysus, demeter, hephaestus, hestia, example
- No external auth provider - self-generated IDs with registration handshake

## Monitoring & Observability

**Engine Admin Interface:**
- ZeroMQ ROUTER socket on port 5560 (default)
- Query commands: `STATUS`, `MODULES`, `QUEUES`, `STATS`
- Returns: msgpack-encoded response with engine state
- Consumed by: TycheTUI terminal interface

**TycheTUI - Terminal Dashboard:**
- Location: `tui/` (git submodule)
- Connects to engine admin/event/heartbeat endpoints
- Displays: module health, queue stats, event log, process manager
- Reconnection logic with exponential backoff

**Logging:**
- Python standard `logging` module
- No structured logging or external log aggregation detected

**Error Tracking:**
- None detected (no Sentry, Rollbar, etc.)

## CI/CD & Deployment

**Version Control:**
- Git with custom hooks at `.githooks/`
- Pre-push: runs `ruff check` and `mypy src`
- Submodules: 6 active (see STACK.md)

**CI Pipeline:**
- None detected (no GitHub Actions workflows, no `.github/workflows/`)

**Deployment:**
- Build target: Python wheel via hatchling
- Docker: ClickHouse only (`docker/clickhouse-compose.yml`)
- No containerization for the engine itself detected

## Environment Configuration

**No `.env` file detected.** Configuration is code-based.

**Runtime ports (defaults):**
| Service | Default Port | Config Location |
|---------|-------------|-----------------|
| Registration | 5555 | `Endpoint` constructor |
| Event XPUB | 5556 | `Endpoint` constructor |
| Event XSUB | 5557 | `event_endpoint.port + 1` |
| Heartbeat PUB | 5558 | `Endpoint` constructor |
| Heartbeat ROUTER | 5559 | `heartbeat_endpoint.port + 1` |
| Admin ROUTER | 5560 | `ADMIN_PORT_DEFAULT` |
| Job ROUTER | 5564 | `ADMIN_PORT_DEFAULT + 4` |

**TUI connection defaults** (`tui/src/types.ts`):
- host: `127.0.0.1`
- eventPort: `5556`
- heartbeatPort: `5558`
- adminPort: `5560`

## Webhooks & Callbacks

**Incoming:**
- None detected

**Outgoing:**
- None detected

## Integration Risks

**ZeroMQ:**
- All communication depends on ZMQ - network partition causes module expiration
- Heartbeat timeout: 3 missed beats (3 seconds) before module unregistered
- No TLS/encryption on ZMQ sockets detected

**ClickHouse:**
- Optional dependency - engine runs without persistence
- Docker compose uses empty password (development only)

**CTP/Binance:**
- Research-phase integrations - not wired into production code paths
- API keys/credentials would need secure storage when integrated

---

*Integration audit: 2026-05-14*
