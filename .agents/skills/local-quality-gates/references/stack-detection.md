# Workspace Stack and Toolchain Detection Guide

> Summary: Heuristics and indicator files for identifying languages, package managers, formatters, linters, typecheckers, and test runners in a workspace.

## 1. Package Managers and Language Indicators

| Ecosystem           | Manifest File                         | Lockfile                        | Execution Prefix     |
| :------------------ | :------------------------------------ | :------------------------------ | :------------------- |
| **Python (uv)**     | `pyproject.toml`                      | `uv.lock`                       | `uv run`             |
| **Python (poetry)** | `pyproject.toml`                      | `poetry.lock`                   | `poetry run`         |
| **Python (pip)**    | `requirements.txt`, `requirements.in` | `requirements.txt`              | `python -m`          |
| **Node (pnpm)**     | `package.json`                        | `pnpm-lock.yaml`                | `pnpm exec` / `pnpm` |
| **Node (npm)**      | `package.json`                        | `package-lock.json`             | `npx` / `npm run`    |
| **Node (yarn)**     | `package.json`                        | `yarn.lock`                     | `yarn`               |
| **Node (bun)**      | `package.json`                        | `bun.lock` (`bun.lockb` legacy) | `bun x` / `bun`      |
| **Rust**            | `Cargo.toml`                          | `Cargo.lock`                    | `cargo`              |
| **Go**              | `go.mod`                              | `go.sum`                        | `go`                 |
| **PHP**             | `composer.json`                       | `composer.lock`                 | `composer exec`      |

## 1.1 Dependency Lifecycle Classification

The manifest and lockfile table identifies the files to protect; it does not
tell the agent to update dependencies in a hook. Classify the package-manager
commands into three separate roles before composing a gate:

| Role                       | Allowed in pre-commit?                                                                  | Examples                                                                                                                                                      |
| :------------------------- | :-------------------------------------------------------------------------------------- | :------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Lockfile validation        | Yes, when deterministic and it does not rewrite dependency declarations or the lockfile | `uv lock --check`, `poetry check --lock`, `cargo check --locked`, a project-configured `go mod tidy -diff` when supported, or staged manifest/lockfile parity |
| Environment sync/bootstrap | No by default; run explicitly during setup                                              | `uv sync --locked`, `poetry install`, `npm ci`, `pnpm install --frozen-lockfile`, `yarn install --immutable`, `go mod download`                               |
| Dependency update/resolve  | No; perform as a reviewed change                                                        | `uv lock --upgrade`, `poetry update`, `npm update`, `pnpm update`, `yarn up`, `bun update`, `cargo update`, `go get -u`, `composer update`                    |

The execution prefix (`uv run`, `pnpm exec`, `cargo`, and so on) is not a
lockfile policy by itself. If it implicitly synchronizes an environment, use
it only as an existing project contract or add the manager's no-sync option
after explicit setup. Never infer an updater from the presence of a manifest
and lockfile. When the manager has no safe native check, use the shared
lockfile-parity gate and document the limitation instead of inventing a
mutating command.

Go nuance: `go.sum` records module checksums, not a fully resolved lockfile.
`go mod verify` audits downloaded module-cache contents and may add missing
checksum entries, so it is not a read-only `go.mod`/`go.sum` coherence check.
Prefer `go mod tidy -diff` when the project's Go version supports it and the
observed cost is acceptable; otherwise use staged parity and keep cache
integrity auditing in a separate gate.

## 2. Toolchain Discovery Heuristics

Before selecting a tool, inspect the workspace configuration files:

### Python

- **Ruff**: Search for `[tool.ruff]` in `pyproject.toml` or `ruff.toml`.
- **Mypy**: Search for `[tool.mypy]` in `pyproject.toml` or `mypy.ini` / `setup.cfg`.
- **Pyright**: Search for `pyrightconfig.json` or `[tool.pyright]` in `pyproject.toml`.
- **Pytest**: Search for `[tool.pytest.ini_options]` in `pyproject.toml` or `pytest.ini` / `conftest.py`.
- **Circular imports**: If an acyclic graph is project policy, reuse `import-linter`, `pycycle` or an existing architecture command. Report missing deterministic coverage instead of a false pass.

### JavaScript / TypeScript

- **Biome**: Search for `biome.json` or `biome.jsonc`.
- **ESLint**: Search for `eslint.config.js`, `.eslintrc.*`, or `"eslintConfig"` in `package.json`.
- **Prettier**: Search for `.prettierrc*`, `prettier.config.js`, or `"prettier"` in `package.json`.
- **TypeScript (tsc)**: Search for `tsconfig.json`.
- **Test Runners**: Inspect `package.json` for `vitest`, `jest`, `playwright`, `mocha`.
- **Circular dependencies**: If required, reuse `madge --circular`, `dependency-cruiser` or an existing package script. Report missing deterministic coverage.

### Go

- Standard: `gofmt`, `go vet`, `golangci-lint` (`.golangci.yml`).
- **Circular imports**: The Go compiler rejects import cycles; when that policy is selected, run the narrowest affected `go test`/`go list` package check and report compiler errors as `FAIL`.

### Rust

- Standard: `cargo fmt`, `cargo clippy` (`clippy.toml`), `cargo check`.
- **Circular dependencies**: Inspect the existing Cargo/module architecture command. When selected, `cargo check` covers compiler-level cycles; use a configured graph checker for module-level rules.

### Other or polyglot repositories

- When the project requires acyclic dependencies, locate its graph or architecture validator. A missing tool means requested coverage is `UNSUPPORTED`.

## 3. Structural Lint Capability Discovery

For a selected structural profile, inspect the linter before declaring
`[LINTER]` complete. Record the rule, metric, threshold, file scope, and one of
`ENABLED`, `DELEGATED`, `MANUAL`, or `UNSUPPORTED` for each capability:

1. Cyclomatic complexity and cognitive complexity as separate metrics.
2. Maximum nesting depth for control flow and handlers.
3. Redundant branches after terminal statements and avoidable nesting.
4. Empty handlers, broad catches, and preserved error context.
5. Routine size by executable statements or the closest explicitly named
   native metric.

Also inspect whether the tool can limit work to changed or affected code and
whether the project already owns a non-growing baseline. Do not infer support
from a generic lint command, equate lines with statements, add a new dependency
without authorization, or replace parser-aware analysis with a diff regex.

More than five positional parameters is a review signal when the configured
linter exposes that metric. It is not required as a universal blocking rule.

## 4. Existing Hook Runner Detection

Check for prior git hook configurations:

1. `.pre-commit-config.yaml` -> Python-based pre-commit framework.
2. `.husky/` -> Node Husky hook runner.
3. `lefthook.yml` / `.lefthook/` -> Lefthook binary runner.
4. `.git/hooks/` -> Plain shell scripts.

Confirm the effective `core.hooksPath`, installed hook files and runtime
availability. A configuration file alone does not activate a Git hook.

## 5. Reuse-First Decision Matrix

1. If the repository already uses `biome`, do not introduce `eslint` or `prettier`.
2. If the repository uses `ruff`, do not introduce `black`, `flake8`, or `isort`.
3. If the repository already has an active runner (e.g. Husky or pre-commit), extend the existing runner instead of replacing it.
4. With no runner, choose one the project can pin, install and maintain. Do
   not select pre-commit or Lefthook solely from the language name.
