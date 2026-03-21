# TycheEngine CLI Client Design
**Spec:** `repl_client`
**Version:** v2
**Date:** 2026-03-21
**Status:** Draft

---

## 1. Overview

A Node.js interactive CLI client for TycheEngine that connects to Nexus (control) and Bus (data) via ZeroMQ. Provides an interactive shell to:
- Auto-register with Nexus as `tyche-cli` module
- Send commands to Nexus (START, STOP, STATUS, RECONFIGURE)
- Subscribe to streaming data topics on the Bus
- Inspect received messages (health checks, system status, quotes, trades, bars, etc.)

---

## 2. Configuration

| Setting | Value |
|---------|-------|
| Node.js version | >= 18 |
| Service name | `tyche-cli` |
| CPU core | 0 (default) |
| Nexus address | `tcp://localhost:5555` |
| Bus address | `tcp://localhost:5557` |
| Heartbeat interval | 1000ms |

---

## 3. Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    CLI CLIENT (Node.js)                  │
│                                                          │
│  ┌─────────────────┐         ┌─────────────────────┐   │
│  │  Nexus Client   │         │    Bus Client       │   │
│  │  DEALER tcp:5555│         │    SUB  tcp:5557    │   │
│  └────────┬────────┘         └──────────┬──────────┘   │
│           │                             │               │
└───────────┼─────────────────────────────┼───────────────┘
            │                             │
      ┌─────┴─────┐                 ┌─────┴─────┐
      │   Nexus   │                 │    Bus    │
      │ ROUTER:5555│                │XPUB:5557  │
      └───────────┘                 └───────────┘
```

---

## 4. Protocol Details

### 4.1 Nexus Connection (DEALER → ROUTER)

**Registration Flow (auto on connect):**
```
CLI → Nexus: [identity | "TYCHE" | "READY" | correlation_id_u64 | "tyche-cli" | cpu_core]
Nexus → CLI: [identity | "TYCHE" | "READY_ACK" | correlation_id_u64 | timestamp_ns]
```

**Heartbeat Flow (every 1000ms):**
```
CLI → Nexus: [identity | "TYCHE" | "HB" | timestamp_ns]
```

**Command Flow:**
```
CLI → Nexus: [identity | "TYCHE" | "CMD" | command | payload_msgpack]
Nexus → CLI: [identity | "TYCHE" | "REPLY" | correlation_id_u64 | status | payload_msgpack]
```

### 4.2 correlation_id Encoding

- Stored as JavaScript `bigint` (64-bit unsigned)
- Transmitted as **UTF-8 decimal string** (not raw bytes)
- Example: `12345n` → `"12345"`

### 4.3 Bus Connection (SUB)

**Default subscriptions (auto on connect):**
```
CTRL.NEXUS.HEALTHCHECK
CTRL.NEXUS.SYSTEM_STATUS
```

**Message format (received):**
```
Frame 0: topic (UTF-8 string)
Frame 1: timestamp_ns (8 bytes big-endian u64)
Frame 2: payload (MessagePack)
```

---

## 5. CLI Commands

### 5.1 REPL Commands

| Command | Description |
|---------|-------------|
| `.connect` | Connect and auto-register with Nexus; subscribe to default topics |
| `.disconnect` | Disconnect from all sockets |
| `.status` | Show connection and registration status |
| `.subscribe <topic>` | Subscribe to a topic |
| `.unsubscribe <topic>` | Unsubscribe from a topic |
| `.subscriptions` | List current subscriptions |
| `.send <cmd> [payload]` | Send command to Nexus |
| `.topics` | Show valid topic format |
| `.help` | Show available commands |
| `.exit` | Exit the CLI |

### 5.2 Nexus Commands (via `.send`)

| Command | Payload | Description |
|---------|---------|-------------|
| `START` | `{}` | Start module |
| `STOP` | `{}` | Stop module |
| `STATUS` | `{}` | Get module status |
| `RECONFIGURE` | `{...}` | Reconfigure module |

---

## 6. Topic Format

```
<ASSET_CLASS>.<VENUE>.<SYMBOL>.<DATA_TYPE>[.<INTERVAL>]

Examples:
  CRYPTO_SPOT.BINANCE.BTCUSDT.QUOTE
  EQUITY.NYSE.AAPL.BAR.M5
  INTERNAL.OMS.POSITION
  CTRL.NEXUS.HEALTHCHECK
  CTRL.NEXUS.SYSTEM_STATUS
```

**Prefix subscriptions (ZeroMQ):**
```
CTRL.NEXUS.HEALTHCHECK  → receives health check broadcasts
CTRL.NEXUS.SYSTEM_STATUS → receives system status broadcasts
```

---

## 7. Dependencies

| Package | Version | Purpose |
|---------|---------|---------|
| `zeromq` | ^6.0.0 | ZeroMQ bindings |
| `msgpack5` | ^6.0.0 | MessagePack serialization |

---

## 8. File Structure

```
tyche-cli/
├── src/
│   ├── index.js           # CLI entry point
│   ├── nexus-client.js    # Nexus DEALER connection + auto-register
│   ├── bus-client.js      # Bus SUB connection
│   ├── protocol.js        # Frame encoding/decoding
│   └── repl.js            # CLI command handler
├── package.json
└── README.md
```

---

## 9. Usage

```bash
# Connect to local engine
node src/index.js

# In CLI (auto-connected and auto-registered):
tyche> .status
Nexus:
  Connected:  true
  Registered: true
  Service:    tyche-cli
Bus:
  Connected:     true
  Subscriptions: 2

tyche> .subscriptions
CTRL.NEXUS.HEALTHCHECK
CTRL.NEXUS.SYSTEM_STATUS

tyche> .send STATUS {}
Status: OK
Payload: {...}

tyche> .exit
```

---

## 10. Auto-Registration Flow

1. `.connect` called
2. DEALER socket connects to Nexus
3. READY frame sent with `service_name="tyche-cli"`, `cpu_core=0`
4. Wait for READY_ACK (500ms timeout, 20 retries)
5. On success: start heartbeat loop (1000ms interval)
6. On failure: throw error, disconnect

---

## 11. Default Subscription Behavior

On successful `.connect`:
1. Subscribe to `CTRL.NEXUS.HEALTHCHECK`
2. Subscribe to `CTRL.NEXUS.SYSTEM_STATUS`
3. Display subscribed topics

Users can `.unsubscribe` any default topic if desired.
