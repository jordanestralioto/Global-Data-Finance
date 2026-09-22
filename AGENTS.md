## System Overview

Global-Data-Finance (`globaldatafinance`) is a Python library for extracting,
normalizing, and persisting Brazilian CVM regulatory filings and B3 historical
market data. Python applications consume the package; it is not a deployed
service, database, queue, or runtime platform.

The library accepts source selections, date ranges, source files, configuration,
and caller-owned paths. It returns result objects, downloaded or normalized
data, and Parquet artifacts. Data integrity, input validation, path safety,
deterministic output, and compatibility of public and persisted contracts take
priority over convenience.

CVM and B3 behavior remain independently owned by their source areas. Shared
concerns belong in common foundations only when they are genuinely reusable.

## Success Metrics

| Metric           | Target                                           |
| ---------------- | ------------------------------------------------ |
| Coverage gate    | 85% minimum, enforced by `pyproject.toml` and CI |
| Supported Python | `>=3.12,<4.0`; CI validates 3.12, 3.13, and 3.14 |

## Pipeline Architecture

This is a library with data-processing flows, not a deployed data pipeline.
Consumers enter through `src/globaldatafinance/__init__.py`, which exports the
public `FundamentalStocksDataCVM`, `HistoricalQuotesB3`, and
`ExtractionResultB3` contracts. The facades live in
`src/globaldatafinance/application/cvm_docs/` and
`src/globaldatafinance/application/b3_docs/`; they validate and orchestrate
source behavior, return result objects, and write only caller-approved
artifacts.

The CVM implementation owner is
`src/globaldatafinance/brazil/cvm/fundamental_stocks_data/`; the B3 owner is
`src/globaldatafinance/brazil/b3_data/historical_quotes/`. Genuinely shared
configuration, safety, logging, I/O, and base exceptions live in
`src/globaldatafinance/core/`, `src/globaldatafinance/macro_infra/`, and
`src/globaldatafinance/macro_exceptions/`. Keep I/O at the boundary and keep
orchestration separate from validation and transformation. Tests mirror these
public, source, and shared boundaries.

## Configuration & Runtime

| Surface                                   | Location                                                                                                       | Purpose                                                                            |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Package, build, and quality configuration | [pyproject.toml](pyproject.toml)                                                                               | Python range, dependencies, build backend, and tool settings                       |
| Resolved dependencies                     | [uv.lock](uv.lock)                                                                                             | Locked uv dependency state; never hand-edit                                        |
| Test configuration                        | [pytest.ini](pytest.ini)                                                                                       | Test discovery, markers, and defaults; coverage policy remains in `pyproject.toml` |
| Shared runtime foundations                | `src/globaldatafinance/core/`, `src/globaldatafinance/macro_infra/`, `src/globaldatafinance/macro_exceptions/` | Configuration, safety, logging, shared I/O, and base exceptions                    |
| Local quality gates                       | [.pre-commit-config.yaml](.pre-commit-config.yaml)                                                             | Repository-owned validation and formatting hooks                                   |
| CI quality contract                       | [.github/workflows/pipeline.yml](.github/workflows/pipeline.yml)                                               | Supported Python matrix and required CI gates                                      |
| Documentation site                        | [mkdocs.yml](mkdocs.yml)                                                                                       | MkDocs configuration and bilingual navigation                                      |
| Internal agent harness                    | [.agents/harness.json](.agents/harness.json)                                                                   | Development tooling selection; not product code                                    |

### Commands

| Action                               | Command                                                                                                                          |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| Bootstrap locked dependencies        | `uv sync --locked --all-extras --dev`                                                                                            |
| Install repository hooks             | `uv run --locked --no-sync pre-commit install --install-hooks`                                                                   |
| Run the aggregate local gate         | `uv run --locked --no-sync pre-commit run --all-files --show-diff-on-failure`                                                    |
| Run deterministic tests and coverage | `uv run --locked --no-sync pytest -m "not slow and not real_data and not perf" --cov --cov-report=xml --cov-report=term-missing` |
| Run the structural test-quality gate | `uv run --locked --no-sync python scripts/check_test_quality.py`                                                                 |
| Run local COTAHIST fast tests        | `COTAHIST_PATH=./cotahist_b3 COTAHIST_TEST_YEAR=2023 uv run --locked --no-sync pytest -m "real_data and not slow"`               |
| Type-check product code              | `uv run --locked --no-sync mypy src --pretty`                                                                                    |
| Run the repository Ruff gate         | `uv run --locked --no-sync python scripts/check-ruff-policy.py --profile all`                                                    |
| Check formatting                     | `uv run --locked --no-sync ruff format --check src tests scripts examples`                                                       |
| Audit dependencies                   | `uv run --locked --no-sync pip-audit --timeout 60`                                                                               |
| Build documentation strictly         | `uv run --locked --no-sync mkdocs build --strict`                                                                                |
| Build the distribution               | `uv build`                                                                                                                       |

Run Python tooling through `uv run --locked --no-sync`. Use
`uv sync --locked --all-extras --dev` only for deliberate environment bootstrap
or dependency work.

Runtime configuration and logging sources own public variable names, values,
defaults, and behavior. Integration and slow tests can require external sources
or large local data; select them deliberately according to the testing guide.

Test execution has one primary tier per test: `unit`, `integration`, or `perf`.
The `slow`, `asyncio`, and `real_data` markers are orthogonal qualifiers;
`real_data` must accompany `integration`, is excluded from deterministic CI, and
is selected only when the caller provides a local COTAHIST dataset. The `perf`
tier is opt-in and is not part of the normal test discovery contract.
Deterministic integration tests use repository-created ZIP, CSV, Parquet, and
temporary-directory inputs. A future official annual COTAHIST fixture is a
release decision: it must be versioned or published as a licensed CI artifact
before becoming mandatory in CI.

## Technical Stack

The package targets Python `>=3.12,<4.0`, uses a `src/` layout, uv for
dependency management and command execution, Hatchling for builds, and columnar
Parquet for persisted outputs. [pyproject.toml](pyproject.toml) is authoritative
for the exact dependency set, versions, and tool configuration.

Pytest validates behavior and coverage; mypy checks types; pre-commit
coordinates local gates; and the repository owns dedicated security, dependency,
import-boundary, documentation, and package checks. Ruff uses a closed
repository policy: 79-character lines, single-quote formatting, Google-style
docstrings, McCabe complexity capped at 10, and explicit base, documentation,
and security profiles. Run those profiles through
`scripts/check-ruff-policy.py`; `pyproject.toml` owns their exact rules and the
single file-scoped exception.

## Mandatory Rules

- Do not write irrelevant comments in code.
- Verify files before editing; do not assume structure or behavior.
- Plan before modifying and keep scope small, reviewable, and verifiable.
- Write well-factored code with clear single responsibility per function, class,
  or module; do not create monolithic functions that handle multiple concerns.
- Never leave duplicated logic; extract common functionality into shared
  functions or modules.
- Never introduce circular imports or mutual module dependencies.
- Deliver only what is necessary to satisfy the request end-to-end; do not
  bundle unrequested changes or mix structural refactors with bug fixes.
- Tests must prove relevant behavior, edge cases, and regressions, not merely
  nominal line coverage. Keep every test on exactly one primary tier; use
  `real_data` only with `integration`, and use `slow`, `asyncio`, and `perf` as
  explicit qualifiers according to their contracts. Keep external-source tests
  marked as integration and slow tests marked as slow; use the deterministic
  local gate by default.
- Always act as a skeptic: verify hypotheses empirically instead of accepting
  them, whether they came from the user or from you. Never flatter the user or
  engage in sycophantic agreement.
- Do not write code files whose sole purpose is to re-export other files or
  modules without added value.
- `__init__.py` files must contain only explicit exports, never implementation
  logic.
- Never edit generated mirrors or generated files directly; change the canonical
  source and run the documented generation or synchronization step.
- Code, comments, Git branches, commits, pull requests, and planning artifacts
  are English. Maintain product documentation in Portuguese and English
  counterparts.
- Follow the repository's established naming, formatting, ownership, and module
  boundaries.
- Preserve the current library shape and established abstractions. Do not add a
  web framework, deployment runtime, competing framework, or parallel
  architectural path without an explicit decision.
- Use repository-native entrypoints and official scripts before ad hoc commands.
- Preserve the public package boundary in `src/globaldatafinance/__init__.py`
  and the facades under `src/globaldatafinance/application/`. Preserve public
  signatures, defaults, result and exception behavior, persisted schemas, and
  output naming; stop and ask before making a breaking change.
- Keep source-specific CVM and B3 behavior in their owners under
  `src/globaldatafinance/brazil/`. Put a concern in `core/`, `macro_infra/`, or
  `macro_exceptions/` only when it is genuinely shared; do not force different
  sources into an identical internal file layout.
- Preserve the B3 `COTAHIST_AYYYY.(ZIP|TXT)` filename contract, basename-only
  output names, and distinct `fast`/`slow` processing semantics.
- Keep I/O at the boundary, orchestration separate from validation and
  transformation, and library output on the established logging and presentation
  paths.
- Validate inputs, downloaded content, and path safety before extraction,
  directory creation, or writes. Preserve diagnostic causes; never swallow
  failures silently.
- Add a data source as one complete vertical slice: source implementation under
  `src/globaldatafinance/brazil/`, facade under
  `src/globaldatafinance/application/`, root public export, mirrored behavior
  tests, and canonical documentation. Reuse existing source boundaries where
  they fit; do not create abstraction layers merely to make two sources look
  symmetrical.
- Type-annotate public surfaces and run
  `scripts/check-ruff-policy.py --profile all` for the complete Ruff contract.
  Do not broaden rule selections or ignores casually.
  `scripts/process_runner.py` is the sole subprocess boundary and its scoped
  `S603` exception is not precedent for other modules.
- Update tests, contracts, and canonical documentation when behavior or a public
  boundary changes.
- Keep intentional test deletions, relocations, and consolidations documented
  with a scoped reason in `.test-integrity-policy.json`; never weaken the
  integrity gate globally.
- Do not leave dead code, unused compatibility paths, duplicated ownership, or
  stale documentation after a completed clean cutover unless compatibility is an
  explicit requirement.
- Treat runtime code, manifests, tests, accepted decisions, and current
  documentation as current state. Treat proposals and unimplemented material in
  `openspec/` as planned state.
- Use the `Related Documentation` table as a task-driven routing map. Open only
  the smallest relevant source; do not read every linked document or repeat a
  read on every turn unless the task scope or repository state changes, or a
  conflict requires revalidation.
- Keep this file focused on durable policy, macro boundaries, and navigation.
  Put detailed contracts in their canonical owner documents and link to them.
- Before concluding, run the official validation relevant to the changed scope.
  Report `passed`, `failed`, `skipped`, and `external_failure` separately.

## Execution Policy

### Precedence

Rank: system constraints → repository/workspace policy and tooling → user
request. Act on the highest-ranking unambiguous, safe instruction without asking
again. If same-rank instructions conflict, prefer the more specific and safer
one.

### Secrets

Never seek, log, copy, or expand secrets. Treat `.env`, API keys, tokens,
cookies, auth sessions, certificates, and private keys as sensitive. If a secret
appears in output: stop, redact it, and report that sensitive data was found.

### Repo Alignment

Follow the repository's canonical contracts, documentation, current code,
accepted decisions, and official scripts before inventing a new workflow. Prefer
existing project patterns, entrypoints, and abstractions over ad hoc
alternatives. Do not silently change public contracts, persisted formats,
authentication flows, runtime topology, or security boundaries. If code, docs,
and tooling disagree, stop, report the ambiguity, and identify the conflicting
sources.

### Autonomy

Execute reversible repository/workspace changes without confirmation only when
all hold:

- Goal and success criteria are unambiguous.
- Change is contained inside the authorized repository/workspace scope.
- Change is fully recoverable via version control.

Stop and ask when scope is ambiguous, side effects are destructive, external
systems or production are involved, secrets are involved, or same-rank
instructions conflict.

### Validation

Before concluding code or tooling changes, use the repository's official
validation entrypoint for the affected scope. Prefer repository-native commands
and scripts over custom one-off equivalents. If validation is skipped,
unsupported, or failing, report the reason and impact; never treat it as a pass.

### Execution Safety

Before any destructive, publish, migration, deployment-like, or external-state
operation:

1. State exactly what will be affected.
2. Inspect and validate the exact target and scope.
3. Run a dry run when the command supports it.
4. Break complex operations into readable steps; do not hide behavior in opaque
   one-liners.

Before running local scripts, inspect the command path. Stop and ask if a script
is obfuscated, downloads executables, touches secrets, or has unclear side
effects.

### Failure Handling

If a security lock, permission denial, authentication boundary, or authorization
boundary blocks the task, stop. Do not work around it. Report the block, the
evidence, and the safest next step.

## Related Documentation

Open only what the current task needs. This table is a routing map, not a
mandatory reading sequence. Start with the smallest source that can answer the
question, use orientation documents only when context is unfamiliar or
insufficient, and follow the owner document for the affected boundary. Do not
reopen previously inspected files on every turn or continuation unless the scope
or repository state changes, or a conflict requires revalidation.

| Doc                                                                                                                                                                                                                                                          | Knowledge class        | Purpose                                                                                                                            |
| ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| [README.md](README.md) and [docs/index.md](docs/index.md)                                                                                                                                                                                                    | Orientation            | Use when repository or product context is unfamiliar or insufficient; README covers identity and docs/index maps the documentation |
| [docs/user-guide/installation.md](docs/user-guide/installation.md), [docs/user-guide/quickstart.md](docs/user-guide/quickstart.md), [docs/user-guide/cvm-docs.md](docs/user-guide/cvm-docs.md), and [docs/user-guide/b3-docs.md](docs/user-guide/b3-docs.md) | User guide             | Consumer setup and source-specific inputs, outputs, and usage                                                                      |
| [docs/dev-guide/architecture.md](docs/dev-guide/architecture.md) and [docs/dev-guide/contributing.md](docs/dev-guide/contributing.md)                                                                                                                        | Development            | Ownership, boundaries, commands, quality policy, and contribution workflow                                                         |
| [docs/dev-guide/testing.md](docs/dev-guide/testing.md) and [tests/](tests/)                                                                                                                                                                                  | Tests                  | Markers, test organization, fixtures, and executable behavior proof                                                                |
| [docs/dev-guide/api-reference.md](docs/dev-guide/api-reference.md) and [docs/reference/](docs/reference/)                                                                                                                                                    | Reference              | Public API, data, result, and exception contracts                                                                                  |
| [docs/dev-guide/logging-system.md](docs/dev-guide/logging-system.md), [docs/dev-guide/retry-strategy.md](docs/dev-guide/retry-strategy.md), and [docs/dev-guide/resource-monitoring.md](docs/dev-guide/resource-monitoring.md)                               | Operations             | Logging, retry, and resource-management behavior                                                                                   |
| [pyproject.toml](pyproject.toml), [uv.lock](uv.lock), [pytest.ini](pytest.ini), [.pre-commit-config.yaml](.pre-commit-config.yaml), and [.github/workflows/pipeline.yml](.github/workflows/pipeline.yml)                                                     | Tooling                | Authoritative package, dependency, test, local-gate, and CI configuration                                                          |
| [examples/README.md](examples/README.md) and [examples/](examples/)                                                                                                                                                                                          | Examples               | Runnable onboarding; open only when the task needs an execution example                                                            |
| [.agents/harness.json](.agents/harness.json)                                                                                                                                                                                                                 | Agent harness manifest | Internal development harness; open only for harness work                                                                           |
| [openspec/](openspec/)                                                                                                                                                                                                                                       | Planned                | Planning material; it does not govern runtime or policy until implemented and accepted                                             |

Portuguese pages are the default documentation. Matching English `*.en.md` pages
are translation counterparts. Generated, mirrored, exploratory, archived, and
unimplemented material is non-canonical unless an accepted decision says
otherwise.
