# Phase 1: cleanup and structural decision

Read this for initial diagnosis or cleanup. Open `PHASE_2.md` only after cleanup
leaves a concrete need to separate responsibilities.

## Before editing

- Read local instructions, the target and callers. Record the public interface,
  baseline failures and the native validation commands appropriate to the scope.
- Find reusable abstractions before introducing helpers. Check imports, exports,
  entrypoints and dynamically loaded callers relevant to the target.
- Keep one consumer-owned record. Initialize from `references/PLAN_TEMPLATE.md`
  only when no useful record already exists. An existing plan can be shortened
  in place; historical reports do not need to be converted.
- Reference the instruction that authorizes implementation. If the user asked
  to review a plan first, present the concrete cleanup proposal and wait. If the
  user already authorized the scoped implementation, proceed under that request.

## Diagnose and execute cleanup

Review these categories; record only findings and one short reason for each
category that needs no change:

| Category                      | Decision to capture                                                       |
| ----------------------------- | ------------------------------------------------------------------------- |
| Duplication                   | Consolidate repeated logic before moving it.                              |
| Reuse                         | Name the existing abstraction, or justify a new responsibility.           |
| Complexity                    | Explain a demonstrated gain and its validation; avoid speculative tuning. |
| Comments                      | Remove obsolete claims and clarify necessary rationale.                   |
| Naming and visibility         | Promote Python symbols with real public use and update consumers.         |
| Caller and contract migration | Identify affected callers, imports, exports and public behavior.          |

For material changes, record the affected paths, risk, validation and rollback.
Update that finding with its outcome rather than copying it into another report.
Run checks after cleanup, before assessing the need for extraction.

## Decide whether Phase 2 is needed

Record `PHASE_2_NEEDED: YES` only when both conditions hold:

1. Material size or complexity remains after cleanup.
2. A concrete responsibility boundary would improve cohesion, dependencies or
   independent verification.

Record the evidence and proposed benefit. Line count alone is insufficient.
If cleanup makes the target cohesive, set `PHASE_2_NEEDED: NO`, record checks and
remaining risks, and finish here. No extraction plan or second report is needed.

Do not expand into unrelated algorithm, API or architectural redesign. Revisit
authorization when the scope materially changes.
