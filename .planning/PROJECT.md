# TycheEngine

## What This Is

A high-performance distributed event-driven trading engine built on ZeroMQ. TycheEngine provides the core broker, module lifecycle, heartbeat protocol, and message routing. Trading modules plug into the engine and communicate via pub/sub and request/response patterns.

## Core Value

A modular, multi-process trading system where domain-specific modules (gateway, OMS, risk, portfolio, strategy) connect to a central event broker and communicate through standardized pub/sub and request/response patterns, with events persisted for replay and analysis.

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

## Milestone History

### v1.1 Trading Gateway

**Goal:** A market data and order execution gateway module that connects TycheEngine to external exchanges (starting with CTP), normalizes exchange-specific protocols into standard Tyche events, and provides clean connection lifecycle management.

**Target features:**
- Simulated exchange gateway for local development and backtesting
- CTP (China Futures) gateway for production market data and order routing
- Unified gateway base class/protocol for future exchange adapters
- Market data normalization (quote, trade, bar events from exchange-native formats)
- Order submission, cancellation, and fill reporting through the gateway
- Connection state machine (disconnected, connecting, connected, error, disconnected)
- Reconnection logic with exponential backoff
- Heartbeat integration with the engine's liveness monitoring

---

## Current Milestone: v1.2 OpenTelemetry Observability

**Goal:** Instrument TycheEngine's distributed event flow with OpenTelemetry tracing to visualize, debug, and analyze data movement across modules and processes.

**Target features:**
- Trace pub/sub event propagation (engine → modules, module → module)
- Trace request/response patterns (job routing, synchronous calls)
- Span context propagation across ZeroMQ message boundaries
- Module lifecycle tracing (register, start, stop, heartbeat)
- Configurable sampling and exporter setup (OTLP, console)
- Integration with existing engine events without performance regression
- Attribute enrichment with event type, sender module, topic, and correlation IDs

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] OpenTelemetry SDK initialization integrated with TycheEngine startup
- [ ] Trace context extraction/injection for ZeroMQ messages (span propagation)
- [ ] Pub/sub event tracing: create spans when events are published and consumed
- [ ] Request/response tracing: trace job routing from sender through engine to handler
- [ ] Module lifecycle spans: register, initialize, start, stop, heartbeat
- [ ] Event attributes: event_type, sender_id, topic, message_size, correlation_id
- [ ] Configurable sampling: always_on, ratio_based, always_off
- [ ] OTLP exporter support for sending traces to Jaeger/Tempo/Collector
- [ ] Console exporter for local development and debugging
- [ ] Zero-config mode: auto-detect OTLP endpoint from environment
- [ ] Unit tests: trace context propagation round-trip
- [ ] Unit tests: span creation and attribute correctness
- [ ] Unit tests: sampling behavior
- [ ] Integration test: end-to-end trace across engine + module

### Out of Scope

| Feature | Reason |
|---------|--------|
| Metrics (counters, histograms) | Traces only milestone; metrics in v1.3 |
| Log correlation with trace IDs | Requires logging overhaul; separate milestone |
| Distributed tracing UI/dashboard | Use existing Jaeger/Tempo/Grafana; no custom UI |
| Custom trace collection backend | Standard OTLP only |
| Performance profiling (CPU/memory) | Tracing ≠ profiling; separate concern |
| Alerting on trace anomalies | Requires metrics + alerting infra; out of scope |
| Automatic anomaly detection | ML-based; far future |
| Gateway tracing specifics | Gateway module is v1.1; engine-wide tracing first |

## Context

TycheEngine is a ZeroMQ-based event broker for trading systems. It supports module registration, heartbeat monitoring, event pub/sub via XPUB/XSUB, and job routing. The engine already has `TycheModule` (in `src/tyche/module.py`) which handles socket setup and event discovery.

Event constants exist in `src/tyche/events.py` for market data (QUOTE, TRADE, BAR), order flow (ORDER_SUBMIT, ORDER_APPROVED, ORDER_REJECTED, ORDER_EXECUTE, ORDER_CANCEL, ORDER_UPDATE), fills (FILL), portfolio (POSITION_UPDATE, ACCOUNT_UPDATE), and risk (RISK_ALERT).

The `src/modules/` package is currently empty (just `__init__.py`) — this is where trading domain modules live.

Key files in the existing codebase:
- `src/tyche/engine.py` — `TycheEngine` broker
- `src/tyche/module.py` — `TycheModule` base class with registration, pub/sub, heartbeat
- `src/tyche/types.py` — `Interface`, `InterfacePattern`, `ModuleInfo`, `MessageType`
- `src/tyche/events.py` — event name constants
- `src/tyche/message.py` — `Message` serialization with MessagePack
- `src/tyche/heartbeat.py` — heartbeat monitoring
- `src/tyche/cpp/` — C++ type bindings
- `src/tyche/rust/` — Rust extension bindings

## Constraints

- **Tech stack**: Python 3.9+, ZeroMQ, msgpack, pytest
- **Module location**: `src/modules/gateway/` (new package)
- **CTP API**: `openctp-ctp` Python bindings or direct CTP C++ API via pybind11
- **Test runtime**: Unit tests < 5 seconds; integration tests may take longer for connection setup
- **Module pattern**: All modules inherit from `TycheModule`, use `on_*` for consumers, `send_*` for producers

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Gateway as TycheModule | Follows engine conventions; gets heartbeat, pub/sub, registration for free | — Pending |
| Simulated gateway first | Enables development and testing without external exchange credentials | — Pending |
| CTP as first real exchange | Primary target market; CTP is the standard Chinese futures API | — Pending |
| GatewayBase ABC, not just protocol | ABC enforces interface compliance at import time | — Pending |
| Gateway before OMS/risk/portfolio | Gateway is the outermost layer; other modules consume gateway events | — Pending |
| OpenTelemetry over custom tracing | Industry standard, rich ecosystem, no reinvention | — Pending |
| Trace at Message level, not socket level | Message carries context; socket is transport detail | — Pending |
| W3C trace context propagation | Standard format; interoperable with any OTLP collector | — Pending |
| Lazy SDK init (on first span) | Avoid startup cost if tracing disabled | — Pending |

---
*Last updated: 2026-05-23 after milestone v1.2 started*
