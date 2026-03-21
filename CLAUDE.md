# TycheEngine — Agent Cooperation Guide

Multi-asset HFT trading platform. Python + Rust (PyO3/maturin) hot path. ZeroMQ hub-and-spoke IPC.

## Quick Reference

```bash
# Build Rust crate and install Python package in dev mode
maturin develop --release

# Run all tests
cargo test --manifest-path tyche-core/Cargo.toml
pytest tests/ -v

# Lint
cargo clippy --manifest-path tyche-core/Cargo.toml -- -D warnings
ruff check tyche/ tests/
```

Platform: **Windows 11 dev / Linux production**. Use `python` (not `python3`) on Windows.

---

## Architecture in One Page

```
Nexus (core 0)  ROUTER/DEALER tcp:5555  — lifecycle, registration, commands
Bus   (core 1)  XPUB/XSUB    tcp:5556/5557 — all streaming data (MessagePack)
Modules (core N) — each an independent OS process; registers with Nexus, pub/sub via Bus
```

- Publishers → XSUB port **5556**; Subscribers → XPUB port **5557**
- DEALER sends frames as-is (no empty delimiter). ROUTER prepends identity on receive.
- `correlation_id` encoded as **UTF-8 decimal string** (not raw u64 bytes) in Python layer
- All hot-path types defined **once** in Rust (`#[repr(C)]`), re-exported to Python via PyO3
- MessagePack everywhere — no JSON on the data path
- Topic format: `<ASSET_CLASS>.<VENUE>.<SYMBOL>.<DATA_TYPE>[.<INTERVAL>]`

See `docs/design/core_engine_design_v3.md` for the full spec.

---

## Document Conventions

| Kind | Path template | Example |
|------|--------------|---------|
| Design spec | `docs/design/{spec}_design_v{N}.md` | `core_engine_design_v3.md` |
| Implementation plan | `docs/plan/{spec}_plan_v{N}.md` | `core_engine_plan_v2.md` |
| Spec review log | `docs/review/{spec}_review_v{N}.log` | `core_engine_review_v3.log` |
| Plan review log | `docs/review/{spec}_plan_review_v{N}.log` | `core_engine_plan_review_v2.log` |
| Impl log | `docs/impl/{spec}_implement_v{N}.md` | new file each cycle |

Design and plan version numbers are independent (design_v3 ↔ plan_v2 is acceptable).

---

## Agent Team — Roles and Boundaries

### Architect Agent
**Owns:** Design docs and implementation plans.
**Does:** Reads the spec, explores the codebase, writes/revises design and plan docs.
**Does NOT:** Write production code, edit source files, run build commands.
**Handoff:** Produces `docs/plan/{spec}_plan_v{N}.md`. Hands off to Plan Reviewer.

### Plan Reviewer Agent
**Owns:** Plan review logs.
**Does:** Reviews the plan doc against the design spec for completeness, TDD discipline, and spec adherence. Issues a ISSUES FOUND or APPROVED verdict with structured log.
**Does NOT:** Rewrite the plan — returns issues to Architect for a new plan version.
**Handoff:** Produces `docs/review/{spec}_plan_review_v{N}.log`. On APPROVED, hands off to Implementer.

### Implementer Agent
**Owns:** All source files under `tyche/`, `tyche-core/src/`, `config/`, `tests/`.
**Does:** Follows the approved plan task-by-task using TDD. Creates tests (RED) before implementation (GREEN). Updates impl log.
**Does NOT:** Deviate from the plan without flagging it. Claim completion without running tests.
**Handoff:** When all tests pass, hands off to Code Reviewer. Never skips the verification step.

### Code Reviewer Agent
**Owns:** Code review output only.
**Does:** Reviews implementation against design spec and plan. Reports only high-confidence issues.
**Does NOT:** Implement fixes. Rewrite working code. Approve work that has failing tests.
**Handoff:** Returns specific issues to Implementer. On APPROVED, signals Implementer to commit.

### Debugger Agent
**Owns:** Root cause analysis and targeted fix.
**Does:** Reproduces failure, identifies root cause, applies minimal fix, re-runs tests.
**Does NOT:** Rewrite unrelated code. Change the plan. Use `--no-verify` or bypass test hooks.
**Handoff:** After fix confirmed passing, hands back to Implementer or Code Reviewer.

---

## Workflow — Stage Gates

```
[SPEC] ──► [DESIGN] ──► [PLAN] ──► [REVIEW] ──► [IMPLEMENT] ──► [VERIFY] ──► [COMMIT]
              │             │           │               │              │
          Architect     Architect   Plan Reviewer   Implementer    All tests
          writes doc    writes plan  APPROVED req'd   TDD only       must pass
```

### Gate: Plan → Implement
- Plan review log must have **Result: APPROVED** (no CRITICAL or MAJOR open issues)
- Plan commit hash noted in task context before implementation starts
- Skill `superpowers:writing-plans` must have been used to produce the plan
- Skill `superpowers:subagent-driven-development` or `superpowers:executing-plans` must be invoked to start implementation

### Gate: Implement step → Next step
- RED phase (failing test) must exist in the impl log before GREEN phase (implementation)
- Test command output (pass/fail) must be recorded in the impl log
- No step may be marked `[x]` without its test evidence

### Gate: Implement → Review
- `maturin develop --release` succeeds
- `cargo test` passes with **0 failures**
- `pytest tests/ -v` passes with **0 failures**
- Skill `superpowers:verification-before-completion` must be invoked — show actual output, not assertions

### Gate: Review → Commit
- No HIGH-confidence issues open in code review
- `superpowers:requesting-code-review` invoked before commit
- Commit via `commit-commands:commit-push-pr` skill only (do not bypass hooks)

---

## Agent Cooperation Rules

1. **One owner per artifact.** Each file type has exactly one owning role. Implementers do not edit plan docs; Architects do not edit source files.

2. **No silent deviations.** If the plan is ambiguous or wrong, the Implementer must stop, flag the issue in a message to the Architect, and wait for a plan revision. Do not silently implement a different approach.

3. **Reviewers do not implement.** When a reviewer finds an issue they must return it with a precise description. The Implementer applies the fix. This keeps blame and ownership clear.

4. **Tests before claims.** No agent may claim a step is complete without running the relevant test command and recording the output. "It should work" is not evidence.

5. **Minimal scope.** Each agent operates only on files within its owned scope for the current task. Do not refactor, add comments, or clean up code outside the task boundary.

6. **Escalation path.** If an agent is blocked (build fails, spec is contradictory, test infrastructure is broken), it stops, records the blocker in the impl log, and sends a message to the team lead rather than working around it.

7. **Plan is the contract.** The approved plan is the implementation contract. New requirements discovered mid-implementation go back to the Architect for a plan revision — they are never absorbed silently into the current task.

---

## Git Worktree Rules

### When worktrees are required

Every agent executing an implementation plan **must** work in a dedicated git worktree. This applies to:
- Any invocation of `superpowers:subagent-driven-development` or `superpowers:executing-plans`
- Parallel agent teams working independent tasks simultaneously
- Any branch that must not affect the state visible to other concurrently running agents

Agents doing read-only work (Architect, Plan Reviewer, Code Reviewer) do **not** need worktrees — they do not modify source files.

### Directory convention

Use `.worktrees/` at the project root (hidden, project-local).

```
.worktrees/
  core-engine-task1/    ← one directory per agent / branch
  core-engine-task2/
```

**Safety check — run this before creating any worktree:**

```bash
git check-ignore -q .worktrees
```

If the command exits non-zero (directory is NOT ignored), add it to `.gitignore` and commit that change **before** creating the worktree. Failure to do so causes worktree contents to pollute `git status`.

### Creating a worktree

```bash
# From project root
git worktree add .worktrees/<branch-name> -b <branch-name>
cd .worktrees/<branch-name>
maturin develop --release   # run project setup
```

Branch naming: `<spec>/<task>` — e.g. `core-engine/task-1-scaffold`, `core-engine/task-3-enums`.

### Baseline verification

After setup, run the full test suite and confirm it is clean before touching any code:

```bash
cargo test --manifest-path tyche-core/Cargo.toml
pytest tests/ -v
```

If the baseline fails, **stop** and report the failure to the team lead. Do not proceed — you cannot distinguish new failures from pre-existing ones without a clean baseline.

### Cleanup after merge

When implementation is complete and merged, invoke `superpowers:finishing-a-development-branch` to handle worktree removal, branch cleanup, and merge confirmation. Do not delete worktrees manually.

### Cooperation rules for parallel worktrees

- Each parallel agent owns exactly one worktree. Agents must not read from or write to another agent's worktree directory.
- Shared artefacts (plan docs, config files) that need updating during implementation go through the team lead, not direct cross-agent file access.
- Worktree branches are rebased onto `main` before merge, never merged with unresolved drift. If a rebase conflict arises, the agent stops and escalates to the team lead.

---

## TDD Rules (Non-Negotiable)

- Every task that produces a source file must have a corresponding test file created **first** in a separate step marked RED.
- The RED step is complete only when the test file exists and the test command fails with a compile error or assertion error (not import error from a missing stub).
- The GREEN step is complete only when the same test command passes.
- Rust test splits: `tyche-core/` tests use `#[cfg(test)]` modules inside each source file. Python unit tests live in `tests/unit/`, integration tests in `tests/integration/`.
- Do not add `__init__.py` to `tests/` or any subdirectory of `tests/` — maturin would include them in the wheel.

---

## Key Technical Rules for Implementers

**PyO3 / Cargo:**
- Add `"multiple-pymethods"` to pyo3 features in `Cargo.toml` when splitting `#[pymethods]` blocks across multiple `impl` blocks.
- `BarInterval.topic_suffix` must be in a `#[pymethods]` block with `#[getter]`. `from_suffix` lives in a plain `impl` block.
- `#[pyo3(eq_int)]` required on all `#[repr(u8)]` pyclass enums for Python equality to work.
- Do not add `python-source` to `pyproject.toml` — omit it (defaults to `.`).

**FFI Bridge:**
- `AtomicPtr<T>` per topic (not `Mutex`) — use `OnceLock<RwLock<HashMap<...>>>` for the registry.
- `tyche_core.take_pending(service_name, topic)` is a **module-level function**, not a method.

**ZeroMQ:**
- DEALER sends frames as-is. No empty delimiter. ROUTER prepends identity.
- `correlation_id` is encoded as UTF-8 decimal string throughout the Python layer.
- `_register()` must verify `frames[2].decode() == str(self._correlation_id)` to reject stale ACKs.
- `_handle_nexus` must implement START / STOP / RECONFIGURE / STATUS commands.
- STOP command: send REPLY **before** setting `_stop_event`.

**publish():**
- Check if payload is a `tyche_core` type first; call the appropriate `serialize_*` function.
- Fall back to `msgpack.packb()` for plain dicts/other types.
- Add `msgpack>=1.0` to `pyproject.toml` dependencies.

**Topics:**
- Topic validation enforced by `topics.py`. `publish()` raises `ValueError` on invalid topics.
- Symbol normalisation: alphanumeric + hyphen + underscore only. FX: `EUR/USD` → `EURUSD`. Options/futures fields joined with `_`.

---

## Current State

- **Phase:** Core Engine — implementation not yet started
- **Approved plan:** `docs/plan/core_engine_plan_v2.md` (commit `521da46`)
- **Approved spec:** `docs/design/core_engine_design_v3.md`
- **Source tree:** Empty — only `docs/` and `LICENSE` exist

Next step: invoke `superpowers:subagent-driven-development` and begin Task 1 (Project Scaffold) from the approved plan.
