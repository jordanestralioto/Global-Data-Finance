---
name: 'OPSX: Verify'
description: Verify implementation matches change artifacts before archiving
category: Workflow
tags: [workflow, openspec, verify, audit]
---

Verify that an implementation matches the change artifacts (specs, tasks, design).

**Input**: Optionally specify a change name after `/opsx:verify` (e.g., `/opsx:verify add-auth`). If omitted, you MUST ask the user to select a change from the active changes. Never infer or auto-select a change for `verify`.

**Selection policy**: `verify` always requires explicit change selection unless the change name is already present in the request.

**Schema note**: Use `opsx status --change "<name>" --json` and the available context files as the source of truth. Verification must compare implementation with artifacts, not only with task checkboxes.

**Semantic evidence contract**: Verification MUST persist
`openspec/changes/<name>/evidence/verification-report.json` conforming to
the verification report schema (`verification-report-v1`).
The report is bound to `decision_source.sha256` and to the repository
fingerprint returned by `opsx fingerprint --change "<name>" --json`; the report and gate report are excluded from that
fingerprint. Unresolved in-contract divergence is a blocker, not a warning.

## Steps

1. **If no change name provided, prompt for selection**

   Run `opsx list --json` to get available changes. Use an enumerated-selection capability when available. If it is unavailable or cannot represent every option, print every option in a numbered text list and wait for one explicit selection before continuing.

   Show changes that have implementation tasks (tasks artifact exists).
   Include the schema used for each change if available.
   Mark changes with incomplete tasks as "(In Progress)".

   **IMPORTANT**: Do NOT guess or auto-select a change. Always let the user choose.

2. **Check status to understand the schema**

   ```bash
   opsx status --change "<name>" --json
   ```

   Parse the JSON to understand:

   - `schemaName`: The workflow being used (e.g., "spec-driven")
   - Which artifacts exist for this change

3. **Get the change directory and load artifacts**

   ```bash
   opsx instructions apply --change "<name>" --json
   ```

   This returns the change directory and context files. Read all available artifacts from `contextFiles`.

4. **Bind the verification state**

   Run the bundle gate and capture the exact repository fingerprint before the
   semantic review:

   ```bash
   opsx-handoff --mode bundle "<name>"
   opsx fingerprint --change "<name>" --json
   ```

   The bundle gate is used here on purpose. The completion gate requires
   `evidence/verification-report.json`, which this workflow only writes in step
   9, so running completion first would deadlock every change that has never
   been verified.

   A red bundle gate, open task, phantom completion, missing provenance,
   missing synchronization, or stale gate evidence is a blocker. Copy the
   returned `repositoryFingerprint` object into the semantic report. Every
   changed path except the two report files remains bound to that fingerprint.

5. **Map the complete contract**

   Execute the standard project test suite, static analysis, and build checks
   with the repository's native commands. Read every requirement and every
   categorized scenario in the delta specs, plus every `### Dn:` decision in
   `design.md`. Record concrete implementation and test evidence for each.
   Missing evidence, mandatory-scenario gaps, or a design contradiction is a
   blocker, never a warning.

   Improvements explicitly outside the change's Non-Goals may be warnings
   only when their `classification` is exactly `out-of-contract`.

6. **Verify Completeness**

   **Deterministic completion gate** (run this before the manual review):

   ```bash
   opsx-handoff --mode completion "<name>"
   ```

   On this pass `semantic-report-missing` is the expected state for a change
   that was never verified, because step 9 writes that report. It is the only
   finding you may carry forward here; every other finding is a blocker. Step 9
   re-runs this same gate and requires it fully green.

   This repeats the full bundle gate and reports, without judgment calls: tasks still open, tasks checked off
   while citing a repository path that does not exist
   (`phantom-completion`), requirements or scenarios without resolved task
   traceability, and missing, red, or stale structured evidence at
   `evidence/gate-report.json`.

   - Add a CRITICAL issue for every `phantom-completion` finding. A task
     marked done whose file was never created is unfinished work, not a
     style divergence.
   - Add a CRITICAL issue for every `requirement-untraced` finding.
   - Add a CRITICAL issue when structured validation evidence is missing,
     red, malformed, or bound to a different repository state.
   - The gate covers what a machine can check. It does not replace the
     correctness and coherence review below.

   **Task Completion**:

   - If tasks.md exists in contextFiles, read it
   - Parse checkboxes: `- [ ]` (incomplete) vs `- [x]` (complete)
   - Count complete vs total tasks
   - If incomplete tasks exist:
     - Add CRITICAL issue for each incomplete task
     - Recommendation: "Complete task: <description>" or "Mark as done if already implemented"

   **Spec Coverage**:

   - If delta specs exist in `openspec/changes/<name>/specs/`:
     - Extract all requirements (marked with "### Requirement:")
     - For each requirement:
       - Search codebase for keywords related to the requirement
       - Assess if implementation likely exists
     - If requirements appear unimplemented:
       - Add CRITICAL issue: "Requirement not found: <requirement name>"
       - Recommendation: "Implement requirement X: <description>"

7. **Verify Correctness**

   **Requirement Implementation Mapping**:

   - For each requirement from delta specs:
     - Search codebase for implementation evidence
     - If found, note file paths and line ranges
     - Assess if implementation matches requirement intent
     - If divergence detected:
       - Add a blocker: "Implementation diverges from spec: <details>"
       - Recommendation: "Review <file>:<lines> against requirement X"

   **Scenario Coverage**:

   - For each scenario in delta specs (marked with "#### Scenario:"):
     - Check if conditions are handled in code
     - Check if tests exist covering the scenario
     - If scenario appears uncovered:
       - Add a blocker: "Scenario not covered: <scenario name>"
       - Recommendation: "Add test or implementation for scenario: <description>"

8. **Verify Coherence**

   **Design Adherence**:

   - If design.md exists in contextFiles:
     - Extract key decisions (look for sections like "Decision:", "Approach:", "Architecture:")
     - Verify implementation follows those decisions
     - If contradiction detected:
       - Add a blocker: "Design decision not followed: <decision>"
       - Recommendation: "Update implementation or revise design.md to match reality"
   - If no design.md: Skip design adherence check, note "No design.md to verify against"

   **Code Pattern Consistency**:

   - Review new code for consistency with project patterns
   - Check file naming, directory structure, coding style
   - If significant deviations found:
     - Add SUGGESTION: "Code pattern deviation: <details>"
     - Recommendation: "Consider following project pattern: <example>"

9. **Write the structured verification report**

   Persist exactly this JSON artifact at
   `openspec/changes/<name>/evidence/verification-report.json`, conforming to
   the verification report schema (`verification-report-v1`):

   ```json
   {
     "schemaVersion": "1.0.0",
     "artifactType": "verification-report",
     "changeName": "<name>",
     "sourceDigest": "<decision_source.sha256>",
     "repositoryFingerprint": {"algorithm": "sha256", "value": "...", "head": "...", "changedFiles": []},
     "requirements": [{"requirement": "<exact heading>", "status": "covered", "implementationEvidence": ["src/file.py:10"], "testEvidence": ["tests/unit/test_file.py:20"]}],
     "scenarios": [{"scenario": "[happy] <exact title>", "status": "covered", "implementationEvidence": ["src/file.py:10"], "testEvidence": ["tests/unit/test_file.py:20"]}],
     "designDecisions": [{"decision": "D1: <exact title>", "status": "followed", "implementationEvidence": ["src/file.py:10"], "testEvidence": ["tests/unit/test_file.py:20"]}],
     "blockers": [],
     "warnings": [],
     "verdict": "passed"
   }
   ```

   Map every requirement, scenario, and design decision. Use
   `"verdict": "blocked"` and list every unresolved contract divergence when
   any blocker exists. A report with blockers MUST NOT say ready for archive.

   **Issues by Priority**:

   1. **CRITICAL** (Must fix before archive):

      - Incomplete tasks
      - Missing requirement implementations
      - Each with specific, actionable recommendation

   2. **WARNING** (Only out of contract):

      - Improvements explicitly excluded by Non-Goals
      - Every warning must set `classification` to `out-of-contract`

   3. **SUGGESTION** (Nice to fix):

      - Pattern inconsistencies
      - Minor improvements
      - Each with specific recommendation

   **Final Assessment**:

   - If any blocker exists: set `verdict` to `blocked` and stop.
   - If no blocker exists: set `verdict` to `passed` only after re-running the
     fingerprint and completion gate. With the report now on disk,
     `opsx-handoff --mode completion "<name>"` MUST be fully green; a remaining
     `semantic-report-missing` means the report was never persisted.

## Verification Heuristics

- **Completeness**: Focus on objective checklist items (checkboxes, requirements list)
- **Correctness**: Use concrete implementation and test evidence; uncertainty about in-contract behavior is a blocker
- **Coherence**: Look for glaring inconsistencies, don't nitpick style
- **False Positives**: Classify only explicitly out-of-contract improvements as warnings; do not downgrade contract divergence
- **Actionability**: Every issue must have a specific recommendation with file/line references where applicable

## Graceful Degradation

- If the structured report cannot be produced, stop with a blocker and do not
  report archive readiness.
- If an artifact is missing, record the missing mapping and stop.
- Always record skipped checks in the report; never silently downgrade them.

## Output Format

Use Markdown only as a human summary after writing the JSON report. Include
the exact report path, mapping counts, blocker count, warning count, and
terminal verdict; conversational prose never replaces the JSON artifact.
