# Contributing

Use Python `>=3.12,<4.0`, Git, and uv. Create your branch from `develop` and
open the pull request against that same branch.

## Set up the environment

```bash
git clone https://github.com/jordanestralioto/Global-Data-Finance.git
cd Global-Data-Finance
uv sync --locked --all-extras --dev
uv run --locked --no-sync pre-commit install --install-hooks
git switch -c fix/cotahist-validation develop
```

`uv sync` prepares the environment once. Afterwards, run tools with
`uv run --locked --no-sync` to use the already resolved dependencies.

## Make the change

- Follow the [architecture](architecture.md): CVM and B3 behavior belongs to
  its source; share only what is reusable.
- Preserve public signatures, results, exceptions, and schemas. Breaking
  changes require an explicit decision and documented migration.
- Use English names, code, comments, and commits. Add type annotations, use
  Google docstrings, and keep Ruff's 79-character formatting.
- Use `_` for helpers confined to their module. A name shared between modules
  does not thereby become part of the public API. Keep mutable state private
  and expose operations when another module needs access.
- Validate inputs and paths before writing. Preserve failure causes.
- Update tests that prove the behavior and regression, and maintain product
  documentation in Portuguese and English.

## Validate before the PR

```bash
uv run --locked --no-sync pre-commit run --all-files --show-diff-on-failure
uv run --locked --no-sync pytest
```

Default pytest selects deterministic tests. For coverage, markers,
integrations, and local data, use the [testing guide](testing.md).

| Change | Additional validation |
| --- | --- |
| Python code | `uv run --locked --no-sync mypy src --pretty` |
| Documentation | `uv run --locked --no-sync mkdocs build --strict` |
| Packaging | `uv build` and [release acceptance](release-readiness.md) |

Installed hooks distribute checks by cost:

| Stage | What it checks |
| --- | --- |
| `pre-commit` | Diff integrity, lockfile, syntax, formatting, lint, and contracts. |
| `commit-msg` | Conventional Commits format. |
| `pre-push` | Types, tests with coverage, and dependency auditing. |

Canonical entries are in `.pre-commit-config.yaml` and `pyproject.toml`.
To reproduce the complete push stage, run
`uv run --locked --no-sync pre-commit run --hook-stage pre-push --all-files`.
Diff gates inspect the index during commits; in CI, they inspect the cumulative
range since the previous release. With no staged changes, diff-based gates
can return `SKIP` even with `--all-files`; that is not approval of those gates.
Local Gitleaks scans the index; CI also scans the complete checkout.

## Submit the PR

Review the diff and stage only the paths belonging to the change. Review
automatic formatting before staging it.

```bash
git commit -m "fix: validate COTAHIST inputs before writing"
```

Describe the problem, final behavior, validation commands, and checks skipped
or dependent on an external environment. For test deletions or consolidations,
record the reason in `.test-integrity-policy.json`.

## Dependencies and internal tooling

Change dependencies deliberately with uv and review `pyproject.toml` and
`uv.lock`. Do not edit the lockfile by hand. Hooks validate the resolution;
updates and environment synchronization stay outside the commit path.

Agent projections in `.agents/`, `.claude/`, `.codex/`, and `.opencode/` are
maintained by the `central-skills` repository. Change the source and regenerate
rather than editing generated files. `harness-sync --check` is a manual
maintainer check; ordinary contributors do not need to install that tool.

To report vulnerabilities, follow the
[security policy](https://github.com/jordanestralioto/Global-Data-Finance/blob/develop/SECURITY.md).
