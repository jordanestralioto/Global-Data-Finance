---
name: 'OPSX: New'
description: Start a new OpenSpec change with preflight spec checks and decision envelope
category: Workflow
tags: [workflow, openspec, scaffold]
---

Start a new OpenSpec change using the artifact-driven approach.

**Input**: The argument after `/opsx:new` is the change name (kebab-case), OR a description of what the user wants to build.

**Schema policy**: Use the default schema unless the user explicitly requests a different workflow or schema.

**Decision-source preflight**: A nontrivial change must have a confirmed
`decision_source` envelope before any formal artifact is written. Collect its
type, repository-relative path, SHA-256 digest, confirmation date, owned
decision IDs, and dependencies. A classifier-approved direct route does not
create an OpenSpec change or an empty envelope. Missing or incomplete decision
coverage is a hard stop; only deterministic repository facts may be recorded
without a new decision.

**Stop condition**: Stop after creating the change, showing the current artifact status, and printing the instructions for the first artifact `ready`.

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

   Before scaffolding the new change, inspect existing changes to ensure main specs (`openspec/specs/`) are up to date:

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

   This creates a scaffolded change at `openspec/changes/<name>/` with the
   repository schema. There is no `--schema` flag: this repo has one schema.

   The `opsx new` command validates this envelope atomically while creating the
   manifest. Before reading or writing proposal, specs, design, or tasks, run
   the same explicit preflight again:

   ```bash
   opsx preflight --change "<name>" --json
   ```

   Stop on any nonzero result and report every missing, tampered, uncovered,
   duplicate, or cyclic decision finding. Do not invent a decision to make the
   preflight pass.

   *(CLI Fallback: If `opsx` fails, stop and report that the decision
   envelope cannot be validated; never manually scaffold formal artifacts.)*

5. **Show the artifact status**

   ```bash
   opsx status --change "<name>"
   ```

   This shows which artifacts need to be created and which are ready (dependencies satisfied).

   *(CLI Fallback: If `opsx` fails, simply list the empty files that need to be filled in order)*

6. **Get instructions for the first artifact**
   The first artifact depends on the schema. Check the status output to find the first artifact with status "ready".

   ```bash
   opsx instructions <first-artifact-id> --change "<name>"
   ```

   This outputs the template and context for creating the first artifact.

   *(CLI Fallback: If `opsx` fails, use standard markdown structure for the first artifact, e.g., a simple proposal outline)*

7. **STOP and wait for user direction**

## Output

After completing the steps, summarize:

- Change name and location
- Schema/workflow being used and its artifact sequence
- Current status (0/N artifacts complete)
- The template for the first artifact
- Prompt: "Ready to create the first artifact? Run `/opsx:continue` or just describe what this change is about and I'll draft it."

## Guardrails

- Do NOT create any artifacts yet - just show the instructions
- Do NOT advance beyond showing the first artifact template
- If the name is invalid (not kebab-case), ask for a valid name
- If a change with that name already exists, suggest using `/opsx:continue` instead
