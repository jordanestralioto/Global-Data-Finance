# AI Coding Agent Anti-Patterns and Diff Sanity Guide

> Summary: Comprehensive reference of common mistakes, shortcuts, and erosion patterns introduced by AI coding agents during refactoring or feature implementation, and how to intercept them locally.

The scanner rules below describe an optional strict profile. Select it only
when the project's policy accepts its bans and Python runtime requirement;
the portable workflow does not impose these rules on every stack.

## 1. Catalog of AI Coding Agent Traps

### 1.1 Leftover Debug and Inspection Artifacts

AI agents frequently insert statements to inspect runtime states and forget to remove them:

- **Python**: `breakpoint()`, `import pdb; pdb.set_trace()`, raw `print()` statements in library/core code.
- **JavaScript/TypeScript**: `debugger;`, `console.log(`, `console.dir(`.
- **Rust**: `dbg!(...)`, `println!(...)` in production crates.
- **Go**: `fmt.Println` in internal services without logger.

### 1.2 Unfulfilled Stubs and Placeholders

When generating broad scaffolds or completing functions hurriedly, agents may leave placeholder implementations:

- `raise NotImplementedError("TODO")`
- `throw new Error("TODO: implement")`
- `pass  # TODO` as sole body of new public functions.
- `return null; // FIXME`

### 1.3 Erosion of Type Safety and Lint Disables

To pass validation gates without fixing underlying contract issues, agents often silence compilers:

- `@ts-ignore`, `@ts-nocheck` or `@ts-expect-error` in executable TypeScript or configuration.
- `# type: ignore` or `# noqa` in executable Python or configuration. The diff
  gate rejects these markers, including rule-specific forms and lines with a
  reason. A `.md`, `.markdown`, `.rst` or `.txt` file may quote them as
  explanatory documentation, including inside a fenced code block; that
  exception does not apply to any executable or configuration format.
- `as any` casting without explanation.
- `// eslint-disable-next-line` without a stated reason.

### 1.4 Test Integrity Violations

When a test fails following an implementation change, agents sometimes weaken or skip the test instead of fixing the implementation:

- Inserting `.only` (e.g. `it.only(`, `describe.only(`) to run only one test and bypass failures elsewhere.
- Adding `@pytest.mark.skip`, `@pytest.mark.xfail`, `it.skip()`, `xit()`.
- Removing assertions (`assert`, `expect(...)`) or replacing specific assertions with tautologies (`expect(true).toBe(true)`).

### 1.5 Unsynchronized Dependency Changes

- Adding a dependency to `package.json` or `pyproject.toml` without running the package manager lock command.
- Committing phantom packages not reflected in lockfiles.

### 1.6 Operational bypasses in every textual diff

The operational scan is independent of the code classifier and applies to
every textual file, including documentation, OpenSpec Markdown, generated
projections, scripts and configuration. It blocks download-to-shell
pipelines, hook-disabling command flags, hook-skip environment assignments,
CI settings that continue after an error, and shell fallbacks that force a
successful exit. A documentation citation never authorizes one of these
operations.

### 1.7 Control-Flow and Structural Complexity

Structural erosion is visible when a routine becomes progressively harder to
reason about even though each branch is locally valid:

- Arrow-shaped code created by nested conditions, loops, and error handlers.
- Cyclomatic or cognitive complexity that exceeds the project's configured
  limit. Record these as separate metrics; neither is a substitute for the
  other.
- Redundant `else` branches after a terminal statement.
- Missing guard clauses when an invalid precondition or edge case can be
  rejected before the main path.

Do not impose a single-exit rule. Multiple returns are acceptable when they
make preconditions and the main path clearer. Treat scattered exits as a
problem only when they obscure cleanup, effects, or invariants.

These findings require a parser-aware linter or analyzer. Do not add regexes
for nesting or complexity to `check_diff_sanity.py`.

### 1.8 Error Handling and Exception Masking

Error handling becomes deceptive when it prevents a visible failure without
preserving enough information to diagnose or recover from it:

- A root or universal error type is caught inside ordinary business logic.
- An empty handler, neutral fallback, or generic return silently swallows the
  failure.
- One broad handler wraps unrelated operations, hiding which operation failed.
- A replacement error discards the original cause or stack information.

A broad catch can be valid at an explicit process, request, worker, CLI, or
integration boundary. Keep that scope narrow, perform a defined action, and
preserve the original cause using the language's native mechanism. An
intentional ignore must be explicit and narrowly justified; an empty handler
is not sufficient evidence.

### 1.9 Monolithic Functions and Scope Bloat

Flag routines that accumulate unrelated responsibilities, exceed the
configured statement limit, or mix orchestration, validation, persistence,
and presentation. Count executable statements when the analyzer supports
them; physical line count is a separate repository policy and must not be
reported as the same metric.

More than five positional parameters is a review signal for coupling or
control flags, not a universal failure. Prefer decomposition or a cohesive
input object only when it clarifies a real responsibility boundary.

### 1.10 Assertion Vacuum and Hollow Verification

Tests are hollow when they execute code without proving an observable result,
or when a specific assertion is replaced by a tautology, broad truthiness
check, or assertion that only repeats the mock setup.

`check_test_integrity.py` detects focused tests, unjustified skips, deleted
tests, and net assertion loss. It cannot prove test meaning across every test
framework. Keep assertion design under `[TEST_INTEGRITY]` and use the
`testing-patterns` skill for non-tautological behavior checks; do not claim
that `[LINTER]` or a generic regex can detect every hollow test.

### 1.11 Dead Code and Obsolete Compatibility Paths

Unused imports, definitions, files, and exports require capability-specific
analysis. Review test-only references, aliases, wrappers, and compatibility
branches against their consumers and accepted contracts. A referenced alias
can still be obsolete. Follow [dead-code-policy.md](dead-code-policy.md) for
snapshots, ambiguous findings, specific exceptions, and read-only enforcement;
do not extend the diff-text scanner into a pretend reachability analyzer.

## 2. Detection Strategy in Diff

Diff-oriented gates must analyze lines starting with `+` in
`git diff --cached`. Structural gates must run the project's parser-aware
linter or analyzer against changed or affected code instead:

1. **New violations must trigger `FAIL`**: A newly introduced `console.log` on a staged line is a hard block.
2. **Intentional exceptions require the narrowest safe scope**:
   - If a third-party type boundary needs explanation, describe it in the
     surrounding documentation or fix the contract at the source; do not add a
     type-check suppression to executable code.
   - `# noqa`, `# noqa: <rule>`, type-ignore markers, and TypeScript suppression
     markers are violations in executable/configuration formats regardless of
     the reason attached. Documentation may quote them only as non-executable
     examples.
