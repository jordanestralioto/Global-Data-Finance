# Refactor: {{target}}

- Date: {{date}}
- Target: `{{target}}`
- Authorization: record the existing instruction and its scope; respect requested approval boundaries.
- Baseline: public imports, callers, responsibilities and current check results.
- Validation commands: select the consumer's required checks.

## Phase 1: cleanup

Keep findings concise. For an empty category, one reason is enough. Add rows for
material findings, including affected paths, risk, validation and rollback.
Update the outcome in place after execution.

| Category                      | Finding or reason for no change | Change and validation | Outcome |
| ----------------------------- | ------------------------------- | --------------------- | ------- |
| Duplication                   |                                 |                       |         |
| Reuse                         |                                 |                       |         |
| Complexity                    |                                 |                       |         |
| Comments                      |                                 |                       |         |
| Naming and visibility         |                                 |                       |         |
| Caller and contract migration |                                 |                       |         |

## Decision after cleanup

- PHASE_2_NEEDED: pending
- Evidence: remaining size or complexity, responsibility boundary and expected benefit.
- Cleanup validation: commands, exit codes and unresolved failures.

If Phase 2 is unnecessary, finish with validation and risks below.

## Phase 2: extraction, only when needed

- Canonical public entrypoint:
- Legacy file to remove:
- Responsibility map and extraction order:
- Public symbols, internal symbols and caller migrations:
- Structural check: command, selected paths, result and limitations.

## Completion

- Native validation: commands, exit codes and evidence paths.
- Outcome: completed changes or unresolved items; reference the findings above.
- Remaining risks and unverified behavior:
- Rollback: restore the affected source, exports and callers together.
