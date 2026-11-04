---
name: 'OPSX: Apply'
description: Implement tasks from an OpenSpec change using Developer Engineer
category: Workflow
tags: [workflow, openspec, apply, implementation]
---

Implement tasks from an OpenSpec change using the **Developer Engineer** agent (`developer-engineer`).

**Agent**: Always activate the **Developer Engineer** agent (`developer-engineer`) as the primary executor before proceeding with any steps below. Role activation never selects, recommends, infers, ranks, or switches a model and never requires model metadata; the user-selected model remains authoritative.

**Input**: Optionally specify a change name (e.g., `/opsx:apply add-auth`). If omitted, `apply` is the only OPSX workflow allowed to infer from conversation context or auto-select when there is exactly one safe active candidate. If that is not true, you MUST prompt for available changes.

**Selection policy exception**: Unlike `continue`, `sync`, `archive` and `verify`, this workflow may infer or auto-select the change when it is safe to do so. Always announce the chosen change and how to override it.

**Schema note**: Use `opsx status --change "<name>" --json` and `opsx instructions apply --change "<name>" --json` as the source of truth for schema, context files and task state. Do not assume `spec-driven` unless the CLI output indicates it.

**Write boundary**: Before any implementation write, run
`opsx preflight --change "<name>" --json`. Then run the
bundle gate and stop on either failure. Announce the exact selected change and
request a separate, explicit authorization for this apply invocation. Source
confirmation, artifact-creation approval, or authorization for a sibling
change is not apply authorization. If authorization is absent, stop before
modifying code, tests, tasks, evidence, or canonical documentation.

**Steps**

1. **Activate Developer Engineer Agent**

   Invoke and adopt the identity and rules of the **Developer Engineer** agent (`developer-engineer`). All code modifications, verifications, and task updates in this workflow MUST be executed under this agent's identity and governance.

2. **Select the change (exception policy)**

   If a name is provided, use it. Otherwise:

   - Infer from conversation context if the user mentioned a change
   - Auto-select if only one active change exists
   - If ambiguous, run `opsx list --json` to get available changes. Use an enumerated-selection capability when available. If it is unavailable or cannot represent every option, print every option in a numbered text list and wait for one explicit selection before continuing.

   Always announce: "Using change: <name>" and how to override (e.g., `/opsx:apply <other>`).

3. **Check status to understand the schema**

   ```bash
   opsx status --change "<name>" --json
   ```

   Parse the JSON to understand:

   - `schemaName`: The workflow being used (e.g., "spec-driven")
   - Which artifact contains the tasks (typically "tasks" for spec-driven, check status for others)

4. **Get apply instructions**

   Run the decision-source preflight first:

   ```bash
   opsx preflight --change "<name>" --json
   ```

   Stop on any finding, including a tampered source, uncovered decision ID,
   duplicate sibling ownership, unknown dependency, or dependency cycle.

   First hard-block ambiguous or incomplete spec-driven documentation:

   ```bash
   opsx-handoff --mode bundle "<name>"
   ```

   Stop on any error. There is no interactive override for a red bundle gate.

   ```bash
   opsx instructions apply --change "<name>" --json
   ```

   *(CLI Fallback: If `opsx` fails, read the artifact files directly from `openspec/changes/<name>/`)*

   This returns:

   - Context file paths (varies by schema)
   - Progress (total, complete, remaining)
   - Task list with status
   - Dynamic instruction based on current state

   After the bundle is green and before starting task 1, ask: **Authorize
   apply for exactly `<name>` in this invocation?** Use a structured
   confirmation capability when available; otherwise present numbered text
   choices and wait. A negative or missing answer is a hard stop.

   **Handle states:**

   - If `state: "blocked"` (missing artifacts): show message, suggest using `/opsx:continue`
   - If `state: "all_done"`: report that implementation is already complete
   - Otherwise: proceed to implementation

5. **Read context files**

   Read the files listed in `contextFiles` from the apply instructions output.
   The files depend on the schema being used:

   - **spec-driven**: proposal, specs, design, tasks
   - Other schemas: follow the contextFiles from CLI output

6. **Show current progress**

   Display:

   - Schema being used
   - Progress: "N/M tasks complete"
   - Remaining tasks overview
   - Dynamic instruction from CLI

7. **Implement tasks (loop until done or blocked)**

   For each pending task:

   - Show which task is being worked on
   - Make the code changes required
   - Keep changes minimal and focused
   - **Execute project tests/validation** (e.g. project test suite, linters) relevant to the changes to ensure no regressions
   - Mark task complete in the tasks file: `- [ ]` → `- [x]` **only AFTER verification passes**
   - Continue to next task

   **Pause if:**

   - Task is unclear → ask for clarification
   - Implementation reveals a design issue → suggest updating artifacts
   - Error or blocker encountered → report and wait for guidance
   - User interrupts

8. **Produce state-bound evidence and run the apply-exit gate**

   After every task is implemented and its focused validation passes, run
   the project's configured `validationCommand` (declared in
   `openspec/handoff.json`, substituting `<change>` with `<name>` to produce
   `openspec/changes/<name>/evidence/gate-report.json`) and then run the
   apply-exit gate:

   ```bash
   <validationCommand>
   opsx-handoff --mode apply "<name>"
   ```

   Report implementation success only if both commands exit zero. This gate
   deliberately does not claim semantic verification or canonical sync; those
   remain owned by `/opsx:verify` and `/opsx:sync` before completion/archive.

9. **On completion or pause, show status**

   Display:

   - Tasks completed this session
   - Overall progress: "N/M tasks complete"
   - If all done: suggest `/opsx:verify`, not archive
   - If paused: explain why and wait for guidance

**Output During Implementation**

```
## Implementing: <change-name> (schema: <schema-name>)

Working on task 3/7: <task description>
[...implementation happening...]
✓ Task complete

Working on task 4/7: <task description>
[...implementation happening...]
✓ Task complete
```

**Output On Completion**

```
## Implementation Complete

**Change:** <change-name>
**Schema:** <schema-name>
**Progress:** 7/7 tasks complete ✓

### Completed This Session
- [x] Task 1
- [x] Task 2
...

Implementation is complete. Continue with `/opsx:verify`; archive remains
blocked until semantic verification and deterministic sync also pass.
```

**Output On Pause (Issue Encountered)**

```
## Implementation Paused

**Change:** <change-name>
**Schema:** <schema-name>
**Progress:** 4/7 tasks complete

### Issue Encountered
<description of the issue>

**Options:**
1. <option 1>
2. <option 2>
3. Other approach

What would you like to do?
```

**Guardrails**

- Keep going through tasks until done or blocked
- Always read context files before starting (from the apply instructions output or directory fallback)
- If task is ambiguous, pause and ask before implementing
- If implementation reveals issues, pause and suggest artifact updates
- Keep code changes minimal and scoped to each task
- **Validate task changes using the project's native test/build command before checking the task off**
- Update task checkbox immediately after completing and validating each task
- Pause on errors, blockers, or unclear requirements - don't guess
- A task that does not say which file to touch is a documentation defect, not a puzzle to solve. Stop, report it, and propose the concrete wording — do not infer the target and proceed
- Never check off a task whose artifact does not exist on disk. `opsx-handoff --mode apply "<name>"` reports these as `phantom-completion`
- Apply never runs or claims the archive completion gate; recommend verify next
- Use contextFiles from CLI output, don't assume specific file names

**Fluid Workflow Integration**

This skill supports the "actions on a change" model:

- **Can be invoked anytime**: Before all artifacts are done (if tasks exist), after partial implementation, interleaved with other actions
- **Allows artifact updates**: If implementation reveals design issues, suggest updating artifacts - not phase-locked, work fluidly
