---
name: 'OPSX: Review'
description: Rigorously audit an OpenSpec change before implementation against system principles, architecture, handoff completeness, and sabatina alignment
category: Workflow
tags: [workflow, openspec, review, audit]
---

# 🕵️ OpenSpec Review Workflow (`/opsx:review`)

Act as a **Rigorously Skeptical Technical Reviewer**. Your mission is to audit the OpenSpec change in `openspec/changes/<change-name>/` before implementation, identifying specification gaps, architectural violations, inconsistencies with the decision source (sabatina), and regression risks.

> **Golden Rule:** Do not implement code, do not edit change artifacts, and do not provide hollow praise. Focus strictly on finding defects, omissions, unverified assumptions, and contradictions.

______________________________________________________________________

## Instructions

### 1. Selection & Mechanical Preflight

1. If no change name was provided in the command, run `opsx list --json` and prompt for explicit change selection.
2. Execute the repository's mechanical gate to validate structural bundle integrity:
   ```bash
   opsx-handoff --mode bundle "<change-name>"
   ```
3. Read all artifacts for the change (`proposal.md`, `specs/*/spec.md`, `design.md`, `tasks.md`, and `.openspec.yaml` if present).

______________________________________________________________________

### 2. Sabatina Alignment (Decision Source)

If the change references a decision source or sabatina (in `.openspec.yaml`, `proposal.md`, or `docs/internal/sabatina/<slug>.md`):

- **Decision Fidelity**: Does the OpenSpec strictly adhere to all recorded answers in the decisions (`Qn`)?
- **Rejected Alternatives**: Did `design.md` or `tasks.md` accidentally reintroduce any approach explicitly discarded during the inquiry?
- **Invariants & Non-Goals**: Are the invariants and scope boundaries established in the sabatina fully preserved in `proposal.md` (`Non-Goals`) and `specs/`?
- **Orphan Decisions & Hallucinations**: Did the OpenSpec introduce major business requirements or architectural choices that were never deliberated in the decision source?

______________________________________________________________________

### 3. Critical Audit Axes

Cross-reference the change artifacts with the existing codebase across these dimensions:

#### A. Architecture, Coupling & Circular Imports

- Do `design.md` or `tasks.md` introduce mutual imports or circular dependencies between modules?
- Are responsibilities cleanly decoupled (Single Responsibility), or is there a risk of inflating existing god files / god components?
- Are architectural boundaries, package hierarchy, and public contracts respected?

#### B. Code Duplication (DRY) & Reuse

- Does the proposal invent new utilities, helpers, types, or schemas that already exist in the repository?
- Does the plan reuse standard patterns, existing abstractions, and official entry points instead of reinventing them?

#### C. Handoff Completeness (Junior Developer Standard)

- Could a junior developer with no prior context implement this change end-to-end without guessing intent or asking questions?
- Do tasks in `tasks.md` specify exact repository-relative file paths and concrete test commands (no globs, loose filenames, or generic folders)?
- Is there a complete `## 0. Traceability` table linking every requirement and scenario to concrete implementation and test tasks?

#### D. Boundary Scenarios & Failure Modes

- Does every requirement in `specs/` explicitly cover `[happy]`, `[negative]`, and `[boundary]` with clear `WHEN` and `THEN` clauses?
- How are partial failures, race conditions, concurrency, invalid inputs, and timeouts handled?
- Is there a clear rollback, migration reversibility, or failure recovery strategy?

#### E. Security & Code Integrity

- Is there strict input validation, authorization boundaries (BOLA/IDOR), and tenant/data isolation?
- Does the plan rely on forbidden hacks (`// @ts-ignore`, `eslint-disable`, `# noqa`, type bypasses)?

______________________________________________________________________

### 4. Review Report Format

Present the structured verdict grouping findings by severity:

```markdown
## 📋 OpenSpec Review: <change-name>

**Bundle Gate:** [ ✅ Passed | ❌ Failed ]
**Sabatina Alignment:** [ ✅ Aligned | ⚠️ Divergences Found | ℹ️ N/A (No Sabatina) ]
**Overall Verdict:** [ 🟢 APPROVED FOR APPLY | 🟡 ADJUSTMENTS REQUIRED | 🔴 BLOCKED ]

---

### 🔴 Blockers
*Critical issues that must be fixed in the artifacts before `/opsx:apply` can proceed.*
- **[Axis/File]**: Description of defect, concrete impact/risk, and required remedy.

### 🟡 Warnings
*Omissions, potential duplications, or architectural concerns that warrant revision.*
- **[Axis/File]**: Description of risk and recommendation.

### 💡 Suggestions
*Minor improvements to naming, readability, or ergonomics that do not block implementation.*
- **[Axis/File]**: Actionable suggestion.

---

### 🎯 Next Steps
- If **Blockers** exist: *Update change artifacts with `/opsx:continue` before invoking `/opsx:apply`.*
- If **Approved**: *Proceed to implementation with `/opsx:apply <change-name>`.*
```
