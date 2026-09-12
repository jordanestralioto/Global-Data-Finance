# Contributing Guide

Complete instructions and developer expectations for contributing code and feature enhancements to Global-Data-Finance.

______________________________________________________________________

## Configuring Your Development Environment

### 1. Fork and Clone

```bash
# Create a fork on GitHub, then execute:
git clone https://github.com/jordanestralioto/Global-Data-Finance.git
cd Global-Data-Finance
```

### 2. Install Dependencies

`uv` serves as the canonical project dependency manager (with the verified `uv.lock` committed directly to repository tracking). Development uses **Python >=3.12,<4.0**. The current CI workflow exercises Python 3.12, 3.13, and 3.14.

```bash
# Synchronize the exact lockfile-approved environment (creates .venv)
uv sync --locked --all-extras --dev

# Execute commands without implicit environment synchronization:
uv run --locked --no-sync pytest
uv run --locked --no-sync mypy src
```

### 3. Install Pre-commit Quality Hooks

```bash
uv run --locked --no-sync pre-commit install --install-hooks
```

______________________________________________________________________

## Code Style & Standards

### Style Guidelines

- Strictly obey **PEP 8** formatting rules
- Declare comprehensive **type hints** across all public and private signatures
- Format module docstrings adhering to **Google Style** documentation layouts
- Enforce a hard line length boundary of **79 characters** (evaluated via Ruff Blue-style rules)

### Ruff Profiles

Ruff uses an explicit base selection for `src/`, `tests/`, `scripts/`, and
`examples/`. The `scripts/check-ruff-policy.py` script is the single internal
entrypoint for the complete profiles: `base` verifies the base selection,
`docs` applies Google docstring rules to `src/`, `scripts/`, and `examples/`
(excluding `**/__init__.py`), and `security` applies `S` rules to code and
scripts and to tests with only `S101` ignored.

The base selection preserves the existing simplification and correctness rules
and adds two focused contracts. `C901` limits McCabe cyclomatic complexity to
**10 per function**: complexity 10 passes and 11 or more fails. `BLE001`,
`TRY203`, `TRY400`, and `TRY401` prevent blind catches, useless reraises, and
logging that discards or repeats exception context. The full `TRY` group and
`PLR0912` are not part of this gate.

```bash
# Verify every profile and the policy shape in pyproject.toml
uv run --locked --no-sync python scripts/check-ruff-policy.py --profile all

# Reproduce only the complexity and exception gate
uv run --locked --no-sync ruff check --select C901,BLE001,TRY203,TRY400,TRY401 src tests scripts examples

# Check formatting without changing files
uv run --locked --no-sync ruff format --check src tests scripts examples
```

This is a closed policy: the checker rejects every Ruff key outside the
canonical shape and values, including `exclude`, `extend`, `ignore`,
`extend-ignore`, `extend-select`, `extend-per-file-ignores`, and unexpected
nested tables. The only per-file exception is `S603` in
`scripts/process_runner.py`, which centralizes allowlisted, resolved,
shell-free command execution for tooling scripts. Those scripts must not call
`subprocess` directly.

### Docstring Implementation Example

```python
def download_docs(
    self,
    destination_path: str,
    list_docs: list[str] | None = None,
) -> DownloadResultCVM:
    """Downloads official regulatory disclosures from CVM servers.

    Args:
        destination_path: Target local storage repository directory.
        list_docs: Explicit collection of document codes to retrieve. If None, downloads all available filings.

    Returns:
        A DownloadResultCVM tracking object summarizing success metrics and failure records.

    Raises:
        InvalidDocumentName: Raised if an unsupported document string is supplied.
        InvalidDestinationPathError: Raised if the destination path is invalid or unsafe.
    """
    pass
```

______________________________________________________________________

## Automated Testing

### Executing the Test Suite

```bash
# Execute complete repository test suite
uv run --locked --no-sync pytest

# Execute tests alongside coverage report calculation
uv run --locked --no-sync pytest --cov

# Execute strictly fast unit tests
uv run --locked --no-sync pytest -m unit
```

Prior to submitting any Pull Request, verify quality compliance across the entire verification pipeline:

```bash
uv run --locked --no-sync pre-commit run --all-files --show-diff-on-failure
uv run --locked --no-sync pytest
```

### Local Quality Gates

The `pre-commit` hook validates the staged index and keeps dependency updates
outside the commit path. It never runs `uv sync`, `uv lock`, or a version
updater: `uv lock --check` only proves the current lockfile is coherent. The
`pre-push` hook runs the more expensive type, coverage, and vulnerability
checks before a branch is published.

The local Gitleaks hook checks only staged content to keep commit feedback
fast. CI runs an additional directory-mode scan over a clean checkout, so it
does not depend on staged files. `pip-audit` remains outside the fast
`pre-commit` stage and runs during the heavier `pre-push` and CI validation.

When a dependency must change, make that operation explicit, review the
`uv.lock` diff, synchronize the environment, and then commit:

```bash
uv lock --upgrade
uv sync --locked --all-extras --dev
git add pyproject.toml uv.lock
```

The diff-sanity, test-integrity, and shell-syntax gates inspect only staged
content during a commit. CI invokes the same scripts over the pull request or
push commit range, so a diff `SKIP` without staged files is not a CI approval.

`.agents/` remains tracked so every clone distributes the portable validators,
but it is a generated projection maintained by the separate `central-skills`
repository; generated files must never be edited manually.
Ordinary contributors and project users do not need a `central-skills`
installation. A maintainer changing the selection or projection must fix
the canonical source, regenerate with `harness-sync`, and run the check:

```bash
harness-sync --check
```

The `check-harness-sync` hook is manual and intended only for maintainers with
the optional executable installed. It is not part of the default `pre-commit`,
`pre-push`, or CI stages; when the executable is absent, the check fails
explicitly instead of producing a false `SKIP`.

Generic hooks have an explicit exclusion for `.agents/`, `.claude/`, `.codex/`,
`.opencode/`, and `.github/prompts/`, so they do not format or inspect those
projections. The tracked validators inside `.agents/` are the deliberate
exception: they can run directly from a clone and do not require an external
installation. The optional synchronization executable being absent does not
block normal commits or pushes; real validator failures must be fixed rather
than bypassed by disabling hooks.

### Authoring Unit Tests

```python
import pytest
from globaldatafinance import FundamentalStocksDataCVM

@pytest.mark.unit
class TestFundamentalStocksData:
    def test_get_available_docs(self):
        """Verifies successful retrieval of supported document catalog."""
        cvm = FundamentalStocksDataCVM()
        docs = cvm.get_available_docs()

        assert isinstance(docs, dict)
        assert "DFP" in docs
        assert len(docs) > 0
```

______________________________________________________________________

## Git Workflow

### Branch Organization

- `main`: Production-grade stable code release history
- `develop`: Active integration testing and current feature staging
- `feature/feature-name`: Autonomous branch for new capability expansions
- `fix/bug-name`: Targeted remediation branch for resolving bugs

### Commit Formatting

Adopt structured, semantic, and descriptive commit formatting:

```bash
# Good examples
git commit -m "feat: implement asynchronous parallel worker pool for CVM downloads"
git commit -m "fix: resolve socket timeout exception during multi-decade COTAHIST extractions"

# Discouraged examples
git commit -m "update code"
git commit -m "fix bug"
```

### Pull Request Lifecycle

1. Branch off directly from `develop`
2. Implement your code changes or bug remediations
3. Contribute accompanying automated test suites
4. Update canonical documentation files and inline docstrings
5. Submit your Pull Request targeting `develop`

______________________________________________________________________

## Pull Request Checklist

- [ ] Code fully complies with PEP 8 and formatting constraints
- [ ] Explicit type annotations added to all signatures
- [ ] Comprehensive Google-style docstrings authored
- [ ] Test suites authored demonstrating happy/error paths
- [ ] Entire testing verification suite passes cleanly
- [ ] Repository documentation artifacts updated accordingly
- [ ] Pre-commit repository verification hooks run clean without warnings

______________________________________________________________________

## Support Contact

- **GitHub Issues**: [Open an issue](https://github.com/jordanestralioto/Global-Data-Finance/issues)
- **Direct Email**: estraliotojordan@gmail.com
