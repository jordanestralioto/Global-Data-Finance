# Contributing to Global-Data-Finance

Thank you for your interest in contributing to Global-Data-Finance.

This file is the quick entry point for contributors. The complete guides,
including source ownership, quality gates, testing, and documentation
requirements, are available in both supported documentation languages:

- [Portuguese contribution guide](docs/dev-guide/contributing.md)
- [English contribution guide](docs/dev-guide/contributing.en.md)

## Prerequisites

- Python `>=3.12,<4.0`
- [uv](https://docs.astral.sh/uv/)
- Git

## Workflow

1. Fork the repository on GitHub.

2. Create a branch from `develop`, using an English descriptive name such as
   `feature/add-source` or `fix/path-validation`.

3. Install the locked development environment and repository hooks:

   ```bash
   uv sync --locked --all-extras --dev
   uv run --locked --no-sync pre-commit install --install-hooks
   ```

4. Implement the change within the existing CVM, B3, application, or shared
   ownership boundaries. Preserve public APIs, persisted schemas, and path
   safety contracts.

5. Add or update tests that prove the changed behavior, relevant edge cases,
   and regressions. Give every test exactly one primary tier (`unit`,
   `integration`, or `perf`); use `slow`, `asyncio`, and `real_data` only as
   explicit qualifiers. Keep caller-owned COTAHIST tests opt-in.

6. Run the safe local validation relevant to the change:

   ```bash
   uv run --locked --no-sync pre-commit run --all-files --show-diff-on-failure
   uv run --locked --no-sync python scripts/check_test_quality.py
   uv run --locked --no-sync pytest -m "not slow and not real_data and not perf" \
       --cov --cov-report=term-missing
   uv run --locked --no-sync mypy src --pretty
   uv run --locked --no-sync python scripts/check-ruff-policy.py --profile all
   uv run --locked --no-sync mkdocs build --strict
   ```

7. Update the canonical Portuguese documentation and its English counterpart
   when behavior, a public boundary, or a user-facing contract changes.

8. Commit in English using
   [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/), for
   example:

   ```bash
   git commit -m "feat: add support for a new data source"
   ```

9. Open a Pull Request against `develop` and include the scope of the change,
   test commands, and any skipped or external checks.

## Dependency and staging policy

Use `uv` for dependency operations and do not create another lockfile. A
dependency change is deliberate: update `pyproject.toml` and `uv.lock`, then
run the locked environment checks before submitting the change.

When the working tree contains unrelated changes, stage only the explicit
paths belonging to the contribution. Do not use `git add .` or `git add -A`.

For security reports, follow [SECURITY.md](SECURITY.md). All participants are
expected to follow [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
