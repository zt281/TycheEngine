# External Integrations

**Analysis Date:** 2026-04-28

## APIs & External Services

**CTP (Comprehensive Transaction Platform) - Futures Trading:**
- Purpose: Connect to Chinese futures exchanges (CFFEX, SHFE, DCE, CZCE, INE, GFEX)
- SDK: `openctp-ctp>=6.7.0` (imported as `openctp_ctp.mdapi` and `openctp_ctp.tdapi`)
- Implementation: `src/modules/trading/gateway/ctp/gateway.py`
- Two modes:
  - **Simulated** (`CtpSimGateway`): OpenCTP free simulation servers (`src/modules/trading/gateway/ctp/sim.py`)
  - **Live** (`CtpLiveGateway`): Real broker frontends (`src/modules/trading/gateway/ctp/live.py`)
- Auth: Broker-assigned `user_id`, `password`, `broker_id`; optional `auth_code` + `app_id` for live brokers
- Exchange mapping: `EXCHANGE_MAP` in `gateway.py` maps instrument prefixes to exchange IDs

**Simulated Exchange (Internal):**
- Purpose: Development/testing without real exchange connection
- Implementation: `src/modules/trading/gateway/simulated.py`
- Generates synthetic random-walk market data and simulated order fills

## Data Storage

**Databases:**
- **ClickHouse** - Primary production persistence backend
  - Client: `clickhouse-connect>=0.7.0`
  - Implementation: `src/modules/trading/persistence/clickhouse_backend.py`
  - Schema: `src/modules/trading/persistence/schema.py`
  - Table: `events` (MergeTree, partitioned by day)
  - Docker: `docker/clickhouse-compose.yml` (image `clickhouse/clickhouse-server:24`)
  - Connection: Configurable host/port/user/password; defaults to `localhost:8123`

- **JSONL (File-based)** - Dev/test fallback backend
  - Implementation: `src/modules/trading/persistence/jsonl_backend.py`
  - Layout: `{data_dir}/{date}/events.jsonl`
  - No external dependencies

**File Storage:**
- Local filesystem for JSONL backend and DataRecorderModule (`src/modules/trading/store/recorder.py`)
- Date-partitioned directories under `./data/recorded/`

**Caching:**
- None detected. No Redis, Memcached, or similar caching layer.

## Authentication & Identity

**CTP Gateway Authentication:**
- Type: Broker-specific credential-based
- Credentials stored in: JSON config files + environment variables (`TYCHE_GATEWAY_*`)
- Live mode requires: `broker_id`, `user_id`, `password`, `td_front`, `md_front`
- Optional: `auth_code` and `app_id` for brokers requiring app authentication
- Sim mode requires: `user_id`, `password` only (OpenCTP public servers)

**Module Identity:**
- Type: Self-generated random IDs
- Format: `{deity_name}{6-char hex}` (e.g., `zeus3a7f2b`)
- Implementation: `ModuleId.generate()` in `src/tyche/types.py`

## Messaging & Protocols

**ZeroMQ:**
- Protocol: TCP (intra-machine and cross-machine)
- Patterns used:
  - REQ-ROUTER: Module registration and interface discovery
  - XPUB/XSUB: Event broadcasting (pub-sub)
  - DEALER-ROUTER: Direct P2P "whisper" messaging
  - PUSH-PULL: Load-balanced work distribution
  - PUB-SUB: Heartbeat monitoring (Paranoid Pirate pattern)
- Port conventions: Registration 5555, Events 5556, Heartbeat 5559, Admin 5560

**MessagePack:**
- Format: Binary serialization for all ZMQ payloads
- Custom hooks: Decimal (via `__decimal__` tag), Enum (via `.value`), bytes (UTF-8 decode)
- Implementation: `src/tyche/message.py`

**CTP Protocol:**
- Format: CTP's native C++ API via Python bindings (`openctp_ctp`)
- Two APIs: MdAPI (market data), TdAPI (trading)
- Async callback pattern: SPI callbacks bridged via `queue.Queue` to module event thread

## Monitoring & Observability

**Error Tracking:**
- None detected. No Sentry, Rollbar, or similar service.
- Errors logged via Python `logging` module.

**Logs:**
- Python standard `logging` module
- Heartbeat monitoring for module liveness (Paranoid Pirate pattern)
- Backend health checks (`health()` method on persistence backends)

**Metrics:**
- None detected. No Prometheus, StatsD, or similar.

## CI/CD & Deployment

**Hosting:**
- Not specified. Designed for self-hosted deployment.

**CI Pipeline:**
- Platform: GitHub Actions (`.github/workflows/ci.yml`)
- Jobs:
  - Lint: ruff + mypy on Python 3.11
  - Test: pytest unit tests on matrix (ubuntu-latest, windows-latest) x (Python 3.9-3.12)
  - Coverage: codecov upload from ubuntu-latest + Python 3.11
- Timeout: 5 minutes per test job

**Wiki Sync:**
- Platform: GitHub Actions (`.github/workflows/wiki-sync.yml`)
- Syncs `.qoder/repowiki/en/content/*.md` to GitHub Wiki on push to main

## Environment Configuration

**Required env vars (CTP Gateway):**
- `TYCHE_GATEWAY_USER_ID` - OpenCTP sim account
- `TYCHE_GATEWAY_PASSWORD` - OpenCTP sim password
- `TYCHE_GATEWAY_BROKER_ID` - Broker ID (default: 9999)
- `TYCHE_GATEWAY_LIVE_USER_ID` - Live broker account
- `TYCHE_GATEWAY_LIVE_PASSWORD` - Live broker password
- `TYCHE_GATEWAY_LIVE_BROKER_ID` - Live broker ID
- `TYCHE_GATEWAY_LIVE_TD_FRONT` - Trading frontend address
- `TYCHE_GATEWAY_LIVE_MD_FRONT` - Market data frontend address
- `TYCHE_GATEWAY_LIVE_AUTH_CODE` - Broker auth code (optional)
- `TYCHE_GATEWAY_LIVE_APP_ID` - Registered app ID (optional)

**Secrets location:**
- CTP credentials: JSON config files or environment variables (never committed)
- Codecov token: GitHub secret (`CODECOV_TOKEN`)

## Webhooks & Callbacks

**Incoming:**
- None detected

**Outgoing:**
- None detected

## Data Exchange Formats

**Internal Events:**
- Format: MessagePack-serialized `Message` dataclass
- Structure: `msg_type`, `sender`, `event`, `payload`, `recipient`, `durability`, `timestamp`, `correlation_id`
- Decimal precision preserved via custom encoder/decoder

**Trading Models:**
- All models have `to_dict()` / `from_dict()` methods for serialization
- Decimal values serialized as strings to preserve precision
- Enum values serialized as names (strings)
- Files: `src/modules/trading/models/order.py`, `tick.py`, `position.py`, `account.py`, `instrument.py`

**Persistence:**
- ClickHouse: Base64-encoded payload in String column, DateTime64(3) timestamps
- JSONL: JSON lines with string-encoded Decimal values

---

*Integration audit: 2026-04-28*
