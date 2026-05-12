# Agent Cooperation Guide


## Document Conventions

| Kind | Path template | Example |
|------|--------------|---------|
| Design spec | `docs/design/{spec}_design_v{N}.md` | `architecture_design_v1.md` |
| Implementation plan | `docs/plan/{spec}_plan_v{N}.md` | `plan_v1.md` |
| Spec review log | `docs/review/{spec}_design_v{N}_review_round{R}.log` | `architecture_design_v1_review_round1.log` |
| Plan review log | `docs/review/{spec}_plan_v{N}_review_round{R}.log` | `plan_v1_review_round1.log` (re-review of same plan: `_review_round2.log`) |
| Impl log | `docs/impl/{spec}_implement_v{N}.md` | new file each cycle |
| ADR (decision record) | `docs/adr/{spec}_adr_{slug}.md` | `module_interface_adr_handle_response.md` |

**Versioning Rule:** When a design spec is approved, all derived documents reset to v1. Design and plan version numbers are independent only within the same design cycle (design_v3.plan_v2 is acceptable; design_v3.plan_v1 tied to design_v2 is not).

**Review Round Rule:** A new plan version (`_v{N+1}`) is created only when the plan is structurally re-derived (e.g., after a design revision). A re-review of the same plan after fixing review conditions increments only the round counter (`_review_round{R+1}`). This prevents review log filenames from colliding with future plan versions.

---

## Mandatory Cycle Rule

Every feature, fix, or enhancement **must** follow the cycle below, **except** when Emergency Override Protocol applies. The cycle is a graph, not a line — feedback edges from IMPLEMENT back to PLAN and DESIGN are first-class.

```
                                        ┌────── plan amendment ───────┐
                                        │                             │
                                        ▼                             │
DESIGN ──► PLAN ──► PLAN REVIEW ──► CONFIRM ──► IMPLEMENT ──► REVIEW & VERIFY ──► COMMIT
   ▲          ▲                                     │                  │
   │          │                                     │                  │
   │          └──── DECISION_REQUIRED (ADR) ────────┘                  │
   │                                                                   │
   └──────────────────── design gap (bumps design version) ────────────┘

  Architect   Plan Reviewer   Team Lead    Implementer(s)    Code Reviewer    Team Lead
  writes      checks vs.      reads        TDD per task      checks vs.       commits with
  plan doc    spec, gates     APPROVED,    logs RED/GREEN    design+plan,     impl log
              one of three    spawns team  evidence in       runs full        Task Log
              verdicts        or routes    Task Log          test suite,      reference
                              ADR back                       appends
                                                             CRITICAL
                                                             to impl log
```

**Feedback edges:**
- **plan amendment** — small in-flight plan revision (≤30 LOC delta or ≤2 task additions/removals). Team lead approves unilaterally and records in impl log under a new `## Plan Amendments` section. Does not require re-review.
- **DECISION_REQUIRED → ADR** — plan review verdict signaling unanswered design choice (see Plan Review Verdicts below). Team lead writes ADR; plan auto-promotes to APPROVED on ADR completion.
- **design gap** — implementation discovers the design itself is incomplete or wrong. Bumps design to `_v{N+1}`; the current plan and any in-flight tasks are paused until design re-review completes. Recorded in impl log under `## Design Gaps Surfaced`.

### Plan Review Verdicts

A plan review log must end with one of three verdicts:

| Verdict | Meaning | Next step |
|---------|---------|-----------|
| `APPROVED` | Plan is implementable as written; no open issues. | Team lead confirms, spawns team, implementation begins. |
| `REJECTED` | Plan has CRITICAL or MAJOR issues that require Architect rework. | Architect revises plan in-place; reviewer re-reviews; round counter increments. |
| `DECISION_REQUIRED` | Plan is structurally sound but contains one or more open decisions the Architect cannot resolve alone (typically design-level forks). | Team lead writes ADR(s) at `docs/adr/{spec}_adr_{slug}.md` answering each open decision. Plan auto-promotes to `APPROVED` once all ADRs are committed. No second review round needed. |

`DECISION_REQUIRED` plans must have an `## Open Decisions` section listing each decision with: `id`, `question`, `options considered`, `default if not answered`, and `blocks tasks`. The reviewer cites this section when issuing the verdict.

### Plan amendment vs plan revision

| | Plan amendment | Plan revision |
|---|---------------|---------------|
| Trigger | Implementation finds plan needs minor tweak (rename, scope reduction, additional small task). | Plan is structurally wrong; rework needed. |
| Size | ≤30 LOC delta in plan; ≤2 task additions/removals; no change to task dependency graph. | Anything larger, or any change to existing task semantics. |
| Approval | Team lead, unilateral, recorded in impl log `## Plan Amendments`. | Full PLAN → PLAN REVIEW → CONFIRM cycle. New review round. |
| File output | Append to impl log; the plan doc itself updated in-place with a footnote. | Plan doc updated; new review log file with incremented round counter. |


### Required skills — in order

| Stage | Who invokes | Skill |
|-------|------------|-------|
| Read latest docs & current state | Architect agent | (required before writing plan — see below) |
| Write plan | Architect agent | `superpowers:writing-plans` |
| Review plan | Plan Reviewer agent | `feature-dev:code-reviewer` or dedicated review role; emits one of three verdicts |
| Write ADR (if `DECISION_REQUIRED`) | Team Lead | manual; one file per open decision |
| Start implementation | Team Lead | `superpowers:subagent-driven-development` or `superpowers:executing-plans` |
| Each impl step | Implementer agent | `superpowers:test-driven-development` |
| Review & verify | Code Reviewer agent | `superpowers:requesting-code-review` + `superpowers:verification-before-completion` — runs full test suite and appends CRITICAL issues to impl log |
| Commit | Team Lead | `commit-commands:commit-push-pr` — must reference at least one impl log Task Log entry |

---

## Agent Team — Roles and Boundaries

### Role Flexibility Tiers

The standard workflow uses strict role separation. However, four flexibility tiers exist to balance process rigor with operational velocity:

| Tier | Mode | Conditions | Permissions |
|------|------|------------|-------------|
| 1 | Standard | Normal feature work | Full role separation as documented |
| 1.5 | Lightweight | Single file, ≤100 LOC source change, no public API change, has tests, no design impact | Solo agent permitted (Architect + Implementer + Reviewer collapsed). Plan reduced to a one-paragraph task description + diff plan + self-review checklist. Skip Plan Review; one independent reviewer signs off after impl. TDD still required. |
| 2 | Fast-track | Trivial fixes, documentation-only changes | Architect may edit non-code files; Implementer may fix obvious typos in tests without round-trip |
| 3 | Emergency | Production incidents, critical security fixes | Emergency Override Protocol applies |

**Escalation to a higher tier** requires team lead notification and post-hoc documentation in the impl log. **De-escalation** (e.g., a Tier 1.5 task that turns out to need design changes) requires stopping immediately and re-entering at Tier 1 PLAN.

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
2. A plan review log exists at `docs/review/{spec}_plan_v{N}_review_round{R}.log` (highest round wins).
3. The latest review log contains the line `Result: APPROVED` with no open CRITICAL or MAJOR issues. If the latest verdict is `DECISION_REQUIRED`, all referenced ADRs must exist under `docs/adr/` and be committed before implementation may start.
4. The plan commit hash has been recorded in the task context.
5. `superpowers:subagent-driven-development` or `superpowers:executing-plans` has been invoked in the current session.

### Hard stops — commit MUST NOT happen unless

1. The impl log has at least one Task Log entry referencing the current task with RED/GREEN evidence.
2. The CRITICAL section has no `OPEN` items for the task being committed.
3. Code Reviewer has emitted a Review & Verify pass (full test suite green) for the current task.

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
<!-- Anyone listed in the Source enum below may append entries. -->
<!-- Implementer updates status to RESOLVED after fix is confirmed. -->
<!-- This section is the Team Lead's authoritative view of outstanding bugs and spec deviations. -->

### [TASK-N] <short title>
**Status:** OPEN | RESOLVED
**Source:** code-review | external-review | post-mortem | self-report
**Found by:** <agent name or human reviewer; for code-review include round number>
**Description:** <precise description of the bug or deviation>
**Fix applied:** <commit hash or "pending">

## Plan Amendments
<!-- Team lead appends here when applying in-flight plan amendments (≤30 LOC plan delta). -->

### [AMEND-N] <short title>
**Date:** YYYY-MM-DD
**Approved by:** <team lead name>
**Amendment:** <what changed in the plan>
**Reason:** <why; usually impl finding>

## Design Gaps Surfaced
<!-- Recorded when implementation discovers the design itself is incomplete or wrong. -->
<!-- Triggers a design version bump; current plan is paused until new design is reviewed. -->

### [GAP-N] <short title>
**Surfaced during:** TASK-N
**Gap:** <what the design does not specify or specifies incorrectly>
**Action:** <design version bumped from vN to vN+1 | ADR written | other>

## Task Log
<per-task RED/GREEN evidence — detailed, for Implementer and Debugger use>
```

Rules for the CRITICAL section:
- Allowed `Source:` values are `code-review`, `external-review`, `post-mortem`, `self-report`. Any agent or human reviewer may append; the Source tag identifies origin.
- The Implementer is the **only** agent that updates `Status:` from OPEN to RESOLVED.
- An entry must never be deleted — only marked RESOLVED with a fix reference.
- If the CRITICAL section is empty (no entries), write `_(none)_` explicitly.

Rules for Plan Amendments:
- Only the Team Lead writes here.
- Each amendment must stay within the size envelope defined in **Plan amendment vs plan revision** above. Anything larger triggers a full plan revision instead.

Rules for Design Gaps Surfaced:
- Any agent may append. The Team Lead decides whether to bump the design version or write an ADR.
- When a design version is bumped, the current plan is paused; downstream tasks must wait for the new design to be reviewed and a fresh plan derived.

### Team lead — minimal reading contract

The team lead does **not** need to read the full impl log. To understand current project status, the team lead reads only:

1. Latest design spec (`docs/design/` — highest version number).
2. Approved plan (`docs/plan/` — highest version number with a corresponding APPROVED review log).
3. Latest plan review log (`docs/review/{spec}_plan_v{N}_review_round{R}.log` — highest round wins).
4. Any ADRs referenced by `DECISION_REQUIRED` verdicts (`docs/adr/{spec}_adr_*.md`).
5. The `## CRITICAL`, `## Plan Amendments`, and `## Design Gaps Surfaced` sections of the current impl log only — not the full Task Log.

If the CRITICAL section shows no open items, no design gaps are pending, and the plan tasks are complete, the team lead may proceed to commit. The team lead does not need to read the full Task Log unless debugging an escalation.

---

## Agent Cooperation Rules

1. **One owner per artifact.** Each file type has exactly one owning role. Implementers do not edit plan docs; Architects do not edit source files (Tier 2+ exceptions apply).

2. **No silent deviations.** If the plan is ambiguous or wrong, the Implementer must stop, flag the issue in a message to the Architect, and wait for a plan revision. Do not silently implement a different approach.

3. **Reviewers do not implement.** When a reviewer finds an issue they must return it with a precise description. The Implementer applies the fix. This keeps blame and ownership clear.

4. **Tests before claims.** No agent may claim a step is complete without running the relevant test command and recording the output. "It should work" is not evidence.

5. **Minimal scope.** Each agent operates only on files within its owned scope for the current task. Do not refactor, add comments, or clean up code outside the task boundary.

6. **Escalation path.** If an agent is blocked (build fails, spec is contradictory, test infrastructure is broken), it stops, records the blocker in the impl log, and sends a message to the team lead rather than working around it.

7. **Plan is the contract — but the contract is amendable.** The approved plan is the implementation contract. Mid-implementation findings route as follows:
   - **Small adjustments** (within the amendment envelope) — Team Lead approves, records in impl log `## Plan Amendments`. No re-review.
   - **Structural changes** — back to Architect for plan revision; full PLAN → PLAN REVIEW cycle with new round counter.
   - **Design-level gaps** — recorded in impl log `## Design Gaps Surfaced`; bump design version and re-derive plan. Implementation pauses.
   - **Open decisions raised by reviewer** — `DECISION_REQUIRED` verdict triggers ADR(s); plan auto-promotes to APPROVED on ADR commit.

   New requirements are never absorbed silently into a current task (Emergency Override excepted).

8. **Tasks must be small and reviewable.** Each task in a plan must be small enough to answer three questions clearly:
   - **What needs to be done?** (specific change or addition)
   - **What problem does it resolve?** (why this change is needed)
   - **What is the expected result?** (how to verify completion)

   Code changes for a single task should be **less than 300 lines** (excluding tests). This keeps reviews focused, reduces cognitive load, and makes bugs easier to spot. If a task exceeds this limit, it must be split into smaller sub-tasks.

9. **Commits must be traceable.** Every commit message must reference at least one impl log Task Log entry (e.g., `TASK-3 GREEN`). Commits without a Task Log reference are rejected by the Team Lead at the commit gate. This makes RED/GREEN evidence non-optional in practice and prevents silent skips of TDD.

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
| Design gap surfaced mid-implementation | Impl finds design hole the plan cannot cover | Append `[GAP-N]` to impl log `## Design Gaps Surfaced`; pause affected tasks; bump design version; re-derive plan |
| ADR pending after `DECISION_REQUIRED` verdict | Plan stuck in non-APPROVED state | Team lead writes ADR(s); implementation cannot start until all referenced ADRs are committed |
| Plan amendment exceeds size envelope | Team lead drafts amendment that touches >30 LOC of plan or alters task graph | Reject amendment; route through full plan revision instead |

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