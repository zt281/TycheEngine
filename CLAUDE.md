# Agent Cooperation Guide


## Document Conventions

| Kind | Path template | Example |
|------|--------------|---------|
| Design spec | `docs/design/{spec}_design_v{N}.md` | `architecture_design_v1.md` |
| Implementation plan | `docs/plan/{spec}_plan_v{N}.md` | `plan_v1.md` |
| Spec review log | `docs/review/{spec}_review_v{N}.log` | `review_v1.log` |
| Plan review log | `docs/review/{spec}_plan_review_v{N}.log` | `plan_review_v1.log` |
| Impl log | `docs/impl/{spec}_implement_v{N}.md` | new file each cycle |

**Versioning Rule:** When a design spec is approved, all derived documents reset to v1. Design and plan version numbers are independent only within the same design cycle (design_v3.plan_v2 is acceptable; design_v3.plan_v1 tied to design_v2 is not).

---

## Mandatory Cycle Rule

Every feature, fix, or enhancement **must** follow the exact cycle defined above, **except** when Emergency Override Protocol applies.

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

---

## Agent Team — Roles and Boundaries

### Role Flexibility Tiers

The standard workflow uses strict role separation. However, three flexibility tiers exist to balance process rigor with operational velocity:

| Tier | Mode | Conditions | Permissions |
|------|------|------------|-------------|
| 1 | Standard | Normal feature work | Full role separation as documented |
| 2 | Fast-track | Trivial fixes, documentation-only changes | Architect may edit non-code files; Implementer may fix obvious typos in tests without round-trip |
| 3 | Emergency | Production incidents, critical security fixes | Emergency Override Protocol applies |

**Escalation to a higher tier** requires team lead notification and post-hoc documentation in the impl log.

---

### Skill Verification

Before relying on skill output:
- Verify skill completed without errors in the response
- Spot-check output against expected format (plans must have tasks, reviews must have verdicts)
- If skill behavior seems inconsistent, escalate to team lead

### Plan phase — mandatory pre-work (Architect)

Before invoking `superpowers:writing-plans` or writing a single line of a plan, the Architect agent **must**:

1. Read the current design spec (`docs/design/` — latest version by number).
2. Read all existing plan docs for the **current design cycle only** and their review logs to understand what has already been approved, rejected, or revised.
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

A solo agent performing all roles is **not permitted** (except under Emergency Override). Role separation is enforced by file ownership rules (see Agent Cooperation Rules below).

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

1. **One owner per artifact.** Each file type has exactly one owning role. Implementers do not edit plan docs; Architects do not edit source files (Tier 2+ exceptions apply).

2. **No silent deviations.** If the plan is ambiguous or wrong, the Implementer must stop, flag the issue in a message to the Architect, and wait for a plan revision. Do not silently implement a different approach.

3. **Reviewers do not implement.** When a reviewer finds an issue they must return it with a precise description. The Implementer applies the fix. This keeps blame and ownership clear.

4. **Tests before claims.** No agent may claim a step is complete without running the relevant test command and recording the output. "It should work" is not evidence.

5. **Minimal scope.** Each agent operates only on files within its owned scope for the current task. Do not refactor, add comments, or clean up code outside the task boundary.

6. **Escalation path.** If an agent is blocked (build fails, spec is contradictory, test infrastructure is broken), it stops, records the blocker in the impl log, and sends a message to the team lead rather than working around it.

7. **Plan is the contract.** The approved plan is the implementation contract. New requirements discovered mid-implementation go back to the Architect for a plan revision — they are never absorbed silently into the current task (Emergency Override excepted).

8. **Tasks must be small and reviewable.** Each task in a plan must be small enough to answer three questions clearly:
   - **What needs to be done?** (specific change or addition)
   - **What problem does it resolve?** (why this change is needed)
   - **What is the expected result?** (how to verify completion)

   Code changes for a single task should be **less than 300 lines** (excluding tests). This keeps reviews focused, reduces cognitive load, and makes bugs easier to spot. If a task exceeds this limit, it must be split into smaller sub-tasks.

---

## Process Failure Modes

When the process itself encounters problems, follow these recovery paths:

| Failure | Detection | Recovery |
|---------|-----------|----------|
| Plan Reviewer unavailable | SLA (2min) breached | Team lead assigns alternate reviewer or escalates to Emergency tier |
| Conflicting plans created | Two plans reference same design_vN | Team lead selects one; other is archived with note |
| Code Reviewer offline mid-review | No response for 2min | Implementer pings; after 3mins, team lead reassigns |
| Verification skill fails intermittently | Flaky pass/fail on same code | Run 3x; if inconsistent, treat as test infrastructure bug |
| Architect and Implementer disagree on spec | Flag raised during implementation | Team lead convenes both; Architect decides; document decision |

---

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

**TDD Task Status:** See "Gate: Implement step → Next step" for task status flow during TDD.

---

## Testing Requirements

### Test Categories

| Category | Location | Requirements |
|----------|----------|--------------|
| Unit tests | `tests/unit/` | ≥80% line coverage, mock external deps, run in <5 seconds |
| Integration tests | `tests/integration/` | Full stack minus external venues, may use real ZeroMQ sockets |
| Performance tests | `tests/perf/` | p99 latency < 10μs for dispatch path, record in CI benchmarks |
| Property tests | `tests/property/` | All serialization/deserialization round-trips, use hypothesis |

### Coverage Requirements

- Minimum line coverage: **80%** for unit tests
- New code must have **≥90%** coverage
- Coverage regression >2% blocks commit
- Exclude `if __name__ == "__main__":` blocks and type-checking imports from coverage

### Additional Test Requirements

- **Reconnection logic:** Test Nexus disappearance/reappearance scenarios
- **Configuration validation:** Cover edge cases and invalid input rejection
- **Serialization round-trips:** Verify `Decimal` precision is preserved through encode/decode