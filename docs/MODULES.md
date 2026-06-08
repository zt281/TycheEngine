# TycheEngine Modules Documentation

## Overview

The `feature/new_design` branch introduces three domain-specific modules for China futures/options trading:

| Module | Path | Purpose |
|--------|------|---------|
| **OpenCTP Gateway** | `src/modules/openctp_gateway/` | Connects to CTP/TTS trading front, subscribes to market data, publishes `quote` events |
| **Static Data** | `src/modules/static_data/` | Fetches and caches exchange metadata; answers queries via job handlers |
| **Greeks Engine** | `src/modules/greeks_engine/` | Computes real-time option Greeks (IV, delta, gamma, vega, theta, rho) |

All modules extend `TycheModule` (`src/tyche/module.py`) and communicate with `TycheEngine` via ZeroMQ.

---

## Architecture

```
                    +------------------+
                    |   TycheEngine    |
                    |  (ZeroMQ broker) |
                    +--------+---------+
                             |
         +-------------------+-------------------+
         |                   |                   |
         v                   v                   v
+--------+--------+ +--------+--------+ +--------+--------+
| OpenCTP Gateway | |   Static Data   | |  Greeks Engine  |
|  (quote producer) |  (query service)  | (greeks producer) |
+-----------------+ +-----------------+ +-----------------+
         |                   ^                   |
         |                   | (job: query_)     |
         v                   |                   v
    CTP/TTS           +------+------+      quote events
    (market data)     |  JSON files |           |
                      |  data/static|           v
                      +-------------+    +-------------+
                                         |  Consumers  |
                                         | (strategies)|
                                         +-------------+
```

### Data Flow

1. **Gateway** connects to CTP/TTS, receives tick data, publishes `quote` events to the engine
2. **Greeks Engine** subscribes to `quote` events, but only caches underlying (future) prices
3. **Greeks Engine** sends `query_instruments` job to **Static Data** at startup to build option mappings
4. When a `compute_greeks` job arrives, Greeks Engine calculates IV + Greeks and publishes `greeks_update`
5. **Static Data** refreshes periodically from OpenCTP DataCenter REST API and persists to `data/static/`

---

## OpenCTP Gateway Module

**Path:** `src/modules/openctp_gateway/`

### Purpose

Connects to a CTP-compatible trading front (OpenCTP/TTS) and publishes real-time market data as `quote` events into the TycheEngine event bus.

### Components

| File | Role |
|------|------|
| `gateway.py` | `OpenCtpGateway` class — module logic |
| `md_spi.py` | `MdSpi` — market data callback handler |
| `td_spi.py` | `TdSpi` — trade API callback handler (instrument query) |
| `dll_loader.py` | Loads CTP SWIG bindings and DLLs |
| `config.py` | `GatewayConfig` dataclass |

### Lifecycle

```
start()
  ├── super().start()        # Register with TycheEngine
  ├── _connect_td()          # Connect trade API
  │     ├── connect()        # Create CThostFtdcTraderApi
  │     ├── wait_login()     # Wait for OnRspUserLogin
  │     ├── query_instruments()  # ReqQryInstrument
  │     └── wait_instruments()   # Collect instrument list
  │     └── _filter_instruments()  # Filter by underlyings config
  └── _connect_md()          # Connect market data API
        ├── connect()        # Create CThostFtdcMdApi
        ├── wait_login()     # Wait for login
        └── subscribe()      # Subscribe to filtered instruments
```

### Configuration (`GatewayConfig`)

```python
@dataclass
class GatewayConfig:
    engine_host: str = "127.0.0.1"      # TycheEngine host
    engine_port: int = 5555              # TycheEngine registration port
    gateway_type: str = "futures"        # "futures" or "stocks"
    md_front: str = ""                   # Market data front address
    td_front: str = ""                   # Trade front address
    broker_id: str = ""                  # Broker ID
    user_id: str = ""                    # User ID
    password: str = ""                   # Password
    underlyings: Dict[str, List[str]] = field(default_factory=dict)
    # Example: {"SHFE": ["ag", "au"], "CZCE": ["TA"]}
```

### Key Design Decisions

- **Dynamic SPI classes:** `MdSpi` and `TdSpi` use inner classes that dynamically inherit from the correct CTP base class (futures vs stocks have different module names). This allows a single codebase to support both gateway types.
- **Instrument filtering:** The gateway queries all instruments via the trade API, then filters by the `underlyings` config (exchange -> product IDs). If `underlyings` is empty, all instruments are subscribed.
- **Batch subscription:** Instruments are subscribed in batches of 500 with 0.5s delays to avoid overwhelming the CTP API.
- **DLL loading:** `dll_loader.py` handles Windows DLL path registration (`os.add_dll_directory`) and version-specific `.pyd` loading (e.g., `py39/`).

### Events

| Pattern | Method | Event | Description |
|---------|--------|-------|-------------|
| `send_*` | `send_quote()` | `quote` | Declares producer; actual publishing in `_on_market_data()` |

### Startup

```bash
python -m src.modules.openctp_gateway --config config/gateway_config.json
```

---

## Static Data Module

**Path:** `src/modules/static_data/`

### Purpose

Fetches static reference data (exchanges, products, instruments, prices, trading times) from the OpenCTP DataCenter REST API, persists it locally, and serves queries via TycheEngine job handlers.

### Components

| File | Role |
|------|------|
| `static_data.py` | `StaticDataModule` — module logic |
| `client.py` | `OpenCtpDataClient` — REST API client |
| `storage.py` | `StaticDataStorage` — JSON file persistence |
| `config.py` | `StaticDataConfig` dataclass |

### Lifecycle

```
start()
  ├── super().start()        # Register with TycheEngine
  ├── _load_from_disk()      # Load cached data into memory
  └── _start_refresh_loop()  # Background refresh thread
        └── _do_refresh()    # Fetch all → save → update cache
```

### Query API (Job Handlers)

| Handler | Payload Filters | Returns |
|---------|-----------------|---------|
| `handle_query_markets` | `exchange_id`, `area` | List of exchanges |
| `handle_query_products` | `exchange_id`, `product_id`, `product_class` | List of products |
| `handle_query_instruments` | `exchange_id`, `product_id`, `instrument_id`, `product_class`, `inst_life_phase` | List of instruments |
| `handle_query_prices` | `exchange_id`, `product_id`, `instrument_id` | List of price records |
| `handle_query_times` | `exchange_id`, `product_id` | List of trading sessions |
| `handle_query_metadata` | — | Counts, update times, config info |
| `handle_refresh_data` | — | Triggers manual background refresh |

### Data Directory Layout

```
data/static/
  markets.json      # 交易所信息
  products.json     # 品种信息
  instruments.json  # 合约信息
  prices.json       # 报价信息
  times.json        # 交易时段
```

Each file stores: `{"updated_at": ISO timestamp, "count": N, "data": [...]}`

### Configuration (`StaticDataConfig`)

```python
@dataclass
class StaticDataConfig:
    base_url: str = "http://dict.openctp.cn"   # OpenCTP DataCenter
    refresh_interval: int = 21600               # Seconds (6 hours)
    data_dir: str = "data/static"               # Local storage path
    engine_host: str = "127.0.0.1"
    engine_port: int = 5555
    areas: List[str] = ["China"]
    types: List[str] = ["futures", "option"]
    request_timeout: int = 30
    retry_count: int = 3
    retry_delay: int = 5
```

### Key Design Decisions

- **Dual cache:** Data is kept both in memory (for fast queries) and on disk (for persistence across restarts).
- **Background refresh:** A daemon thread refreshes data periodically. Manual refresh can be triggered via `handle_refresh_data`.
- **Retry logic:** The REST client retries failed requests up to `retry_count` times with `retry_delay` seconds between attempts.
- **Filter normalization:** Payload keys use `snake_case` (e.g., `exchange_id`) but are mapped to CTP's `PascalCase` field names (e.g., `ExchangeID`) for filtering.

### Startup

```bash
python -m src.modules.static_data --config config/static_data_config.json
```

---

## Greeks Engine Module

**Path:** `src/modules/greeks_engine/`

### Purpose

Computes real-time implied volatility and Greeks (delta, gamma, vega, theta, rho) for China futures options, publishing results as `greeks_update` events.

### Components

| File | Role |
|------|------|
| `greeks.py` | `GreeksEngine` — module logic |
| `bs_model.py` | Black-Scholes pricing, Greeks, Newton-Raphson IV solver |
| `config.py` | `GreeksConfig` dataclass |

### Lifecycle

```
start()
  ├── super().start()           # Register with TycheEngine
  └── _resolve_instruments()    # Query static_data for futures + options
        ├── query futures -> underlying_instruments
        └── query options -> underlying_map + expiry_map
```

### Greeks Computation Flow

```
handle_compute_greeks(payload)
  ├── Normalize option ID (CTP format -> config format)
  ├── Look up underlying_id from underlying_map
  ├── Get underlying_price from cache (updated by on_quote)
  ├── Parse strike, call/put, expiry from instrument_id
  ├── Calculate time to expiry T
  ├── implied_vol()  # Newton-Raphson solver
  └── bs_greeks()    # Compute all Greeks
        └── send_greeks_update()  # Publish result
```

### Black-Scholes Model (`bs_model.py`)

- **Standard normal CDF:** Abramowitz & Stegun formula 26.2.17 (Hastings rational approximation), absolute error < 7.5e-8. Pure Python, no NumPy/Numba dependency.
- **Greeks scaling:**
  - Vega: per 1% volatility change (multiplied by 0.01)
  - Theta: per day (divided by 365)
  - Rho: per 1% rate change (multiplied by 0.01)
- **IV solver:** Newton-Raphson with tolerance 1e-8, max 100 iterations.

### Option ID Format Handling

| Exchange | CTP Format | Config Format | Derivation Rule |
|----------|-----------|---------------|-----------------|
| SHFE/DCE/INE/GFEX | `ag2506-C-6000` | `ag2506C6000` | `{product_id}_o` |
| CZCE | `TA608C6700` | `TA608C6700` | `{product_id}C` / `{product_id}P` |
| CFFEX | `IO2412-C-4000` | `IO2412C4000` | Same as futures (`IO`, `HO`, `MO`) |

### Configuration (`GreeksConfig`)

```python
@dataclass
class GreeksConfig:
    risk_free_rate: float = 0.02                    # Annual risk-free rate
    underlyings: Dict[str, List[str]] = {}          # exchange_id -> [product_ids]
    # The following are auto-populated at startup:
    underlying_map: Dict[str, str] = {}             # option_id -> future_id
    expiry_map: Dict[str, str] = {}                 # option_id -> "YYYY-MM-DD"
    underlying_instruments: Set[str] = {}           # Set of future instrument IDs
    engine_host: str = "127.0.0.1"
    engine_port: int = 5555
    resolve_timeout: float = 10.0                    # Static data query timeout
```

### Events

| Pattern | Method | Event | Description |
|---------|--------|-------|-------------|
| `on_*` | `on_quote()` | `quote` | Receives ticks, caches underlying prices |
| `handle_*` | `handle_compute_greeks()` | `compute_greeks` | Job handler for Greeks computation |
| `send_*` | `send_greeks_update()` | `greeks_update` | Publishes computed Greeks |

### Published Payload (`greeks_update`)

```python
{
    "instrument_id": "ag2506C6000",
    "underlying_id": "ag2506",
    "underlying_price": 7123.0,
    "strike": 6000.0,
    "expiry": "2025-06-15",
    "is_call": True,
    "market_price": 1123.0,
    "implied_vol": 0.234567,
    "delta": 0.823456,
    "gamma": 0.000123,
    "vega": 12.34,
    "theta": -3.45,
    "rho": 8.90,
    "timestamp": "2025-05-23T10:30:00.000+08:00",
}
```

### Key Design Decisions

- **Independent underlying price caching:** Each `GreeksEngine` instance maintains its own `underlying_prices` cache updated by `on_quote`. This allows multiple instances to run without coordination.
- **Round-robin job dispatch:** `handle_compute_greeks` is a job handler, so the engine routes requests round-robin across all registered GreeksEngine instances.
- **Contract resolution at startup:** All option mappings are built once at startup by querying `static_data`. If static_data is unavailable, the module starts with empty maps.
- **Graceful degradation:** If underlying price is missing, market price is invalid, or IV fails to converge, the computation is skipped with a warning log.

### Startup

```bash
python -m src.modules.greeks_engine --config config/greeks_config.json
```

---

## Module Base Class

**Path:** `src/tyche/module.py`

All modules inherit from `TycheModule`, which provides:

### Interface Auto-Discovery

Methods with these prefixes are automatically discovered and registered:

| Prefix | Pattern | Role |
|--------|---------|------|
| `on_*` | `InterfacePattern.ON` | Event consumer — subscribes to topic |
| `send_*` | `InterfacePattern.SEND` | Event producer — declares publishing capability |
| `handle_*` | `InterfacePattern.HANDLE` | Job handler — round-robin dispatch |
| `request_*` | `InterfacePattern.REQUEST` | Job requester — declares request capability |

### Socket Architecture

| Socket | Pattern | Purpose |
|--------|---------|---------|
| REQ (one-shot) | REQ/REP | Registration handshake with engine |
| PUB | PUB/XSUB | Publish events to engine |
| SUB | XPUB/SUB | Subscribe to events from engine |
| DEALER | DEALER/ROUTER | Send heartbeats to engine |
| DEALER | DEALER/ROUTER | Job request/response (addressable via module_id) |

### Key Methods

| Method | Purpose |
|--------|---------|
| `send_event(event, payload)` | Publish an event to the engine |
| `request_event(event, payload, timeout)` | Send a job request, block for response |

---

## Configuration Examples

### Gateway Config (`config/gateway_config.json`)

```json
{
    "engine": {"host": "127.0.0.1", "port": 5555},
    "gateway": {
        "gateway_type": "futures",
        "md_front": "tcp://trading.openctp.cn:30011",
        "td_front": "tcp://trading.openctp.cn:30001",
        "broker_id": "9999",
        "user_id": "18787",
        "password": "123456",
        "underlyings": {
            "SHFE": ["ag", "au", "cu"],
            "INE": ["sc"],
            "CZCE": ["TA", "MA", "FG"],
            "DCE": ["i"]
        }
    }
}
```

### Greeks Config

```json
{
    "engine": {"host": "127.0.0.1", "port": 5555},
    "greeks": {
        "risk_free_rate": 0.02,
        "underlyings": {
            "SHFE": ["ag", "au"],
            "CZCE": ["TA"]
        }
    }
}
```

---

## Startup Sequence

For a full trading pipeline, start modules in this order:

1. **TycheEngine** — Must be running before any module registers
2. **Static Data** — Greeks Engine queries it at startup
3. **OpenCTP Gateway** — Publishes quotes; no dependencies
4. **Greeks Engine** — Queries static_data, subscribes to quotes

```bash
# Terminal 1: Engine
python -m src.tyche.engine

# Terminal 2: Static Data
python -m src.modules.static_data

# Terminal 3: Gateway
python -m src.modules.openctp_gateway --config config/gateway_config.json

# Terminal 4: Greeks Engine
python -m src.modules.greeks_engine --config config/greeks_config.json
```

---

## Dependencies

| Module | External Dependencies |
|--------|----------------------|
| OpenCTP Gateway | CTP SWIG bindings (`thostmduserapi`, `thosttraderapi` or `soptthostmduserapi`, `soptthosttraderapi`), Windows DLLs |
| Static Data | `requests` (HTTP client) |
| Greeks Engine | None (pure Python math) |
| All | `pyzmq`, `msgpack` (via TycheEngine core) |
