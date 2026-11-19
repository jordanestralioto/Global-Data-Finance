# Contributing

Use Python `>=3.12,<4.0`, Git, and uv. Create your branch from `develop` and
open the pull request against that same branch.

## Set up the environment

```bash
git clone https://github.com/jordanestralioto/Global-Data-Finance.git
cd Global-Data-Finance
uv sync --locked --all-extras --dev
uv run --locked --no-sync pre-commit install --install-hooks
uv run --locked --no-sync python scripts/check_push_snapshot.py --install
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

Keep local drafts and working notes in `docs/internal/`. Git ignores this
directory, and `check-docs-contracts` excludes it, including the English
translation requirement. The MkDocs build also excludes it.

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
| `pre-push` | Pushed snapshot, types, tests with coverage, and dependency auditing. |

Canonical entries are in `.pre-commit-config.yaml` and `pyproject.toml`.
To reproduce the complete push stage, run
`uv run --locked --no-sync pre-commit run --hook-stage pre-push --all-files`.
During `git push`, every pushed ref that carries new commits must point at the
current checkout, and that checkout must be exactly that commit: no staged or
unstaged changes, no untracked files, no tracked files hidden by
`assume-unchanged` or `skip-worktree` (as in a sparse checkout), and no ignored
Python sources or tool configuration that the tests could load. Otherwise the
tests would validate a different snapshot. In an incremental push, pre-commit
stashes unstaged tracked changes before the hooks and restores them afterward;
the hooks then validate the index. When the push includes the root commit, as
in the first push to an empty remote, there is no stash and `push-snapshot`
rejects those changes. pre-commit passes only the first ref of a push to its
hooks. The command `scripts/check_push_snapshot.py --install`
therefore installs a validator that pre-commit runs before the hooks with each
push's complete list of refs; it keeps no state between pushes. The first hook
(`push-snapshot`) requires that validator, checks the first ref and the
checkout, and without the validator fails with the installation command. When
the rejected ref is not the first, pre-commit still runs its hooks before Git
rejects the push; press Ctrl+C to stop waiting. Push each branch from its own
clean checkout. pre-commit and the validator treat as new only the commits
missing from the local remote-tracking refs (`refs/remotes/<remote>/`). If
those refs are stale, for example after the remote is restored or a branch is
deleted there, a commit they still contain is published without running the
hooks. In those cases, run `git fetch --prune <remote>` before pushing.
The manual reproduction above reports `SKIP` for that hook and
covers the working tree. Ruff, detect-secrets, and mdformat hooks run from the
`uv.lock` environment, at the versions CI uses.
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
updates and environment synchronization stay outside the commit path. When a
`pyproject.toml` change alters the declared dependencies, such as adding or
removing one, `uv lock --check` builds the project metadata with hatchling and
hatch-vcs. Without those packages in the uv cache, the check must reach the
package index. Without network access, it fails as an infrastructure error and
blocks the commit until it is repeated with network access or a populated
cache. Edits that keep the dependencies, such as changing the description, did
not need those packages with uv 0.13.7.

Agent projections in `.agents/`, `.claude/`, `.codex/`, and `.opencode/` are
maintained by the `central-skills` repository. Change the source and regenerate
rather than editing generated files. `harness-sync --check` is a manual
maintainer check; ordinary contributors do not need to install that tool.
Formatting hooks do not edit `.agents/`. Secret scanners, read-only
validators, `diff-sanity`, and `shell-syntax` inspect that projection, because
hooks execute scripts from it. Only the debug and stub rules of `diff-sanity`
skip it, since the harness CLIs print by design.

To report vulnerabilities, follow the
[security policy](https://github.com/jordanestralioto/Global-Data-Finance/blob/develop/SECURITY.md).
