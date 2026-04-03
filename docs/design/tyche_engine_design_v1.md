# Tyche Engine Design Specification v1

## Overview

Tyche Engine is a high-performance distributed event-driven framework built on ZeroMQ. It provides a modular architecture for building multi-process applications with reliable event management and module lifecycle management.

## Architecture

### System Topology

```
+------------------+         +------------------+
|   TycheEngine    |<------->|  ExampleModule   |
|    (Node A)      |  ZMQ    |    (Node B)      |
+------------------+         +------------------+
```

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

Modules are assigned unique identifiers with format: `{deity_name}{6-char MD5}`

Examples:
- `zeus3f7a9c`
- `athena8b2d4e`
- `hermes9c5e1f`

Available deities: zeus, hera, poseidon, hades, athena, apollo, artemis, ares, aphrodite, hermes, dionysus, demeter, hephaestus, hestia

### Interface Patterns

| Pattern | Method Name | ZeroMQ Pattern | Behavior |
|---------|-------------|----------------|----------|
| `on_{event}` | `on_data` | PUSH-PULL | Fire-and-forget, load-balanced |
| `ack_{event}` | `ack_request` | DEALER-ROUTER | Must reply with ACK within timeout |
| `whisper_{target}_{event}` | `whisper_athena_message` | DEALER-ROUTER | Direct P2P, bypasses Engine routing |
| `on_common_{event}` | `on_common_broadcast` | PUB-SUB | Broadcast to ALL subscribers |
| `broadcast_{event}` | `broadcast_alert` | XPUB | Publishes event via Engine |

### Event Delivery Guarantees

| Pattern | Delivery | Failure Mode |
|---------|----------|--------------|
| `on_` | At-least-once, FIFO | Retry with exponential backoff |
| `ack_` | At-least-once with confirmation | Timeout → retry → dead letter |
| `whisper_` | Best-effort or confirmed | Connection failure → fallback to Engine |
| `on_common_` | Best-effort | Drop if subscriber slow |

### Persistence Architecture

Events flow through async persistence with configurable durability levels:

| Level | Value | Behavior |
|-------|-------|----------|
| `BEST_EFFORT` | 0 | No persistence guarantee |
| `ASYNC_FLUSH` | 1 | Async write (default) |
| `SYNC_FLUSH` | 2 | Sync write, confirmed |

### Heartbeat Protocol (Paranoid Pirate)

Implements reliable worker heartbeating:
- **Interval**: 1.0 seconds between heartbeats
- **Liveness**: 3 missed heartbeats before peer considered dead
- **Worker behavior**: Send heartbeat at regular intervals
- **Broker behavior**: Track liveness, expire dead peers

### Serialization

- **Format**: MessagePack
- **Special handling**: Decimal precision preserved via custom encoding
- **Envelope**: ZeroMQ multipart with identity frames for routing

## Components

### TycheEngine (Node A)

Central broker responsible for:
- Module registration and lifecycle management
- Event routing and broadcasting
- Heartbeat monitoring
- Interface registry

### TycheModule (Node B Base)

Base class for all modules providing:
- Engine connection management
- Event handler registration
- Automatic interface discovery
- Heartbeat sending

### ExampleModule (Reference Implementation)

Demonstrates all interface patterns:
- `on_data`: Fire-and-forget handler
- `ack_request`: Request-response handler
- `whisper_athena_message`: P2P handler
- `on_common_broadcast`: Broadcast handler

## Endpoints

Default port allocation for 2-node system:

| Service | Port | Socket Type |
|---------|------|-------------|
| Registration | 5555 | ROUTER (Engine), REQ (Module) |
| Event XPUB | 5556 | XPUB (Engine) |
| Event XSUB | 5557 | XSUB (Engine) |
| Heartbeat | 5558 | PUB (Engine), SUB (Module) |
| ACK Router | 5566 | ROUTER (Engine), DEALER (Module) |

## References

- [ZeroMQ Guide](https://zguide.zeromq.org/)
- Paranoid Pirate Pattern (reliable worker heartbeating)
- Binary Star Pattern (high availability)
