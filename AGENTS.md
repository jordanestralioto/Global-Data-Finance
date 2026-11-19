# AGENTS.md

## Project Overview

`globaldatafinance` is a Python library that extracts, normalizes, and persists
Brazilian CVM filings and B3 historical quotes; see the [README](README.md).
Applications consume it as a package; it is not a deployed service. Do not add
a web framework, deployment runtime, or competing architectural path without
an explicit decision.

## Development Workflow

Bootstrap with `uv sync --locked --all-extras --dev` only for deliberate
environment or dependency work. Run every other Python tool through
`uv run --locked --no-sync`. Never hand-edit `uv.lock`.

| Action                               | Command                                                                                                                          |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| Install repository hooks             | `uv run --locked --no-sync pre-commit install --install-hooks`                                                                   |
| Install the push ref validator       | `uv run --locked --no-sync python scripts/check_push_snapshot.py --install`                                                      |
| Run the aggregate local gate         | `uv run --locked --no-sync pre-commit run --all-files --show-diff-on-failure`                                                    |
| Run deterministic tests and coverage | `uv run --locked --no-sync pytest -m "not slow and not real_data and not perf" --cov --cov-report=xml --cov-report=term-missing` |
| Run the structural test-quality gate | `uv run --locked --no-sync python scripts/check_test_quality.py`                                                                 |
| Run local COTAHIST fast tests        | `COTAHIST_PATH=./cotahist_b3_local COTAHIST_TEST_YEAR=2023 uv run --locked --no-sync pytest -m "real_data and not slow"`         |
| Type-check product code              | `uv run --locked --no-sync mypy src --pretty`                                                                                    |
| Run the complete Ruff contract       | `uv run --locked --no-sync python scripts/check-ruff-policy.py --profile all`                                                    |
| Audit dependencies                   | `uv run --locked --no-sync python scripts/audit_locked_dependencies.py`                                                          |
| Build documentation strictly         | `uv run --locked --no-sync mkdocs build --strict`                                                                                |
| Build the distribution               | `uv build`                                                                                                                       |

Coverage policy lives in `pyproject.toml`, not `pytest.ini`.
`scripts/check-ruff-policy.py` runs path-scoped `ruff check` profiles and
validates the format configuration; the `ruff-format` pre-commit hook formats
the code.

Diff-based gates inspect the index. With nothing staged they can report `SKIP`
even under `--all-files`; `SKIP` is not a pass. Before concluding, run the
validation relevant to the changed scope and report `passed`, `failed`,
`skipped`, and `external_failure` separately.

### Test tiers

Every test has exactly one primary tier: `unit`, `integration`, or `perf`.
`slow`, `asyncio`, and `real_data` are qualifiers; `real_data` requires
`integration`. Markers are strict, and the default selection excludes `slow`,
`real_data`, and `perf`. Deterministic integration tests build their own ZIP,
CSV, Parquet, and temporary-directory inputs. `real_data` reads a
caller-provided COTAHIST directory and is excluded from deterministic CI; making
an official COTAHIST fixture mandatory in CI is a release decision that needs a
versioned or licensed CI artifact.

Record every intentional test deletion, relocation, or consolidation with a
scoped reason in `.test-integrity-policy.json`; never weaken the integrity gate
globally.

## Engineering Rules

- Branch from `develop` and open pull requests against `develop`.
- Code, comments, branches, commits, pull requests, and planning artifacts are
  English. Product documentation is Portuguese by default, with a matching
  English `*.en.md` counterpart; update both.
- Do not write irrelevant comments in code.
- `__init__.py` files contain only explicit exports, never implementation
  logic. Do not add modules whose only purpose is re-exporting other modules.
- Preserve the public boundary in `src/globaldatafinance/__init__.py` and the
  facades under `src/globaldatafinance/application/`: signatures, defaults,
  result and exception behavior, persisted schemas, and output naming. Stop and
  ask before any breaking change.
- Keep CVM and B3 behavior in their owners under
  `src/globaldatafinance/brazil/`. Move a concern to `core/`, `macro_infra/`, or
  `macro_exceptions/` only when it is genuinely shared; do not force both sources
  into an identical internal layout or add abstractions only for symmetry.
- Preserve the B3 `COTAHIST_AYYYY.(ZIP|TXT)` filename contract, basename-only
  output names, and the distinct `fast`/`slow` processing semantics.
- Keep I/O at the boundary, orchestration separate from validation and
  transformation, and library output on the `application/*_formatter.py` and
  established logging paths.
- Validate inputs, downloaded content, and path safety before extraction,
  directory creation, or writes. Preserve diagnostic causes; never swallow
  failures silently.
- Add a data source as one vertical slice: source implementation under
  `brazil/`, facade under `application/`, root export, mirrored behavior tests,
  and Portuguese and English documentation.
- `scripts/process_runner.py` is the sole subprocess boundary; its scoped
  `S603` exception is not precedent. Do not broaden Ruff selections or ignores
  casually.
- After a clean cutover, remove dead code, compatibility paths, duplicated
  ownership, and stale documentation unless compatibility is an explicit
  requirement.
- Agent projections in `.agents/`, `.claude/`, `.codex/`, and `.opencode/` are
  maintained by the `central-skills` repository. Change that source and
  regenerate instead of editing them here; `harness-sync --check` verifies the
  projection.
- Treat `openspec/` proposals and unimplemented material as planned state; code,
  manifests, tests, accepted decisions, and current documentation are current
  state.

## Navigation

Code owners, relative to `src/globaldatafinance/`; the
[architecture guide](docs/dev-guide/architecture.md) owns the details.

| Concern                                         | Owner                                           |
| ----------------------------------------------- | ----------------------------------------------- |
| Public exports                                  | `__init__.py`                                   |
| Facade validation and orchestration             | `application/cvm_docs/`, `application/b3_docs/` |
| CVM company selection and document policy       | `brazil/cvm/fundamental_stocks_data/`           |
| CVM download, CSV preservation, and publication | `brazil/cvm/ingestion/`                         |
| B3 historical quotes                            | `brazil/b3_data/historical_quotes/`             |
| Configuration, logging, retry, and safety       | `core/`                                         |
| Generic I/O and recoverable publication         | `macro_infra/`                                  |
| Shared base exceptions                          | `macro_exceptions/`                             |

Layer and independence contracts live in `[tool.importlinter]` in
[pyproject.toml](pyproject.toml); `scripts/check-import-cycles.py` blocks import
cycles.

Open only the document that answers the current question:

| Question                                   | Document                                                                                                                                                           |
| ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Consumer setup, inputs, outputs, and usage | [installation](docs/user-guide/installation.md), [quickstart](docs/user-guide/quickstart.md), [CVM](docs/user-guide/cvm-docs.md), [B3](docs/user-guide/b3-docs.md) |
| Contribution flow and hook stages          | [contributing](docs/dev-guide/contributing.md)                                                                                                                     |
| Markers, fixtures, and local COTAHIST data | [testing](docs/dev-guide/testing.md)                                                                                                                               |
| Public API, data, result, and exceptions   | [API reference](docs/dev-guide/api-reference.md), [docs/reference/](docs/reference/)                                                                               |
| Logging, retry, and resource behavior      | [logging](docs/dev-guide/logging-system.md), [retry](docs/dev-guide/retry-strategy.md), [resource monitoring](docs/dev-guide/resource-monitoring.md)               |
| Runnable onboarding examples               | [examples/README.md](examples/README.md)                                                                                                                           |
| Agent harness work only                    | [.agents/harness.json](.agents/harness.json)                                                                                                                       |
