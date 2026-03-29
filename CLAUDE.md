# TycheEngine — Agent Cooperation Guide

Multi-asset algorithmic trading platform. Pure Python architecture. ZeroMQ hub-and-spoke IPC via Unix domain sockets / named pipes.

## Quick Reference

```bash
# Install core service
pip install tyche-core

# Install module client library
pip install tyche-cli

# Run all tests
pytest tests/ -v

# Lint
ruff check tyche/ tests/
```

Platform: **Windows 11 dev / Linux production**. Use `python` (not `python3`) on Windows.

---

## Architecture in One Page

```
Nexus (core 0)  ROUTER/DEALER ipc:///tmp/tyche/nexus.sock  — lifecycle, registration, commands
Bus   (core 1)  XPUB/XSUB    ipc:///tmp/tyche/bus_xsub.sock / ipc:///tmp/tyche/bus_xpub.sock — all streaming data (MessagePack)
Modules (core N) — each an independent OS process; registers with Nexus, pub/sub via Bus
```

- Publishers → XSUB socket `ipc:///tmp/tyche/bus_xsub.sock`
- Subscribers → XPUB socket `ipc:///tmp/tyche/bus_xpub.sock`
- DEALER sends frames as-is (no empty delimiter). ROUTER prepends identity on receive.
- `correlation_id` encoded as **UTF-8 decimal string** (not raw u64 bytes) in Python layer
- All types defined in Python dataclasses with `frozen=True, slots=True` for efficiency
- MessagePack everywhere — no JSON on the data path
- Topic format: `<ASSET_CLASS>.<VENUE>.<SYMBOL>.<DATA_TYPE>[.<INTERVAL>]`

See `docs/design/pure_python_architecture_design_v1.md` for the full spec.

---

## Document Conventions

| Kind | Path template | Example |
|------|--------------|---------|
| Design spec | `docs/design/{spec}_design_v{N}.md` | `pure_python_architecture_design_v1.md` |
| Implementation plan | `docs/plan/{spec}_plan_v{N}.md` | `pure_python_plan_v1.md` |
| Spec review log | `docs/review/{spec}_review_v{N}.log` | `pure_python_review_v1.log` |
| Plan review log | `docs/review/{spec}_plan_review_v{N}.log` | `pure_python_plan_review_v1.log` |
| Impl log | `docs/impl/{spec}_implement_v{N}.md` | new file each cycle |

Design and plan version numbers are independent (design_v3 ↔ plan_v2 is acceptable).

---

## Agent Team — Roles and Boundaries

### Architect Agent
**Owns:** Design docs and implementation plans.
**Does:** Reads the latest design spec, all existing plan and review docs, and the current impl log before writing anything. Summarises project state in the plan under `## Project State at Plan Time`. Writes/revises design and plan docs.
**Does NOT:** Write real code in docs, write production code, edit source files, run build commands.
**Handoff:** Produces `docs/plan/{spec}_plan_v{N}.md`. Hands off to Plan Reviewer.

### Plan Reviewer Agent
**Owns:** Plan review logs.
**Does:** Reviews the plan doc against the design spec for completeness, TDD discipline, and spec adherence. Issues a ISSUES FOUND or APPROVED verdict with structured log.
**Does NOT:** Rewrite the plan — returns issues to Architect for a new plan version.
**Handoff:** Produces `docs/review/{spec}_plan_review_v{N}.log`. On APPROVED, hands off to Implementer.

### Implementer Agent
**Owns:** All source files under `tyche-core/`, `tyche-cli/`, `config/`, `tests/`.
**Does:** Read the Critical entry of the code reviews. Avoid making the same mistakes as described in the critical section of the code review. Follows the approved plan task-by-task using TDD. Creates tests (RED) before implementation (GREEN). Updates impl log.
**Does NOT:** Deviate from the plan without flagging it. Claim completion without running tests.
**Handoff:** When all tests pass, hands off to Code Reviewer. Never skips the verification step.

### Code Reviewer Agent
**Owns:** Code review output and the `## CRITICAL` section of the impl log.
**Does:** Reviews implementation against the design spec and approved plan (not just tests). Focusing check if the implementation answers the three questions of each task. Appends every confirmed bug or spec deviation as a CRITICAL entry in the impl log with status OPEN. Re-reviews after Implementer marks items RESOLVED. Issues APPROVED or ISSUES FOUND verdict.
**Does NOT:** Implement fixes. Rewrite working code. Approve work that has failing tests or open CRITICAL items.
**Handoff:** On APPROVED (no open CRITICAL items), signals team lead to proceed to Verify gate. On ISSUES FOUND, returns to Implementer with CRITICAL entries as the fix list.

### Debugger Agent
**Owns:** Root cause analysis and targeted fix.
**Does:** Reproduces failure, identifies root cause, applies minimal fix, re-runs tests.
**Does NOT:** Rewrite unrelated code. Change the plan. Use `--no-verify` or bypass test hooks.
**Handoff:** After fix confirmed passing, hands back to Implementer or Code Reviewer.

---

## Workflow — Stage Gates

```
[SPEC] ──► [DESIGN] ──► [PLAN] ──► [PLAN REVIEW] ──► [IMPLEMENT] ──► [IMPL REVIEW] ──► [VERIFY] ──► [COMMIT]
              │             │             │                 │                │               │
          Architect     Architect   Plan Reviewer      Implementer     Code Reviewer    All tests
          writes doc    writes plan  APPROVED req'd     TDD only       vs design+plan    must pass
                                                                       logs CRITICAL
                                                                       to impl log
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

### Gate: Implement → Impl Review
- All plan tasks are marked complete in the impl log with test evidence.
- Code Reviewer agent is spawned and given the design spec, approved plan, and impl log as context.
- Code Reviewer checks the implementation against the design spec and plan — not just tests.
- Every confirmed bug or spec deviation is appended to the impl log under `## CRITICAL` (see impl log format below).
- Code Reviewer produces a verdict: **APPROVED** (no critical issues) or **ISSUES FOUND** (one or more CRITICAL entries).
- On ISSUES FOUND: Implementer resolves each CRITICAL item and the Code Reviewer re-reviews. Loop until APPROVED.

### Gate: Impl Review → Verify
- Code Reviewer verdict in impl log is **APPROVED** with no open CRITICAL items.
- `pip install -e tyche-core/` and `pip install -e tyche-cli/` succeed.
- `pytest tests/ -v` passes with **0 failures**.
- Skill `superpowers:verification-before-completion` must be invoked — show actual command output, not assertions.

### Gate: Verify → Commit
- All Gate: Impl Review → Verify conditions confirmed with recorded output.
- Commit via `commit-commands:commit-push-pr` skill only (do not bypass hooks).

---

## Mandatory Cycle Rule (Non-Negotiable)

Every feature, fix, or enhancement **must** follow this exact cycle. There are no exceptions. No agent may skip or merge stages.

```
PLAN  ──►  PLAN REVIEW  ──►  CONFIRM  ──►  IMPLEMENT  ──►  IMPL REVIEW  ──►  VERIFY  ──►  COMMIT
  │              │              │               │                │               │
Architect   Plan Reviewer   Team Lead      Implementer(s)   Code Reviewer   Team Lead
writes      checks vs.      reads          TDD per task     checks vs.      runs full
plan doc    spec, gates     APPROVED,      logs RED/GREEN   design+plan,    test suite,
            APPROVED        spawns team    evidence         appends         records
                                                            CRITICAL        output
                                                            to impl log
```

### Required skills — in order

| Stage | Who invokes | Skill |
|-------|------------|-------|
| Read latest docs & current state | Architect agent | (required before writing plan — see below) |
| Write plan | Architect agent | `superpowers:writing-plans` |
| Review plan | Plan Reviewer agent | `feature-dev:code-reviewer` or dedicated review role |
| Start implementation | Team Lead | `superpowers:subagent-driven-development` or `superpowers:executing-plans` |
| Each impl step | Implementer agent | `superpowers:test-driven-development` |
| Review implementation | Code Reviewer agent | `superpowers:requesting-code-review` — logs CRITICAL issues to impl log |
| Before claiming done | Implementer agent | `superpowers:verification-before-completion` |
| Commit | Team Lead | `commit-commands:commit-push-pr` |

### Plan phase — mandatory pre-work (Architect)

Before invoking `superpowers:writing-plans` or writing a single line of a plan, the Architect agent **must**:

1. Read the current design spec (`docs/design/` — latest version by number).
2. Read all existing plan docs (`docs/plan/`) and their review logs (`docs/review/`) to understand what has already been approved, rejected, or revised.
3. Read the `## CRITICAL` section of the current impl log (`docs/impl/`) if one exists — open CRITICAL items represent outstanding bugs that must be accounted for in the new plan. The full Task Log is not required reading.
4. Read `CLAUDE.md` (this file) in full to pick up any rule changes since the last session.
5. Check `Current State` at the bottom of this file and reconcile it with the actual file tree — do not trust the summary blindly.
6. Summarise findings in the opening section of the plan doc under the heading `## Project State at Plan Time` before listing any tasks.

Skipping this pre-work produces plans that contradict existing work or re-implement completed tasks. The Plan Reviewer will reject any plan whose `## Project State at Plan Time` section is missing or obviously stale.

### Hard stops — implementation MUST NOT start unless all of the following are true

1. A plan document exists at `docs/plan/{spec}_plan_v{N}.md`.
2. A plan review log exists at `docs/review/{spec}_plan_review_v{N}.log`.
3. The review log contains the line `Result: APPROVED` with no open CRITICAL or MAJOR issues.
4. The plan commit hash has been recorded in the task context.
5. `superpowers:subagent-driven-development` or `superpowers:executing-plans` has been invoked in the current session.

If any condition is unmet, **stop and route back to the appropriate stage**. Do not proceed, do not approximate, do not self-approve.

### Agent team composition (minimum)

Spawn at minimum these three roles as separate agents whenever starting implementation:
- **Architect agent** — owns plan and design docs only.
- **Implementer agent(s)** — owns source files only; one per independent task when parallel work is possible.
- **Code Reviewer agent** — owns review output only; never touches source files.

A solo agent performing all roles is **not permitted**. Role separation is enforced by file ownership rules (see Agent Cooperation Rules below).

### Implementation log format

Every impl log (`docs/impl/{spec}_implement_v{N}.md`) must maintain the following top-level structure:

```markdown
## Project State at Impl Time
<one paragraph: what exists, what is in progress, what is not started>

## CRITICAL
<!-- Code Reviewer appends here. Each entry has: task ref, description, status (OPEN/RESOLVED). -->
<!-- Implementer updates status to RESOLVED after fix is confirmed. -->
<!-- This section is the Team Lead's authoritative view of outstanding bugs and spec deviations. -->

### [TASK-N] <short title>
**Status:** OPEN | RESOLVED
**Found by:** Code Reviewer (impl review round N)
**Description:** <precise description of the bug or deviation>
**Fix applied:** <commit hash or "pending">

## Task Log
<per-task RED/GREEN evidence — detailed, for Implementer and Debugger use>
```

Rules for the CRITICAL section:
- The Code Reviewer is the **only** agent that appends new CRITICAL entries.
- The Implementer is the **only** agent that updates `Status:` from OPEN to RESOLVED.
- An entry must never be deleted — only marked RESOLVED with a fix reference.
- If the CRITICAL section is empty (no entries), the Code Reviewer writes `_(none)_` explicitly.

### Team lead — minimal reading contract

The team lead does **not** need to read the full impl log. To understand current project status, the team lead reads only:

1. Latest design spec (`docs/design/` — highest version number).
2. Approved plan (`docs/plan/` — highest version number with a corresponding APPROVED review log).
3. Plan review log (`docs/review/{spec}_plan_review_v{N}.log`).
4. The `## CRITICAL` section of the current impl log only — not the full Task Log.

If the CRITICAL section shows no open items and the plan tasks are complete, the team lead may proceed to the Verify gate. The team lead does not need to read the full Task Log unless debugging an escalation.

---

## Agent Cooperation Rules

1. **One owner per artifact.** Each file type has exactly one owning role. Implementers do not edit plan docs; Architects do not edit source files.

2. **No silent deviations.** If the plan is ambiguous or wrong, the Implementer must stop, flag the issue in a message to the Architect, and wait for a plan revision. Do not silently implement a different approach.

3. **Reviewers do not implement.** When a reviewer finds an issue they must return it with a precise description. The Implementer applies the fix. This keeps blame and ownership clear.

4. **Tests before claims.** No agent may claim a step is complete without running the relevant test command and recording the output. "It should work" is not evidence.

5. **Minimal scope.** Each agent operates only on files within its owned scope for the current task. Do not refactor, add comments, or clean up code outside the task boundary.

6. **Escalation path.** If an agent is blocked (build fails, spec is contradictory, test infrastructure is broken), it stops, records the blocker in the impl log, and sends a message to the team lead rather than working around it.

7. **Plan is the contract.** The approved plan is the implementation contract. New requirements discovered mid-implementation go back to the Architect for a plan revision — they are never absorbed silently into the current task.

8. **Tasks must be small and reviewable.** Each task in a plan must be small enough to answer three questions clearly:
   - **What needs to be done?** (specific change or addition)
   - **What problem does it resolve?** (why this change is needed)
   - **What is the expected result?** (how to verify completion)

   Code changes for a single task should be **less than 300 lines** (excluding tests). This keeps reviews focused, reduces cognitive load, and makes bugs easier to spot. If a task exceeds this limit, it must be split into smaller sub-tasks.

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
  pure-python-task1/    ← one directory per agent / branch
  pure-python-task2/
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
pip install -e tyche-core/
pip install -e tyche-cli/
```

Branch naming: `<spec>/<task>` — e.g. `pure-python/task-1-scaffold`, `pure-python/task-3-protocol`.

### Baseline verification

After setup, run the full test suite and confirm it is clean before touching any code:

```bash
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
- Python unit tests live in `tests/unit/`, integration tests in `tests/integration/`.
- Do not add `__init__.py` to `tests/` or any subdirectory of `tests/` — pytest handles discovery without it.

---

## Key Technical Rules for Implementers

**IPC Endpoints (IPC protocol):**
- Linux: `ipc:///tmp/tyche/nexus.sock`, `ipc:///tmp/tyche/bus_xsub.sock`, `ipc:///tmp/tyche/bus_xpub.sock`
- Windows: `ipc://tyche-nexus`, `ipc://tyche-bus-xsub`, `ipc://tyche-bus-xpub`
- Socket directory `/tmp/tyche/` must be created by Core on startup

**ZeroMQ:**
- DEALER sends frames as-is. No empty delimiter. ROUTER prepends identity.
- `correlation_id` is encoded as UTF-8 decimal string throughout the Python layer.
- `_register()` must verify `frames[2].decode() == str(self._correlation_id)` to reject stale ACKs.
- `_handle_nexus` must implement START / STOP / RECONFIGURE / STATUS commands.
- STOP command: send REPLY **before** setting `_stop_event`.

**Serialization:**
- MessagePack with `"_type"` discriminator field in every payload
- Types: `Tick`, `Quote`, `Trade`, `Bar`, `Order`, `OrderEvent`, `Ack`, `Position`, `Risk`
- Custom encoder/decoder in `tyche_cli/serialization.py`

**Module Configuration:**
- Each module has its own `config.json` file
- Loaded at startup, path via `--config` CLI arg or default `config.json` in working directory
- Core addresses passed via `--nexus`, `--bus-xsub`, `--bus-xpub` CLI args

**Launcher:**
- Separate `tyche-launcher` tool reads `launcher-config.json`
- Manages module lifecycle: start, monitor, restart on failure
- Modules are independent processes — Core does not spawn them directly

---

## gstack

Use the `/browse` skill from gstack for all web browsing. Never use `mcp__claude-in-chrome__*` tools.

Available gstack skills:
`/office-hours`, `/plan-ceo-review`, `/plan-eng-review`, `/plan-design-review`, `/design-consultation`, `/review`, `/ship`, `/browse`, `/qa`, `/qa-only`, `/design-review`, `/setup-browser-cookies`, `/retro`, `/investigate`, `/document-release`, `/codex`, `/careful`, `/freeze`, `/guard`, `/unfreeze`, `/gstack-upgrade`

---

## Current State

- **Phase:** Pure Python Architecture Rewrite — design complete, awaiting implementation plan
- **Design spec:** `docs/design/pure_python_architecture_design_v1.md` (in progress)
- **Plan:** None yet
- **Source tree:** `tyche-core/` and `tyche-cli/` packages to be created

Next step: Complete design doc, write plan, plan review, then implementation.
