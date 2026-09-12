---
name: 'OPSX: Fast Forward'
description: Fast-forward artifact creation - generate all artifacts needed for implementation in one go
category: Workflow
tags: [workflow, openspec, fast-forward, artifacts]
---

Fast-forward through artifact creation - generate everything needed to start implementation.

**Input**: The argument after `/opsx:ff` is the change name (kebab-case), OR a description of what the user wants to build.

**Schema policy**: Use the default schema unless the user explicitly requests a different workflow or schema.

**Decision-gap stop rule**: Fast-forward never fills a missing decision with a
reasonable assumption. Before creating any formal artifact, require a valid
decision-source envelope and run `opsx preflight --change "<name>" --json`. If scope, behavior, contract, acceptance, rollout, or
rollback is absent from the owned source IDs, stop and report the affected IDs.
Only deterministic mechanical facts may be resolved from the repository.

**Stop condition**: Stop when every artifact required by `apply.requires` is `done`.

## Steps

1. **If no input provided, ask what they want to build**

   Use an open-text input capability when available (without preset options).
   If that capability is unavailable, ask the same question in plain numbered
   text and wait for the user's answer before continuing. Ask:

   > "What change do you want to work on? Describe what you want to build or fix."

   From their description, derive a kebab-case name (e.g., "add user authentication" → `add-user-auth`).

   **IMPORTANT**: Do NOT proceed without understanding what the user wants to build.

2. **Determine the workflow schema**

   This repository uses the standard workflow schema `spec-driven`. There is
   nothing to choose: if the user asks for a different workflow, say that adding
   one requires an explicit custom schema, and confirm before doing it.

3. **Preflight Spec Consistency Check**

   Before creating the change directory and generating artifacts, inspect existing changes to ensure main specs (`openspec/specs/`) are up to date:

   a. Run `opsx list --json` (or inspect active changes under `openspec/changes/`).
   b. Identify active changes containing delta specs at `specs/<capability>/spec.md`.
   c. **Check for un-synced completed changes**: If any active change has all tasks completed (`- [x]`) or status `all_done`, but its delta specs have not been merged into `openspec/specs/`:

   - Display warning `[WARNING]`: *"Change `<name>` appears completed but its delta specs are not synced to main specs (`openspec/specs/`). Recommended: run `/opsx:sync <name>` and `/opsx:archive <name>` before designing the new change."*
   - Ask the user for confirmation using a structured confirmation capability
     when available. Otherwise present numbered text choices for syncing
     first or proceeding anyway, and wait for the user's answer.
     d. **Check for active concurrent changes**: If active changes modify related specs, display an informational note `[INFO]`: *"Active changes with delta specs in progress: `<list>`. Be aware of potential spec overlap."*

4. **Create the change directory**

   ```bash
   opsx new change "<name>" \
     --decision-source-type "<sabatina|user-contract>" \
     --decision-source-path "<repository-relative-source>" \
     --decision-source-sha256 "<sha256>" \
     --confirmed-on "<YYYY-MM-DD>" \
     --decision-id "<Q-id>"
   ```

   There is no `--schema` flag: this repository has a single schema.
   This creates a scaffolded change at `openspec/changes/<name>/`.

   The `opsx new` command validates the envelope atomically while creating the
   manifest. Run the decision-source preflight immediately again. A nonzero
   result is a hard stop before proposal, specs, design, or tasks are written:

   ```bash
   opsx preflight --change "<name>" --json
   ```

5. **Get the artifact build order**

   ```bash
   opsx status --change "<name>" --json
   ```

   Parse the JSON to get:

   - `applyRequires`: array of artifact IDs needed before implementation (e.g., `["tasks"]`)
   - `artifacts`: list of all artifacts with their status and dependencies

6. **Create artifacts in sequence until apply-ready**

   Use a progress-tracking capability when available. Otherwise maintain the
   same artifact checklist in ordinary progress messages and record each
   transition before continuing.

   Loop through artifacts in dependency order (artifacts with no pending dependencies first):

   a. **For each artifact that is `ready` (dependencies satisfied)**:

   - Get instructions:
     ```bash
     opsx instructions <artifact-id> --change "<name>" --json
     ```
   - The instructions JSON includes:
     - `context`: Project background (constraints for you - do NOT include in output)
     - `rules`: Artifact-specific rules (constraints for you - do NOT include in output)
     - `template`: The structure to use for your output file
     - `instruction`: Schema-specific guidance for this artifact type
     - `outputPath`: Where to write the artifact
     - `dependencies`: Completed artifacts to read for context
   - Read any completed dependency files for context
   - Create the artifact file using `template` as the structure
   - Apply `context` and `rules` as constraints - but do NOT copy them into the file
   - Show brief progress: "✓ Created <artifact-id>"

   b. **Continue until all `applyRequires` artifacts are complete**

   - After creating each artifact, re-run `opsx status --change "<name>" --json`
   - Check if every artifact ID in `applyRequires` has `status: "done"` in the artifacts array
   - Stop when all `applyRequires` artifacts are done

   c. **If an artifact requires user input** (unclear context):

   - Use an open-text input capability when available to clarify. Otherwise ask
     the clarification in plain numbered text and wait for the answer.
   - Then continue with creation

7. **Show final status**

   ```bash
   opsx status --change "<name>"
   ```

## Output

After completing all artifacts, summarize:

- Change name and location
- List of artifacts created with brief descriptions
- What's ready: "All artifacts created! Ready for implementation."
- Prompt: "Run `/opsx:apply` to start implementing."

### Audience of every artifact you write

The implementer is a junior developer holding the project's root agent
policy file and the docs it links, and nothing else — no prior context on
this codebase, no knowledge of its business domain. They will not push back
on an ambiguous instruction — they will guess. An artifact is done when such
a reader can execute it without asking a single question, not when it is
technically correct for someone who already knows the system.

Because they already read that policy file, do not restate the stack,
commands, pipeline phases, mandatory rules or documentation routes inside a
change artifact. Link instead.

Fast-forward makes this failure mode worse, because nobody reviews the
intermediate artifacts. Before declaring the change apply-ready, run:

```bash
opsx-handoff --mode bundle "<name>"
```

Fix every finding. An apply-ready change with a red handoff gate is not
apply-ready.

## Artifact Creation Guidelines

- Follow the `instruction` field from `opsx instructions` for each artifact type
- Treat the `context` and `rules` fields as mandatory constraints, not style hints
- If the built-in template omits stricter structure required by injected
  `rules`, preserve the parseable skeleton and add the required structure;
  injected rules take precedence over minimal examples
- The schema defines what each artifact should contain - follow it
- Read dependency artifacts for context before creating new ones
- Use the `template` as a starting point, filling in based on context

## Guardrails

- Create ALL artifacts needed for implementation (as defined by schema's `apply.requires`)
- Always read dependency artifacts before creating a new one
- If context is critically unclear or a decision is absent, stop and report the decision gap; never make a reasonable assumption to keep momentum
- If a change with that name already exists, ask if user wants to continue it or create a new one
- Verify each artifact file exists after writing before proceeding to next
