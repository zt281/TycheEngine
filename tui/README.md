# Tyche Engine TUI Dashboard

A real-time terminal dashboard for monitoring and managing Tyche Engine processes, built with [OpenTUI](https://github.com/opentui/opentui) and [Bun](https://bun.sh/).

The TUI is both a **monitor** and a **process supervisor** — it connects to a running Tyche Engine over ZeroMQ to display live events, module health, and engine stats, while also managing the lifecycle of engine and module processes directly from the terminal.

## Prerequisites

- [Bun](https://bun.sh/) runtime
- Python 3.9+ (for running the engine and modules)

## Installation

```bash
cd tui
bun install
```

## Quick Start

The TUI can either connect to an existing engine or launch one itself via process management.

### Option A: TUI as Supervisor (Recommended)

The TUI reads `tyche-processes.json` and can auto-start the engine and modules:

```bash
cd tui
bun run start --config tyche-processes.json
```

### Option B: Connect to Existing Engine

```bash
# Terminal 1: Start engine manually
python examples/run_engine.py

# Terminal 2: Start TUI (connect only)
cd tui
bun run start
```

### Option C: Development Mode (auto-reload)

```bash
cd tui
bun run dev --config tyche-processes.json
```

## CLI Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--host` | Engine host address | `127.0.0.1` |
| `--event-port` | ZMQ SUB port for events | `5556` |
| `--heartbeat-port` | ZMQ SUB port for heartbeats | `5558` |
| `--admin-port` | ZMQ REQ port for admin queries | `5560` |
| `--config` | Process config JSON file | `tyche-processes.json` |

## Process Configuration

Create a `tyche-processes.json` file to define processes the TUI should manage:

```json
{
  "workdir": "..",
  "processes": [
    {
      "name": "engine",
      "command": "python",
      "args": ["src/tyche/engine_main.py", "--admin-port", "5560"],
      "env": {"PYTHONPATH": "src"},
      "autoStart": true
    },
    {
      "name": "example-module",
      "command": "python",
      "args": ["src/tyche/module_main.py"],
      "env": {"PYTHONPATH": "src"},
      "dependsOn": ["engine"],
      "autoStart": false
    }
  ]
}
```

| Field | Description |
|-------|-------------|
| `name` | Process identifier (displayed in TUI) |
| `command` | Executable to run |
| `args` | Command-line arguments |
| `env` | Environment variables (merged with `process.env`) |
| `cwd` | Working directory override (relative to `workdir`) |
| `dependsOn` | Other processes that must be running before this one starts |
| `autoStart` | Start automatically when TUI launches |

Dependencies are resolved with topological sort — `dependsOn` processes start first.

## Dashboard Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│  TYCHE ENGINE DASHBOARD                    Status: CONNECTED  Up: 5m │
├──────────────────────┬───────────────────────────────────────────────┤
│  Processes (2)       │  Event Log                                    │
│  ┌────────────────┐  │  ┌─────────────────────────────────────────┐  │
│  │> 1. engine   RUN│  │  │ 14:30:45.123000 on_common_ping athena  │  │
│  │  2. module1  STP│  │  │ 14:30:45.456000 on_common_pong  athena  │  │
│  ├────────────────┤  │  │ 14:30:46.789000 on_common_ping athena2  │  │
│  │  Modules (2)   │  │  │ 14:30:46.012000 on_common_pong  athena2 │  │
│  │  ┌──────────┐  │  │  └─────────────────────────────────────────┘  │
│  │  │> athena..│  │  │                                               │
│  │  │  athena2..│  │  │                                               │
│  │  └──────────┘  │  │                                               │
│  └────────────────┘  │                                               │
├──────────────────────┴───────────────────────────────────────────────┤
│  Events/s: 12.3  Total: 456  │  HB OK: 2  WARN: 0  EXPIRED: 0        │
├──────────────────────────────────────────────────────────────────────┤
│  [q] Quit  [p] Pause  [c] Clear  [Tab] Next  [s] Start  [x] Stop    │
│  [r] Restart  [a] All  [k] Kill Sel                                 │
└──────────────────────────────────────────────────────────────────────┘
```

### Panels

| Panel | Position | Content |
|-------|----------|---------|
| **Header** | Top | Connection status, uptime |
| **Process Panel** | Left top | Managed processes with state, PID, selection |
| **Module Panel** | Left bottom | Registered engine modules with health status |
| **Event Log** | Right (main area) | Timestamped events with sender and payload |
| **Stats Bar** | Bottom | Events/sec, total events, heartbeat summary |
| **Footer** | Bottom | Keyboard shortcut reference |

## Keyboard Shortcuts

| Key | Action | Context |
|-----|--------|---------|
| `Tab` | Cycle selection through all processes and modules | Global |
| `q` | Quit TUI (graceful shutdown of all managed processes) | Global |
| `p` | Pause / resume event log | Global |
| `c` | Clear event log | Global |
| `s` | Start selected process | Process selected |
| `x` | Stop selected process (SIGTERM) | Process selected |
| `r` | Restart selected process | Process selected |
| `k` | Force-kill selected process (SIGKILL / taskkill) | Process selected |
| `a` | Start all stopped processes | Global |

### Selection Model

Pressing `Tab` cycles through all items in order: `process[0] → process[1] → ... → module[0] → module[1] → wrap`.

- **Process selected**: The `> ` indicator appears in the Process panel. Process controls (`s`, `x`, `r`, `k`) operate on this process.
- **Module selected**: The `> ` indicator appears in the Module panel. The Event Log is **filtered** to show only events from this module. Process controls are ignored.

## Event Log Features

- **Microsecond timestamps**: `HH:MM:SS.mmmuuu` format
- **Payload preview**: Truncated JSON payload shown inline
- **Color-coded by event type**:
  - `on_*` — cornflower blue
  - `ack_*` — green
  - `whisper_*` — gold
  - `on_common_*` — dark turquoise
  - `broadcast_*` — hot pink
- **Module filtering**: Select a module to filter events by sender
- **Auto-scroll**: Most recent events appear at the bottom
- **Pause**: Press `p` to freeze the log for inspection

## Architecture

The TUI connects to Tyche Engine via three ZMQ sockets and optionally manages child processes:

```
┌─────────────┐      SUB       ┌─────────────────┐
│   Tyche     │◀───────────────│                 │
│   Engine    │      SUB       │  TUI Dashboard  │
│             │◀───────────────│  (OpenTUI/Bun)  │
│  (ZMQ PUB)  │      REQ/REP   │                 │
│             │◀──────────────►│                 │
└─────────────┘                │    ┌─────────┐  │
                               │    │ Process │  │
                               │    │ Manager │  │
                               │    │ (Bun    │  │
                               │    │ spawn)  │  │
                               │    └────┬────┘  │
                               │         │        │
                               │    ┌────┴────┐   │
                               │    │ Engine  │   │
                               │    │ Module  │   │
                               │    │ ...     │   │
                               │    └─────────┘   │
                               └──────────────────┘
```

### Sockets

- **SUB (Events, port 5556)**: Receives all events broadcast by the engine
- **SUB (Heartbeats, port 5558)**: Receives heartbeat messages from engine
- **REQ (Admin, port 5560)**: Queries engine status, module list, and statistics

### Process Management

- Uses `Bun.spawn` for cross-platform process launching
- Topological sort for `dependsOn` resolution
- Windows: `taskkill /T /F /PID` for graceful + force termination
- Unix: `SIGTERM` with 5s timeout, then `SIGKILL` escalation
- Force-kill (`k`): Immediate `taskkill /T /F` or `SIGKILL`

## Requirements

The engine must be started with the admin endpoint enabled (default port 5560):

```python
engine = TycheEngine(
    admin_endpoint="tcp://127.0.0.1:5560"
)
```

When running the engine as a child process via the TUI, ensure `PYTHONPATH` includes the `src/` directory so the `tyche` package is importable.
