# State: TycheEngine v1.2 OpenTelemetry Observability

## Project Reference

**Core Value:** A modular, multi-process trading system where domain-specific modules connect to a central event broker and communicate through standardized pub/sub and request/response patterns, with events persisted for replay and analysis.

**Current Focus:** Defining requirements and roadmap for OpenTelemetry tracing

**Milestone:** v1.2 OpenTelemetry Observability

## Current Position

**Phase:** Not started (defining requirements)
**Plan:** —
**Status:** Defining requirements
**Progress:** 0 phases complete

```
[          ] 0% — Milestone not started
```

## Performance Metrics

| Metric | Target | Current |
|--------|--------|---------|
| Unit test runtime | < 5 seconds | — |
| Integration test runtime | < 30 seconds | — |
| Line coverage (unit) | >= 80% | — |
| Line coverage (new code) | >= 90% | — |
| Trace overhead (p50) | < 1% latency increase | — |
| Trace overhead (p99) | < 5% latency increase | — |

## Accumulated Context

### Decisions

| Decision | Rationale | Status |
|----------|-----------|--------|
| OpenTelemetry over custom tracing | Industry standard, rich ecosystem, no reinvention | Pending |
| Trace at Message level, not socket level | Message carries context; socket is transport detail | Pending |
| W3C trace context propagation | Standard format; interoperable with any OTLP collector | Pending |
| Lazy SDK init (on first span) | Avoid startup cost if tracing disabled | Pending |

### Todos

- [ ] Define requirements for v1.2 OpenTelemetry Observability
- [ ] Create roadmap with phases
- [ ] Phase 1: OpenTelemetry SDK integration and configuration
- [ ] Phase 1: Trace context propagation for ZeroMQ messages
- [ ] Phase 1: Pub/sub event tracing instrumentation
- [ ] Phase 1: Request/response tracing instrumentation
- [ ] Phase 1: Module lifecycle tracing
- [ ] Phase 1: Unit tests for trace context propagation
- [ ] Phase 2: Exporters (OTLP, console) and sampling
- [ ] Phase 2: Integration test with real engine + module

### Blockers

_(none)_

## Session Continuity

**Last updated:** 2026-05-23
**Milestone started:** 2026-05-23
**Next action:** Complete requirements and roadmap, then `/gsd-discuss-phase [N]` or `/gsd-plan-phase [N]`
