# Conceptual Gate Catalog and Tool Mapping

> Summary: Map candidate quality gates to project-native tools. Select slots
> from the project's contract, then record their stage, snapshot and coverage.

## 1. Quality Gate Slot Matrix

| Slot                          | Purpose                                                                                       | Python                                                               | JS / TS                                                                       | Go / Rust                                                                                              |
| :---------------------------- | :-------------------------------------------------------------------------------------------- | :------------------------------------------------------------------- | :---------------------------------------------------------------------------- | :----------------------------------------------------------------------------------------------------- |
| **`[HYGIENE]`**               | Whitespace, EOF, merge markers, large files                                                   | `pre-commit-hooks`                                                   | `pre-commit-hooks` / `lint-staged`                                            | `git diff --check`                                                                                     |
| **`[FILE_LINES]`**            | Line caps for eligible tracked production, test, and documentation files                      | `tools/check-max-lines` when selected                                | `tools/check-max-lines` when selected                                         | `tools/check-max-lines` when selected                                                                  |
| **`[SYNTAX]`**                | Fast parse/compilation check                                                                  | `python -m py_compile`                                               | `tsc --noEmit`                                                                | `go vet` / `cargo check`                                                                               |
| **`[FORMATTER]`**             | Deterministic code formatting (auto-fix)                                                      | `ruff format`                                                        | `prettier --write` / `biome format`                                           | `gofmt -w` / `cargo fmt`                                                                               |
| **`[LINTER]`**                | Code quality plus structural complexity, nesting, flow, error handling, and routine scope     | `ruff check` or configured equivalent                                | `eslint` / `biome lint` or configured equivalent                              | `golangci-lint` / `cargo clippy` or configured equivalent                                              |
| **`[TYPE_CHECK]`**            | Static typing validation                                                                      | `mypy` / `pyright`                                                   | `tsc --noEmit`                                                                | Built-in                                                                                               |
| **`[CIRCULAR_DEPENDENCIES]`** | Detect import cycles when the project requires an acyclic graph; identify historical findings | `import-linter` / `pycycle`                                          | `madge --circular` / `dependency-cruiser`                                     | Go compiler / configured architecture check                                                            |
| **`[SECRETS]`**               | Prevent committing credentials/keys                                                           | Official Gitleaks hook / `gitleaks git --pre-commit --staged`        | Official Gitleaks hook / `gitleaks git --pre-commit --staged`                 | Official Gitleaks hook / `gitleaks git --pre-commit --staged`                                          |
| **`[DIFF_SANITY]`**           | Detect debuggers, stubs, unverified bypasses                                                  | `check_diff_sanity.py`                                               | `check_diff_sanity.py`                                                        | `check_diff_sanity.py`                                                                                 |
| **`[LOCKFILE]`**              | Deterministic manifest/lockfile validation; never automatic dependency updates                | `uv lock --check` / `poetry check --lock` / `check_lockfile_sync.py` | `check_lockfile_sync.py` plus a project-native immutable check when available | `cargo check --locked` / `check_lockfile_sync.py`; Go may configure `go mod tidy -diff` when supported |
| **`[TEST_INTEGRITY]`**        | Prevent test deletions, focused tests, skips, assertion loss, and hollow verification         | `check_test_integrity.py` plus native test lint                      | `check_test_integrity.py` plus native test lint                               | `check_test_integrity.py` plus native test lint                                                        |
| **`[TESTS_FAST]`**            | Run a bounded fast suite with declared coverage                                               | Project's fast pytest tier                                           | Project's fast test script                                                    | Project's fast package tests                                                                           |
| **`[TESTS_FULL]`**            | Run the complete practical local suite for the push snapshot                                  | Project's full pytest tier                                           | Project's full test script                                                    | Project's full package tests                                                                           |
| **`[DEPENDENCY_AUDIT]`**      | Scan resolved dependencies for known advisories without updating them                         | Project's pinned read-only scanner                                   | Project's pinned read-only scanner                                            | Project's pinned read-only scanner                                                                     |

## 2. Structural `[LINTER]` Profile

When the project selects a strict structural profile, classify each dimension.
The numbers below are candidate limits, not universal defaults. Apply agreed
limits to new or changed routines; historical findings need an identity-based
baseline that cannot authorize a new finding.

| Dimension             | Candidate blocking limit                                            | Review signal                              | Interpretation                                                                                              |
| :-------------------- | :------------------------------------------------------------------ | :----------------------------------------- | :---------------------------------------------------------------------------------------------------------- |
| Cyclomatic complexity | Maximum `15`                                                        | Greater than `10`                          | Record as cyclomatic complexity, not as a literal count of runtime paths.                                   |
| Cognitive complexity  | Maximum `15` when supported                                         | Greater than `10`                          | Keep separate from cyclomatic complexity; do not silently substitute one metric for the other.              |
| Nesting depth         | Maximum `4`                                                         | Greater than `3`                           | Use the analyzer's syntactic nesting semantics for conditions, loops, and handlers.                         |
| Flow simplification   | Reject redundant branches after terminal statements when supported  | Review avoidable nesting                   | Prefer guard clauses when they clarify the main path; never enforce a blanket single-exit rule.             |
| Error handling        | Reject empty or silent handlers and broad catches in ordinary logic | Review handler scope and preserved context | A boundary catch is valid only when narrow, actionable, and cause-preserving.                               |
| Routine scope         | Maximum `50` executable statements                                  | Greater than `30`                          | Lines are not statements. More than five positional parameters is a review signal, not a universal failure. |

Classify every dimension in the gap analysis:

- `ENABLED`: a native deterministic rule is configured with metric, threshold,
  and scope.
- `DELEGATED`: another existing gate proves the same property deterministically.
- `MANUAL`: no adequate automatic rule exists and an explicit review control
  remains.
- `UNSUPPORTED`: the stack cannot provide the requested deterministic check.

Only `ENABLED` and `DELEGATED` satisfy a complete blocking profile. When the
user requested blocking enforcement, `UNSUPPORTED` leaves that gate incomplete;
do not add an unrequested dependency or claim a false `PASS`. `MANUAL` must be
reported as partial coverage with residual risk.

Structural checks require parser-aware analysis. `check_diff_sanity.py` remains
a staged-text gate and must not be extended with regexes that pretend to count
nesting, statements, or complexity.

Assertion vacuum and tautological assertions belong to `[TEST_INTEGRITY]`.
Use native test lint when available and otherwise require review through the
`testing-patterns` skill. `check_test_integrity.py` does not prove assertion
meaning across every framework.

## 3. Configuration & Structured Data Validations

- **YAML**: `check-yaml` or `yamllint`
- **JSON**: `check-json` or `jq . <file>`
- **TOML**: `check-toml` or `taplo check`
- **Docker**: `hadolint`
- **Shell**: `shellcheck`, `bash -n`

## 4. Test and Dependency Audit Placement

1. Select `[TESTS_FAST]` for pre-commit only after measuring its cost. Name the
   fast tier or affected package selection and its coverage boundary. A changed
   file selector must account for shared modules and configuration changes;
   otherwise broaden the fast tier or report partial coverage. Test-integrity
   scanning does not execute tests.
2. Select `[TESTS_FULL]` for pre-push when the local suite is practical. Run
   the full selected tier, including slower tests the project assigns locally,
   even when no test file changed. If cost or infrastructure requires CI,
   mark that coverage `DELEGATED`; a fast or affected subset is not full-suite
   evidence. Identify the pushed commit/ref snapshot or label a working-tree
   run honestly when those contents differ.
3. Keep `[DEPENDENCY_AUDIT]` separate from lockfile coherence and update jobs.
   Use a pinned, read-only scanner against the resolved graph: prefer the
   authoritative lockfile when supported, or verify that an audited installed
   environment matches it. Record transitive and development dependency scope,
   advisory source, severity policy and justified, reviewed exceptions.
4. Place the audit in pre-push when its measured cost and network needs fit;
   otherwise delegate it to a protected remote gate. Record a vulnerability as
   a failure under the project policy. A missing scanner, stale data or service
   outage is not a clean audit; an advisory outcome requires an explicit
   repository contract and visible evidence. Never invoke `fix`, `update`,
   `upgrade` or an installer from the audit hook. Rerun the audit after a
   deliberate dependency update. If requested blocking coverage has no suitable
   scanner, report `UNSUPPORTED`; do not import this repository's audit wrapper
   or require another language runtime in a consumer.

## 5. Tool Selection Rules

1. **Prefer project-native tools**: If the repository configures a tool via `pyproject.toml` or `package.json`, execute it via the project's package manager (`uv run`, `pnpm exec`).
2. **Use the published line gate when its policy fits**: In a consumer of the
   installed harness, add
   `"check-max-lines"` to `components.tools` in `.agents/harness.json`, then
   run `harness-sync`. The catalog component is `tools/check-max-lines`.
   Invoke `python .agents/scripts/check-max-lines.py` with Python 3.13+.
   It checks eligible Git-tracked working-tree files with fixed caps of 400
   production, 1000 test, and 500 documentation lines. Confirm that its file
   classification and hard-coded exclusions fit the project: those exclusions
   take precedence over `.max-lines.toml` rules. That policy classifies extra
   paths; `.max-lines-baseline.json` caps existing debt without allowing growth.
   A normal run is read-only and returns 0 for pass, 1 for violations, or 2 for
   discovery/policy errors. The CLI checks the whole repository even when the
   hook passes no filenames. A pre-commit runner may isolate unstaged changes;
   verify this before calling its result staged coverage. Do not substitute
   `check-added-large-files` or routine-statement rules for this gate.
3. **Circular dependency requirement**: When the project requires an acyclic
   graph, configure `[CIRCULAR_DEPENDENCIES]` with its compiler or graph checker.
   If no deterministic command exists, report `UNSUPPORTED` and do not claim
   that requested blocking coverage is installed.
4. **Measure, do not impose a universal speed budget**: Choose each hook's scope
   and stage from the repository's actual cost and workflow. Keep a check in
   pre-commit when its safety value justifies the observed latency; move it to
   pre-push or CI when it harms the workflow or encourages `--no-verify`.
5. **Separate dependency lifecycle operations**: `[LOCKFILE]` may validate
   existing state only. Environment synchronization and dependency updates
   belong to explicit setup or reviewed maintenance changes, not to a default
   pre-commit hook. Commands such as `uv sync --locked`, `npm ci`, `pnpm install`, `cargo update`, and `poetry update` must not be inferred as hooks.
6. **Fallback without invention**: If a stack has no deterministic native
   lockfile check, require staged manifest/lockfile parity through
   `check_lockfile_sync.py` and document the limitation. Do not replace the
   missing check with a mutating install, resolver, updater, or sync command.
   Treat `go mod verify` as module-cache integrity auditing, not as a
   substitute for manifest/lockfile coherence.
7. **Structural coverage must be explicit**: For a selected structural profile,
   inspect each dimension and record its metric, threshold, scope, and status.
   Tool names and limits here are examples, not mandatory dependencies.
8. **Bound structural fixes**: Prefer read-only diagnostics. If the project's
   explicit contract permits a tool's safe fixes for flow or return rules,
   require review before staging. Never enable unsafe fixes or automatic
   business-logic rewrites in a commit hook.
