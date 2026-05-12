---
name: Agent Team Structure
description: Tyche Engine agent team composition and roles per CLAUDE.md Agent Cooperation Guide
type: reference
---

## Agent Team: tyche-engine

| Role | Name | File Ownership | Responsibilities |
|------|------|----------------|------------------|
| **Team Lead** | team-lead | Coordination only | Task assignment, verification, merge decisions, minimal reading contract |
| **Architect** | architect | `docs/design/`, `docs/plan/` | Design specs, implementation plans, mandatory pre-work before writing plans |
| **Plan Reviewer** | plan-reviewer | `docs/review/{spec}_plan_review_v{N}.log` | Reviews plans vs specs, gates APPROVED status |
| **Code Reviewer** | code-reviewer | `docs/review/{spec}_review_v{N}.log`, `docs/impl/` (CRITICAL section append only) | Reviews implementation vs design+plan, CRITICAL issue tracking |
| **Implementer** | implementer | `src/`, `tests/` | Source code, TDD execution (RED→GREEN), test coverage ≥90% |

## Mandatory Cycle (CLAUDE.md §Mandatory Cycle Rule)

```
PLAN → PLAN REVIEW → CONFIRM → IMPLEMENT → IMPL REVIEW → VERIFY → COMMIT
  │         │           │          │             │           │        │
Architect  Plan       Team    Implementer   Code       Team     Team
           Reviewer   Lead      (TDD)       Reviewer   Lead     Lead
```

## Hard Stops for Implementation Start

Implementation CANNOT start unless ALL true:
1. ✓ Plan doc exists at `docs/plan/{spec}_plan_v{N}.md`
2. ✓ Plan review log exists at `docs/review/{spec}_plan_review_v{N}.log`
3. ✓ Review log contains `Result: APPROVED` with no open CRITICAL/MAJOR issues
4. ✓ Plan commit hash recorded in task context
5. ✓ `superpowers:subagent-driven-development` or `superpowers:executing-plans` invoked

## File Ownership Rules (Strict)

| Agent | Owns (read/write) | Never Edits |
|-------|-------------------|-------------|
| Architect | `docs/design/`, `docs/plan/` | `src/`, `tests/`, review output, impl logs |
| Plan Reviewer | Plan review logs | Source files, plan docs, design specs, impl logs |
| Code Reviewer | Impl review logs, CRITICAL section (append only) | Source files, plan docs, design specs |
| Implementer | `src/`, `tests/` | `docs/design/`, `docs/plan/`, review output |

## TDD Rules (Non-Negotiable)

1. **RED first**: Test file exists and fails (compile/assertion error, not import)
2. **GREEN second**: Implementation makes test pass
3. Record evidence in `## Task Log` section of impl log
4. NO `__init__.py` in `tests/` or any subdirectory
5. Tasks <300 lines of code change

## CRITICAL Section Rules (docs/impl/)

- **Code Reviewer ONLY**: Appends new CRITICAL entries
- **Implementer ONLY**: Updates Status from OPEN to RESOLVED
- **Never delete entries** — only mark RESOLVED with fix reference
- Empty section: write `_(none)_` explicitly

## Team Lead — Minimal Reading Contract

To check status, read ONLY:
1. Latest design spec (`docs/design/` — highest version)
2. Approved plan + plan review log (`docs/plan/`, `docs/review/`)
3. `## CRITICAL` section of current impl log (not full Task Log)

## Communication

```python
SendMessage(to="architect", summary="...", message="...")
SendMessage(to="plan-reviewer", summary="...", message="...")
SendMessage(to="code-reviewer", summary="...", message="...")
SendMessage(to="implementer", summary="...", message="...")
```

## Team Config Location

`C:\Users\alan\.claude\teams\tyche-engine\config.json`
