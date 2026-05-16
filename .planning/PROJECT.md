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

## Current Milestone: v1.1 Trading Gateway

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

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] A `GatewayBase` protocol/ABC that defines the interface all exchange gateways implement
- [ ] `SimulatedGateway` for local dev — generates synthetic quotes, trades, and fills
- [ ] `CTPGateway` that wraps the CTP API for market data and trading
- [ ] Market data normalization: exchange-native formats → Tyche events (quote, trade, bar)
- [ ] Order flow: engine events → exchange-native orders, cancellations
- [ ] Fill reporting: exchange fills → Tyche `fill` events
- [ ] Connection state machine with events: `gateway_connecting`, `gateway_connected`, `gateway_disconnected`, `gateway_error`
- [ ] Automatic reconnection with configurable retry policy
- [ ] Gateway registers as a `TycheModule` with appropriate interfaces (on_quote, send_order_submit, etc.)
- [ ] Unit tests for simulated gateway (no external dependencies)
- [ ] Unit tests for CTP gateway with mocked CTP API
- [ ] Integration test: gateway + engine end-to-end with simulated exchange

### Out of Scope

| Feature | Reason |
|---------|--------|
| Multiple simultaneous exchange connections | Single gateway instance per exchange for now |
| FIX protocol gateway | CTP is the primary target; FIX comes later |
| WebSocket/crypto exchange gateways | Futures focus first; crypto later |
| Real-time P&L calculation | Portfolio module responsibility |
| Pre-trade risk checks | Risk module responsibility |
| Market data persistence | Persistence module responsibility (v1.0) |
| GUI for gateway status | TUI dashboard handles this |

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

---
*Last updated: 2026-05-15 after milestone v1.1 started*
