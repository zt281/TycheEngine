# External Integrations

*Generated: 2026-04-21*

## Exchange / Venue Connectivity

### CTP (China Futures Market)

The primary external integration is CTP (Comprehensive Trading Platform), the standard API for Chinese futures exchanges.

**Library:** `openctp-ctp` (Python bindings for CTP v6.7.0+)

**Supported modes:**
- **Simulated** (`CtpSimGateway`) — Connects to OpenCTP free simulation servers (7x24 or regular-hours)
- **Live** (`CtpLiveGateway`) — Connects to real broker CTP front servers

**Exchanges supported via CTP:**
- CFFEX (China Financial Futures Exchange)
- SHFE (Shanghai Futures Exchange)
- DCE (Dalian Commodity Exchange)
- CZCE (Zhengzhou Commodity Exchange)
- INE (Shanghai International Energy Exchange)
- GFEX (Guangzhou Futures Exchange)

**Configuration:**
- JSON config file with CLI/env overrides
- Live mode requires: broker ID, user ID, password, TD front, MD front, optional auth code/app ID
- Sim mode requires: OpenCTP account credentials only

**Key files:**
- `src/modules/trading/gateway/ctp/gateway.py` — Base CTP gateway (SPI bridging)
- `src/modules/trading/gateway/ctp/live.py` — Live broker gateway
- `src/modules/trading/gateway/ctp/sim.py` — OpenCTP simulation gateway
- `src/modules/trading/gateway/ctp/config.py` — Config loader (JSON/env/CLI priority)
- `src/modules/trading/gateway/ctp/state_machine.py` — Connection state machine
- `src/modules/trading/gateway/ctp/gateway_main.py` — Standalone runner entry point

## CI / CD

**GitHub Actions:**
- `.github/workflows/ci.yml` — Lint (ruff), type check (mypy), unit tests across Python 3.9-3.12 on Ubuntu and Windows
- `.github/workflows/wiki-sync.yml` — Syncs repository wiki to GitHub Wiki

## Coverage Reporting

- Codecov integration via `codecov/codecov-action@v4`
- Coverage uploaded only on Ubuntu + Python 3.11 matrix job
