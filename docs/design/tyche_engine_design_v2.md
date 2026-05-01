# Tyche Engine Design Specification v2

## Overview

Tyche Engine is a high-performance distributed event-driven framework built on ZeroMQ. Version 2 simplifies the module interface model from five ad-hoc patterns to three semantically clear message categories, each supporting both fire-and-forget and request-response semantics.

## Architecture

### System Topology

Same as v1: Engine and Modules communicate via ZeroMQ across process boundaries.

### Communication Patterns

| Pattern | ZeroMQ Sockets | Purpose |
|---------|---------------|---------|
| Registration | REQ ↔ ROUTER | Module handshake and interface discovery |
| Event Broadcasting | XPUB/XSUB Proxy | Fire-and-forget event distribution |
| Load-Balanced Work | PUSH → PULL | Distributing tasks across workers |
| Whisper (P2P) | DEALER ↔ ROUTER | Direct async module-to-module communication |
| Heartbeat | PUB/SUB | Health monitoring (Paranoid Pirate Pattern) |
| ACK Responses | ROUTER → DEALER | Asynchronous acknowledgments |

### Module Naming Convention

Unchanged from v1.

### Interface Patterns (v2)

All interfaces are **auto-discovered** from method names. No manual registration is required.

| Category | Fire-and-forget | Request-response | ZeroMQ Pattern | Behavior |
|----------|----------------|------------------|----------------|----------|
| **Broadcast** | `on_broadcasted_{event}` | `handle_broadcasted_{event}` | PUB-SUB / XPUB | All subscribers receive |
| **P2P (Whisper)** | `on_whispered_{event}` | `handle_whispered_{event}` | DEALER-ROUTER | Direct module-to-module |
| **Streaming** | `on_streaming_{event}` | `handle_streaming_{event}` | PUSH-PULL | Continuous data stream |

**Prefix semantics:**
- `on_*` — Fire-and-forget. Handler returns `None`. No ACK expected.
- `handle_*` — Request-response. Handler must return a `dict` response. Return value is preserved by the dispatch layer.

**Suffix semantics:**
- `_broadcasted` — Event is broadcast to all subscribers via the Engine's XPUB/XSUB proxy.
- `_whispered` — Event is sent directly to a specific module via P2P routing.
- `_streaming` — Continuous stream of messages (e.g., market data, logs).

### Removed Patterns (v1)

The following v1 patterns are removed and replaced as shown:

| v1 Pattern | v1 Example | v2 Replacement | v2 Example |
|------------|-----------|----------------|------------|
| `on_{event}` | `on_data` | `on_streaming_{event}` | `on_streaming_market_data` |
| `ack_{event}` | `ack_request` | `handle_broadcasted_{event}` | `handle_broadcasted_order_submit` |
| `whisper_{target}_{event}` | `whisper_athena_message` | `on_whispered_{event}` | `on_whispered_alert` |
| `on_common_{event}` | `on_common_broadcast` | `on_broadcasted_{event}` | `on_broadcasted_position_update` |
| `broadcast_{event}` | `broadcast_alert` | `on_broadcasted_{event}` | `on_broadcasted_risk_alert` |

> **Note:** The v1 `whisper_{target}_{event}` pattern embedded the target module ID in the method name. In v2, the target is specified in the message payload (`recipient` field), not in the method name.

### Event Delivery Guarantees

| Pattern | Delivery | Failure Mode |
|---------|----------|--------------|
| `on_*` | At-least-once, FIFO | Retry with exponential backoff |
| `handle_*` | At-least-once with confirmation | Timeout → retry → dead letter |

### Persistence Architecture

Unchanged from v1.

### Heartbeat Protocol

Unchanged from v1.

### Serialization

Unchanged from v1.

## Components

### TycheEngine (Node A)

Central broker. Unchanged from v1 except `InterfacePattern` enum values.

### TycheModule (Node B Base)

Base class for all modules providing:
- Engine connection management
- **Automatic interface discovery** (no manual registration)
- Event handler dispatch with correct return-value semantics
- Heartbeat sending

### ModuleBase (Protocol)

Lightweight protocol defining the module contract:
- `module_id` property
- `start()` / `stop()` lifecycle methods

No concrete methods. No reflection logic. No dispatch logic.

## Endpoints

Unchanged from v1.
