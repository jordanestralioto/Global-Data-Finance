---
name: 'OPSX: Sync'
description: Sync delta specs from an OpenSpec change to canonical main specs
category: Workflow
tags: [workflow, openspec, specs, sync]
---

Sync delta specs from a change to main specs.

This is a deterministic operation. The agent explains and authorizes the exact
scope; `sync_specs.py` owns every main-spec mutation.

**Input**: Optionally specify a change name after `/opsx:sync` (e.g., `/opsx:sync add-auth`). If omitted, you MUST ask the user to select a change from the active changes. Never infer or auto-select a change for `sync`.

**Selection policy**: `sync` always requires explicit change selection unless the change name is already present in the request.

**Schema note**: Use the actual delta spec files and main spec files as the source of truth. Do not assume a fixed schema beyond the files that exist in the selected change.

**Decision-source policy**: `sync` is permitted only after the selected change
passes the decision-source preflight. The declared source, digest, decision
IDs, dependencies, and sibling ownership are binding. A sync authorization
does not authorize artifact creation, implementation, or archive.

**Steps**

1. **If no change name provided, prompt for selection**

   Run `opsx list --json` to get available changes. Use an enumerated-selection capability when available. If it is unavailable or cannot represent every option, print every option in a numbered text list and wait for one explicit selection before continuing.

   Show changes that have delta specs (under `specs/` directory).

   **IMPORTANT**: Do NOT guess or auto-select a change. Always let the user choose.

2. **Run decision-source preflight**

   ```bash
   opsx preflight --change "<name>" --json
   ```

   Stop on any nonzero exit or any finding. Do not infer missing decisions
   from the delta text, and do not continue with a partial or stale source
   envelope.

3. **Read the complete sync scope before authorization**

   Read `.openspec.yaml`, the declared decision source, proposal, design,
   tasks, every delta spec, and every corresponding main spec. Resolve the
   exact capability and requirement mapping before asking for authorization.
   A delta-only read is insufficient.

4. **Find delta specs**

   Look for delta spec files in `openspec/changes/<name>/specs/*/spec.md`.

   Each delta spec file contains sections like:

   - `## ADDED Requirements` - New requirements to add
   - `## MODIFIED Requirements` - Changes to existing requirements
   - `## REMOVED Requirements` - Requirements to remove
   - `## RENAMED Requirements` - Requirements to rename (FROM:/TO: format)

   If no delta specs found, inform user and stop.

5. **Request explicit sync authorization**

   Show the selected change name, decision-source digest, every capability,
   and the exact add/modify/remove/rename operations. Ask the user to
   authorize this sync by its exact change name. Do not reuse authorization
   for another change, artifact operation, or archive operation.

6. **Apply the authorized operations mechanically**

   Run exactly:

   ```bash
   opsx-sync --change "<name>" --json
   ```

   `ADDED` appends only an absent full block and rejects a conflicting existing
   name. `MODIFIED` replaces the complete existing block and rejects an absent
   owner. `REMOVED` guarantees absence. `RENAMED` changes only the declared
   heading and rejects ambiguous old/new coexistence. A new capability requires
   a concrete `## Purpose` in its delta. The command preserves untouched blocks
   byte-for-byte and writes decision-source provenance.

7. **Validate the synchronized result**

   Re-run the decision-source preflight and inspect the complete diff. Confirm
   that the target main specs contain the delta requirements and no
   placeholders, and that unrelated main specs were not changed. If the
   result is unclear or not idempotent, stop and report the discrepancy.

   Run the canonical read-only check:

   ```bash
   opsx-sync --change "<name>" --check --json
   ```

   It must exit zero with no finding. Inspect the diff and confirm that no
   unrelated canonical spec changed.

8. **Show summary**

   After applying all changes, summarize:

   - Which capabilities were updated
   - What changes were made (requirements added/modified/removed/renamed)

**Delta Spec Format Reference**

```markdown
## ADDED Requirements

### Requirement: New Feature

The system SHALL do something new.

#### Scenario: Basic case

- **WHEN** user does X
- **THEN** system does Y

## MODIFIED Requirements

### Requirement: Existing Feature

#### Scenario: New scenario to add

- **WHEN** user does A
- **THEN** system does B

## REMOVED Requirements

### Requirement: Deprecated Feature

## RENAMED Requirements

- FROM: `### Requirement: Old Name`
- TO: `### Requirement: New Name`
```

**Key Principle: Full-block deterministic operations**

`MODIFIED` always carries the entire updated requirement. Partial scenario
patches and implicit operation conversion are invalid.

**Output On Success**

```
## Specs Synced: <change-name>

Updated main specs:

**<capability-1>**:
- Added requirement: "New Feature"
- Modified requirement: "Existing Feature" (added 1 scenario)

**<capability-2>**:
- Created new spec file
- Added requirement: "Another Feature"

Main specs are now updated. The change remains active - archive when implementation is complete.
```

**Guardrails**

- Read both delta and main specs before making changes
- Preserve existing content not mentioned in delta
- If something is unclear, ask for clarification
- Show what you're changing as you go
- Never use `Archive without syncing`; archive requires synchronized deltas
  and a newly generated semantic verification report
- The operation must be idempotent - running twice must give the same result
- Never hand-edit a main spec to hide an unsatisfied decision-source finding
