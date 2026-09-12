---
name: Audit
description: Perform deep codebase analysis using automated checks and expert review.
category: Workflow
tags: [workflow, audit, review]
---

# Deep Audit Workflow

You are now in **DEEP AUDIT MODE**.

> **Protocol:** Run Checks -> Analyze Evidence -> Recommend Fixes.

## 0. Skill Activation (MANDATORY)

- **ACTIVATE**: `@lint-and-validate` — use this skill for repo-native validation and gate execution.
- **OPTIONAL**: For security-sensitive scope, also activate `@vulnerability-scanner`.
- **READ**: `.agents/runtime/review/review-rubric.md` — use as reference for severity, confidence and blocking thresholds during expert review.

______________________________________________________________________

## 1. Initial Scan (Turbo)

// turbo

1. **Run Audit Suite**

   - Run the repo-native gate suite across all files:
     ```bash
     pre-commit run --all-files
     ```

2. **Analyze Output**

   - Review gate results by status (`passed`, `failed`, `skipped`).
   - Identify:
     - ❌ **Failed**: blocking gates that failed — immediate technical debt.
     - ⏭️ **Skipped**: optional gates or unconfigured hooks.

## 2. Expert Review (Human-in-the-Loop)

1. **Select High-Risk Targets**

   - Based on script output, pick the top 5 risk-heavy files/modules.

2. **Deep Read (`read`)**

   - Review selected files and adjacent dependencies.
   - Look for issues scripts commonly miss:
     - Correctness regressions and edge-case failures.
     - Security risks in input handling and authorization boundaries.
     - Performance hotspots and unnecessary complexity.
     - Maintainability issues (coupling, naming, hidden side effects).

## 3. Targeted Validation

**Reproduce and Verify**

- Reproduce one high-severity issue when feasible.
- Validate expected behavior using targeted tests/commands.

## 4. 📝 Report

**Generate `AUDIT_REPORT.md`**

- Summarize findings with severity and evidence.
- Include concrete remediation actions and validation steps.

### Minimum Report Structure

- Scope and assumptions
- Findings (Severity | File | Evidence | Recommendation)
- Validation commands and outcomes
- Residual risks
- Priority action plan

If no material issues are found, state that explicitly and list
coverage gaps.

______________________________________________________________________

> "Trust the script for stats, trust your judgment for architecture."
