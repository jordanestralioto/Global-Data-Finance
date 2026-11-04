---
name: 'OPSX: Archive'
description: Archive a completed OpenSpec change after verification and synchronization
category: Workflow
tags: [workflow, openspec, archive]
---

Archive a completed OpenSpec change after verification and synchronization.

**Input**: Optionally specify a change name after `/opsx:archive` (e.g., `/opsx:archive add-auth`). If omitted, you MUST ask the user to select from the active changes. Never infer or auto-select a change for `archive`.

**Selection policy**: `archive` requires explicit change selection whenever the request does not already identify the target change.

**Schema note**: Use `opsx status --change "<name>" --json` as the source of truth for artifact state, then inspect tasks and delta specs before moving anything.

**Lifecycle policy**: Archive is a mechanical finalization step. It requires
fresh decision-source preflight, a green completion gate, a passed semantic
verification report, complete tasks, and synchronized delta specs. No prompt,
warning, user confirmation, or legacy exemption overrides a red condition.

**Steps**

1. **If no change name provided, prompt for selection**

   Run `opsx list --json` to get available changes. Use an enumerated-selection capability when available. If it is unavailable or cannot represent every option, print every option in a numbered text list and wait for one explicit selection before continuing.

   Show only active changes (not already archived).
   Include the schema used for each change if available.

   **IMPORTANT**: Do NOT guess or auto-select a change. Always let the user choose.

2. **Run decision-source preflight and inspect the full bundle**

   ```bash
   opsx preflight --change "<name>" --json
   opsx status --change "<name>" --json
   ```

   Stop on any provenance, ownership, dependency, or artifact-state finding.
   Read the source envelope, proposal, design, tasks, every delta spec, and
   every corresponding main spec before deciding whether synchronization is
   complete.

3. **Assess and complete delta synchronization**

   If delta specs exist, compare them with the main specs. If any delta is
   missing, stale, or not provably synchronized, stop and require
   `/opsx:sync <name>` before archive. There is no "Archive without syncing"
   path. Sync requires its own exact change-name authorization and must run
   its own preflight; archive authorization cannot authorize sync.

   After synchronization, confirm the result is idempotent, contains no
   placeholder purpose/requirement, preserves unrelated main-spec content,
   and records the decision-source provenance.

4. **Generate fresh semantic evidence**

   Run `/opsx:verify <name>` and require it to write
   `evidence/verification-report.json` with verdict `passed`. The report must
   map every requirement, categorized scenario, and design decision to
   concrete implementation and test evidence, contain no in-contract
   blocker, and bind the exact current repository fingerprint. Do not reuse a
   report from a previous repository state or from a sibling change.

5. **Run the non-overridable completion gate**

   ```bash
   opsx-handoff --mode completion "<name>"
   ```

   Stop on any nonzero exit. There is no archive path with an interactive override.
   Do not move the change. Archive requires a complete bundle, all tasks
   closed, synchronized deltas, concrete output state, current green gate
   evidence, and a current passed semantic report.

6. **Check artifact completion status**

   Run `opsx status --change "<name>" --json` to check artifact completion.

   Parse the JSON to understand:

   - `schemaName`: The workflow being used
   - `artifacts`: List of artifacts with their status (`done` or other)

   **If any artifacts are not `done`:** stop and list them.

7. **Check task completion status**

   Read the tasks file (typically `tasks.md`) to check for incomplete tasks.

   Count tasks marked with `- [ ]` (incomplete) vs `- [x]` (complete).

   **If incomplete tasks are found:** stop and list them.

   **If no tasks file exists:** Proceed without task-related warning.

8. **Perform the archive**

   Create the archive directory if it doesn't exist:

   ```bash
   mkdir -p openspec/changes/archive
   ```

   Generate target name using current date: `YYYY-MM-DD-<change-name>`

   **Check if target already exists:**

   - If yes: Fail with error, suggest renaming existing archive or using different date
   - If no: Move the change directory to archive

   ```bash
   mv openspec/changes/<name> openspec/changes/archive/YYYY-MM-DD-<name>
   ```

9. **Display summary**

   Show archive completion summary including:

   - Change name
   - Schema that was used
   - Archive location
   - Spec sync status (synced / sync skipped / no delta specs)
   - Note about any warnings (incomplete artifacts/tasks)

**Output On Success**

```
## Archive Complete

**Change:** <change-name>
**Schema:** <schema-name>
**Archived to:** openspec/changes/archive/YYYY-MM-DD-<name>/
**Specs:** ✓ Synced to main specs

All artifacts complete. All tasks complete.
```

**Output On Success (No Delta Specs)**

```
## Archive Complete

**Change:** <change-name>
**Schema:** <schema-name>
**Archived to:** openspec/changes/archive/YYYY-MM-DD-<name>/
**Specs:** No delta specs

All artifacts complete. All tasks complete.
```

**Output On Success With Warnings**

```
## Archive Complete (with warnings)

**Change:** <change-name>
**Schema:** <schema-name>
**Archived to:** openspec/changes/archive/YYYY-MM-DD-<name>/
**Warnings:** None. This output is valid only when all final gates passed.
```

**Output On Error (Archive Exists)**

```
## Archive Failed

**Change:** <change-name>
**Target:** openspec/changes/archive/YYYY-MM-DD-<name>/

Target archive directory already exists.

**Options:**
1. Rename the existing archive
2. Delete the existing archive if it's a duplicate
3. Wait until a different date to archive
```

**Guardrails**

- Always prompt for change selection if not provided
- Use artifact graph (`opsx status --change "<name>" --json`) for completion checking
- Never archive when the completion gate is red; no warning or confirmation overrides it
- Never archive when decision-source preflight, semantic evidence, or delta
  synchronization is red or stale
- Preserve .openspec.yaml when moving to archive (it moves with the directory)
- Show clear summary of what happened
- If sync is requested, use /opsx:sync approach (agent-driven)
- If delta specs exist, always run the sync assessment and require the
  synchronized result before the final gate
- Never delete an existing archive target to make room for a new archive
