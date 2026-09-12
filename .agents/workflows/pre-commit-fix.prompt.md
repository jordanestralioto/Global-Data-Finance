---
name: Pre-commit Fix
description: Systematically triage, fix, and verify pre-commit gate errors using Developer Engineer without introducing regressions or hacking bypasses
category: Workflow
tags: [workflow, quality, pre-commit, fix, lint]
---

# 🛠️ Pre-commit Fix Workflow (`/pre-commit-fix`)

Activate the **Developer Engineer** agent (`developer-engineer`) to systematically diagnose and fix all pre-commit gate failures across the repository.

> **Execution Mindset:** Surgical fixes, no bypasses, adhere to root policies in `AGENTS.md`, and never edit generated mirrors directly.

______________________________________________________________________

## Instructions

### 1. Run the Pre-commit Suite

Execute the project's native pre-commit runner across all files:

```bash
uv run pre-commit run --all-files
```

*(Fallback if `uv` is not used: `pre-commit run --all-files`)*

______________________________________________________________________

### 2. Systematic Triage & Fix Order

Resolve failures in logical dependency order:

1. **Auto-formatting & File Cleanup** (`ruff-format`, `trim trailing whitespace`, `fix end of files`):
   - Hooks that automatically modify files will exit with failure on their first run. Let them format and check if a simple re-run resolves them.
2. **Synchronization & Generated Mirrors** (`harness-sync`, `*-mirror-sync`, `skill-index-sync`):
   - **CRITICAL:** NEVER edit generated mirror files directly (e.g., in `.claude/`, `.github/`, `.opencode/`, `.agents/`).
   - Fix the source in the designated component directories and run the sync command (e.g., `harness-sync`).
3. **Linting & Code Quality** (`ruff check`, `bandit`, `flake8`):
   - Fix genuine lint and security issues.
   - **NO HACKS:** Do not bypass checks with `# noqa`, `// @ts-ignore`, `eslint-disable`, or `type: ignore` unless strictly necessary and architecturally justified.
4. **Type Checking** (`mypy`, `pyright`, `tsc`):
   - Fix underlying type discrepancies with proper annotations, guards, and type-safe narrowings.
   - Do not weaken types to `Any` / `unknown` merely to satisfy the checker.
5. **Domain & Protocol Validators** (domain validation, contract checks, protocol validators):
   - Follow the exact specification schemas and structural rules defined by the project.
6. **Test Regressions** (`pytest`, test suites):
   - Fix broken tests by addressing root causes, not by deleting or tautologically neutering assertions.

______________________________________________________________________

### 3. Guardrails

- **Surgical Scope:** Keep changes minimal and focused strictly on the reported errors. Do not perform unrequested mass refactoring.
- **Contract Preservation:** Never alter public function signatures, API contracts, or breaking behavior to silence a linter.
- **Repository Standards:** Strictly respect formatting, single responsibility, and architectural rules in `AGENTS.md`.

______________________________________________________________________

### 4. Verification Loop

1. Re-run `uv run pre-commit run --all-files`.
2. Repeat fixes until **100% of hooks pass with exit code 0**.

______________________________________________________________________

### 5. Summary

Provide a concise summary:

- Summary of failed gates resolved.
- Files modified (and source-to-mirror sync commands executed, if applicable).
- Confirmation of a 100% clean pre-commit run.
