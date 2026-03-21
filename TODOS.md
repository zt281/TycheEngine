# TODOS

## TODO-1: IPC Security Hardening
**Status:** Deferred to Phase 2
**Priority:** Medium
**Found by:** /plan-eng-review Issue 5

Add `ipc_permissions: 0o600` config and apply to Unix domain socket files to prevent unauthorized access on shared systems.

**Why:** Security hardening for multi-user or containerized deployments
**What:** Config option + socket creation with explicit permissions
**Depends on:** Phase 2 platform layer with multi-user support

---

## TODO-2: Serialization Zero-Copy Optimization
**Status:** Deferred to Phase 2
**Priority:** Low (measure first)
**Found by:** /plan-eng-review Issue 12

Measure MessagePack deserialization overhead under production-like load. If GC pressure is significant, implement type-check-before-deserialize or consider capnp/flatbuffers for hot paths.

**Why:** Reduce latency jitter for high-frequency market data
**What:** Performance profiling + optional optimization
**Depends on:** Real production load measurements

---

## TODO-3: Launcher Implementation
**Status:** In Progress (added to plan per /plan-eng-review)
**Priority:** High
**Found by:** /plan-eng-review Issue 1

Implement `tyche-launcher` package as specified in architecture design v1.

**Components:**
- `launcher.py` — process management, module lifecycle orchestration
- `monitor.py` — health checking, restart policy enforcement
- `config.py` — launcher configuration loader

**Restart policies:** never, always, on-failure
**Circuit breaker:** 3 failures in 60 seconds → failed state requiring manual reset

**Why:** Required for multi-module lifecycle management per approved architecture
**What:** New package with 3 modules + tests
**Depends on:** Task 10 (Module base class) complete

**Estimated effort:** 2-3 days human / 30-60 min CC
