# Tyche Engine TUI Dashboard

A real-time terminal dashboard for monitoring Tyche Engine, built with OpenTUI and Bun.

## Prerequisites

- [Bun](https://bun.sh/) runtime
- A running Tyche Engine instance (with admin endpoint enabled)

## Installation

```bash
cd tui
bun install
```

## Usage

```bash
# Start with defaults (connects to localhost)
bun run start

# Development mode (auto-reload)
bun run dev

# Custom connection
bun run src/index.ts --host 192.168.1.100 --event-port 5556 --heartbeat-port 5558 --admin-port 5560
```

## CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--host` | Engine host address | `localhost` |
| `--event-port` | ZMQ SUB port for events | `5556` |
| `--heartbeat-port` | ZMQ SUB port for heartbeats | `5558` |
| `--admin-port` | ZMQ REQ port for admin queries | `5560` |

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `q` | Quit |
| `p` | Pause/Resume event log |
| `c` | Clear event log |

## Dashboard Layout

```
┌─────────────────────────────────────────────────────────────┐
│  Tyche Engine TUI Dashboard                    [RUNNING]   │
├─────────────────────────────────────────────────────────────┤
│  Engine: localhost:5556/5558/5560  Uptime: 00:15:32        │
├──────────────────────┬──────────────────────────────────────┤
│  MODULES             │  EVENT LOG                           │
│  ┌────────────────┐  │  ┌────────────────────────────────┐  │
│  │ zeus3f7a9c    │  │  │ [10:32:15] tick_update         │  │
│  │   ACTIVE  12ms │  │  │ [10:32:15] market_data         │  │
│  ├────────────────┤  │  │ [10:32:16] order_signal        │  │
│  │ hera8b2d4e    │  │  │ [10:32:16] fill_report         │  │
│  │   ACTIVE   8ms │  │  │ [10:32:17] heartbeat           │  │
│  ├────────────────┤  │  │ [10:32:17] status_update       │  │
│  │ poseidon9c5a1b│  │  │ [10:32:18] tick_update         │  │
│  │   SUSPECT  --  │  │  │ ...                            │  │
│  └────────────────┘  │  └────────────────────────────────┘  │
├──────────────────────┴──────────────────────────────────────┤
│  STATS                                                      │
│  Events/sec: 1,234  │  Modules: 3/3  │  Memory: 128MB        │
├─────────────────────────────────────────────────────────────┤
│  [q] Quit  [p] Pause/Resume  [c] Clear                      │
└─────────────────────────────────────────────────────────────┘
```

## Architecture

The TUI connects to Tyche Engine via three ZMQ sockets:

- **SUB (Events)**: Subscribes to event stream on `--event-port`
- **SUB (Heartbeats)**: Receives module heartbeat messages on `--heartbeat-port`
- **REQ (Admin)**: Queries engine state and module info on `--admin-port`

```
┌─────────────┐      SUB       ┌─────────────────┐
│   Tyche     │◀───────────────│  TUI Dashboard  │
│   Engine    │      SUB       │                 │
│             │◀───────────────│  (OpenTUI/Bun)  │
│  (ZMQ PUB)  │      REQ/REP   │                 │
│             │◀──────────────►│                 │
└─────────────┘                └─────────────────┘
```

## Requirements

The engine must be started with the admin endpoint enabled (default port 5560, added in engine v0.1.0+).

```python
# When starting the engine
engine = TycheEngine(
    admin_endpoint="tcp://*:5560"  # Enable admin queries
)
```
