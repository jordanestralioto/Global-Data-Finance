---
name: 'OPSX: Continue'
description: Continue working on an OpenSpec change - create the next artifact in sequence
category: Workflow
tags: [workflow, openspec, continue, artifacts]
---

Continue working on an OpenSpec change by creating the next artifact.

**Input**: Optionally specify a change name after `/opsx:continue` (e.g., `/opsx:continue add-auth`). If omitted, you MUST ask the user to select a change from `opsx list --json`. Never infer or auto-select a change for `continue`.

**Selection policy**: `continue` always requires explicit change selection unless the change name is already present in the request.

**Schema note**: Use `opsx status --change "<name>" --json` and `opsx instructions <artifact-id> --change "<name>" --json` as the source of truth for artifact order. The `spec-driven` sequence is only a common example.

**Decision-source preflight**: Before writing any proposal, spec, design, or
tasks artifact, run `opsx preflight --change "<name>" --json`.
Stop on a nonzero result. You may resolve exact repository paths, existing
function names, and other mechanical facts from the codebase, but you must
return to the confirmed source for missing scope, behavior, contract,
trade-off, acceptance, rollout, or rollback decisions.

## Steps

1. **If no change name provided, prompt for selection**

   Run `opsx list --json` to get available changes ordered
   by tracked creation date and deterministic name tie-breaker. Use an
   enumerated-selection capability when available. If it is unavailable or
   cannot represent every option, print every option in a numbered text list
   and wait for one explicit selection before continuing.

   Present the top 3-4 most recently modified changes as options, showing:

   - Change name
   - Schema (from `schema` field if present, otherwise "spec-driven")
   - Status (e.g., "0/5 tasks", "complete", "no tasks")
   - Tracked creation date (from the `lastModified` field)

   Mark the most recently modified change as "(Recommended)" since it's likely what the user wants to continue.

   **IMPORTANT**: Do NOT guess or auto-select a change. Always let the user choose.

2. **Check current status**

   ```bash
   opsx status --change "<name>" --json
   ```

   *(CLI Fallback: If `opsx` fails, inspect `openspec/changes/<name>/` directly to determine progress)*

   Parse the JSON to understand current state. The response includes:

   - `schemaName`: The workflow schema being used (e.g., "spec-driven")
   - `artifacts`: Array of artifacts with their status ("done", "ready", "blocked")
   - `isComplete`: Boolean indicating if all artifacts are complete

3. **Act based on status**:

   ______________________________________________________________________

   **If all artifacts are complete (`isComplete: true`)**:

   - Congratulate the user
   - Show final status including the schema used
   - Suggest: "All artifacts created! You can now implement this change with `/opsx:apply <name>` after separate authorization. Verify, sync, completion and archive are later phases; do not skip directly to archive."
   - STOP

   ______________________________________________________________________

   **If artifacts are ready to create** (status shows artifacts with `status: "ready"`):

   - Pick the FIRST artifact with `status: "ready"` from the status output
   - Get its instructions:
     ```bash
     opsx instructions <artifact-id> --change "<name>" --json
     ```
   - Parse the JSON. The key fields are:
     - `context`: Project background (constraints for you - do NOT include in output)
     - `rules`: Artifact-specific rules (constraints for you - do NOT include in output)
     - `template`: The structure to use for your output file
     - `instruction`: Schema-specific guidance
     - `outputPath`: Where to write the artifact
     - `dependencies`: Completed artifacts to read for context
   - **Create the artifact file**:
     - Read any completed dependency files for context
     - Use `template` as the structure - fill in its sections
     - Apply `context` and `rules` as constraints when writing - but do NOT copy them into the file
     - If the built-in template is less strict than injected `rules`, preserve
       its parseable skeleton and add everything required by `rules`; the
       injected rules take precedence over minimal examples
     - Write to the output path specified in instructions
   - Validate exactly the artifact just written:
     ```bash
     opsx-handoff --mode artifact --artifact "<artifact-id>" "<name>"
     ```
   - Show what was created and what is now unlocked, then stop. One invocation
     creates exactly one artifact. Use `/opsx:ff` when the requested outcome is
     the complete apply-ready artifact set.

   ______________________________________________________________________

   **If no artifacts are ready (all blocked)**:

   - This shouldn't happen with a valid schema
   - Show status and suggest checking for issues

4. **After creating an artifact, show progress**

   ```bash
   opsx status --change "<name>"
   ```

## Output

After each invocation, show:

- Which artifact was created
- Schema workflow being used
- Current progress (N/M complete)
- What artifacts are now unlocked
- Prompt: "Run `/opsx:continue` to create the next artifact"

## Artifact Creation Guidelines

The artifact types and their purpose depend on the schema. Use the `instruction` field from the instructions output to understand what to create.

Common artifact patterns:

**spec-driven schema** (proposal → specs → design → tasks):

- **proposal.md**: Ask user about the change if not clear. Fill in Why, What Changes, Capabilities, Impact.
  - The Capabilities section is critical - each capability listed will need a spec file.
- **specs/<capability>/spec.md**: Create one spec per capability listed in the proposal's Capabilities section (use the capability name, not the change name).
- **design.md**: Document technical decisions, architecture, and implementation approach.
- **tasks.md**: Break down implementation into checkboxed tasks.

For other schemas, follow the `instruction` field from the CLI output.

### Audience of every artifact you write

The implementer is a junior developer holding the project's root agent
policy file and the docs it links, and nothing else — no prior context on
this codebase, no knowledge of its business domain. They will not push back
on an ambiguous instruction — they will guess. An artifact is done when such
a reader can execute it without asking a single question, not when it is
technically correct for someone who already knows the system.

Because they already read that policy file, do not restate the stack,
commands, pipeline phases, mandatory rules or documentation routes inside a
change artifact. Link instead. The artifact carries what the policy file
does not: this change's problem, its domain vocabulary, its decisions with
rejected alternatives, what not to touch, and anchored steps.

The `context` and `rules` fields returned by `opsx instructions` carry
the project's authoring standard. Treat `rules` as mandatory. Before
reporting an artifact as done, run the repository's handoff gate and fix
what it reports:

```bash
opsx-handoff --mode artifact --artifact "<artifact-id>" "<name>"
```

## Guardrails

- Create exactly one artifact per invocation. Never continue to the next ready
  artifact in the same invocation.
- Do not report an artifact as done while the handoff gate is red.
- Always read dependency artifacts before creating a new one
- Never skip artifacts or create out of order
- If context is unclear, ask the user before creating
- Verify the artifact file exists after writing before marking progress
- Use the schema's artifact sequence, don't assume specific artifact names
- **IMPORTANT**: `context` and `rules` are constraints for YOU, not content for the file
  - Do NOT copy `<context>`, `<rules>`, `<project_context>` blocks into the artifact
  - These guide what you write, but should never appear in the output
