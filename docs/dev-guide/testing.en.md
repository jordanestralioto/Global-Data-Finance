# Testing Strategy

Comprehensive guide detailing automated test organization, execution commands, and testing patterns implemented within Global-Data-Finance.

______________________________________________________________________

## Test Repository Hierarchy

The test directory structure cleanly mirrors the source tree. Subdirectories inside individual source test folders serve a strictly **organizational** purpose (grouping test scripts by functional topic to enhance code legibility) rather than architectural enforcement—all testing fixtures import symbols directly from the owning source modules.

```text
tests/
├── application/                       # Unit tests evaluating public application facades
│   ├── cvm_docs/
│   └── b3_docs/
│       └── result_formatters/
├── brazil/
│   ├── b3_data/
│   │   └── historical_quotes/
│   │       ├── test_*.py              # domain and facade topics
│   │       ├── extraction_service/    # service, batch parser, resources, merge
│   │       ├── parquet_writer/        # Parquet writing and streaming
│   │       └── integration/            # opt-in local COTAHIST
│   └── cvm/
│       └── fundamental_stocks_data/
│           ├── application/use_cases/ # Orchestration use case tests (client.py)
│           ├── domain/                # Value object and domain validator tests (core.py)
│           ├── infra/adapters/        # Concrete I/O adapter tests (http.py, extract.py)
│           ├── exceptions/            # Custom exception triggering suites (errors.py)
│           └── integration/           # CVM flows with real local ZIP/filesystem
├── core/
├── macro_infra/
└── macro_exceptions/
```

______________________________________________________________________

## Executing Tests

### Deterministic Default Gate

```bash
uv run --locked --no-sync pytest -m "not slow and not real_data and not perf" \
  --cov --cov-report=xml --cov-report=term-missing
```

This command includes unit tests and deterministic integrations built by the
tests themselves. `perf`, real-data, and `slow` scenarios are outside the
default gate.

### Evaluating Code Coverage

Coverage configuration, including the `fail_under = 85` threshold, is owned by
`[tool.coverage.report]` in `pyproject.toml`. The `pytest.ini` file owns pytest
discovery, markers, and options.

```bash
uv run --locked --no-sync pytest -m "not slow and not real_data and not perf" \
  --cov --cov-report=html
```

### Utilizing Pytest Markers

Markers registered in `pytest.ini` have separate contracts. Every test must
have exactly one primary tier:

- `unit`: isolated behavior with fakes, stubs, or pure collaborators;
- `integration`: multiple real production components and deterministic local
  filesystem behavior;
- `perf`: benchmark or resource measurement, opt-in only.

`slow`, `asyncio`, and `real_data` are orthogonal qualifiers. `real_data`
requires `integration`, and `asyncio` never replaces the primary tier.

The `scripts/check_test_quality.py` gate is a structural heuristic: it checks
classification and an accepted observation in the test's direct executable
body without descending into nested helpers, lambdas, or classes. It does not
prove that every assertion protects a regression or remove the need for review
against semantic tautologies.

```bash
# Execute only rapid isolated unit tests
uv run --locked --no-sync pytest -m unit

# Execute deterministic integrations without external data or slow scenarios
uv run --locked --no-sync pytest -m "integration and not slow and not real_data and not perf"

# Execute benchmarks and resource measurements (explicit opt-in)
uv run --locked --no-sync pytest tests/perf -m perf -o addopts=''
```

### Local COTAHIST

`real_data` tests never download files or version financial data. The directory
is caller-owned and can be supplied through `COTAHIST_PATH`; the library never
loads `.env` implicitly. To use a local dotenv file, the caller must select it
explicitly with `uv run --env-file .env`. Without `COTAHIST_PATH`, only the
explicitly selected suite is skipped; once the variable is set, a missing,
empty, unreadable path or missing selected year fails.

The fixture inspects the catalog of every local file before selecting a year.
When exactly one year exists, it may be inferred. With multiple years,
`COTAHIST_TEST_YEAR` is required; the fixture never silently chooses the
largest year. The catalog validates the central directory and internal-member
resolution. Limited parity derives a non-empty sample of up to 20,000 real
`01` records and compares fast/slow across all 20 columns with exact types and
ordering; because it runs both processing modes, it is marked `slow`. The
annual proof, also marked `slow`, processes one full year only once in `fast`
mode.

```bash
COTAHIST_PATH=./cotahist_b3 COTAHIST_TEST_YEAR=2000 \
  uv run --locked --no-sync pytest -m "real_data and not slow"
COTAHIST_PATH=./cotahist_b3 COTAHIST_TEST_YEAR=2000 \
  uv run --locked --no-sync pytest -m "real_data and slow"
COTAHIST_PATH=./cotahist_b3 COTAHIST_TEST_YEAR=2024 \
  uv run --locked --no-sync pytest -m "real_data and not slow"
COTAHIST_PATH=./cotahist_b3 COTAHIST_TEST_YEAR=2024 \
  uv run --locked --no-sync pytest -m "real_data and slow"
```

`COTAHIST_TEST_YEAR` must contain four digits. ZIP takes precedence over TXT
for one year. Modern ZIPs use an internal `COTAHIST_A{YYYY}.TXT` member;
historical ZIPs may use `COTAHIST.A{YYYY}` or the extensionless
`COTAHIST_A{YYYY}` member. The `cotahist_b3/` directory is Git-ignored. A future official annual dataset can
be made mandatory in CI only after a versioned fixture or licensed published
CI artifact exists; until then, validation remains opt-in.

### Auditable real-data campaign

To audit the complete matrix without relying on implicit environment
configuration, run the opt-in executor with every path supplied explicitly.
Keep the report and temporary artifacts outside the repository:

```bash
uv run --locked --no-sync python scripts/real_validation.py \
  --source all \
  --cotahist-path /external/path/COTAHIST \
  --cvm-output /tmp/globaldatafinance-cvm-output \
  --report /tmp/globaldatafinance-real-validation/run-2026-09-01 \
  --timeout 3600
```

`all` creates the 25 COTAHIST years from 2000 through 2024 and the seven
document windows, totaling 102 CVM combinations. For each COTAHIST year, the
executor runs `fast` and a complete `fast`/`slow` parity; the local file is
validated and ZIP precedence is applied before processing. COTAHIST is never
downloaded by the executor. The CVM matrix contacts only the official URLs
defined explicitly in code and classifies HTTP 404/410 as `not_published`,
network unavailability as `external_failure`, and invalid content or processing
failures as `failed`.

Each case runs in an isolated process. The directory supplied to `--report`
contains `manifest.json`, one current result per case in `results.jsonl`,
`summary.json`, individual logs, and artifact evidence. Use `--resume
--report <same-directory>` to rerun only `external_failure` cases or cases
that have not been classified; functional results and `not_published` cases
are preserved. Persisted results are caller-owned evidence, not a signed
attestation: use `--resume` only with a trusted report directory when a
pass/fail conclusion must serve as evidence. Before resuming, every COTAHIST
input is compared with the
manifest `inputSizeBytes` and `inputSha256`. A shared path is hashed once;
any drift raises `ReportFormatError`, does not rerun or overwrite old results,
and requires a new campaign. The COTAHIST `caseId`, year, mode, and input must
also agree with the current catalog. CVM resume first validates the persisted
`campaign.cvmOutput` with the external-destination policy, then rebuilds cases
from the official document/year matrix: persisted fields, including
`inputPath`, `url`, and `outputRoot`, must match both the rebuilt case and the
campaign destination before a worker starts. A tampered `outputRoot` fails
before `mkdir`, `mkdtemp`, a worker, or an HTTP client. The CVM probe uses only
the canonical HTTPS endpoint, does not follow redirects, and never persists a
preflight body. The compressed-archive byte limit is enforced from
both `Content-Length` and the public-facade stream; the recorded hash is taken
from the ZIP immediately before that facade extracts it. `--report` and
`--cvm-output` pass through the sensitive-destination policy before any
directory is created; system roots, protected directories, relative Windows
drives, and untrusted UNC paths are rejected, while `/tmp` and an explicitly
allowed UNC root can be used under the shared policy. Exit code `0` is reserved
for a fully executed matrix with no functional failures, external failures,
unexecuted combinations, or orphan processes; `1` indicates a functional
failure, and `2` indicates an external dependency, timeout, incomplete
execution, or orphan process.

______________________________________________________________________

## Authoring Tests

### Unit Test Pattern

```python
import pytest
from globaldatafinance.brazil.cvm.fundamental_stocks_data.core import (
    validate_docs_name,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.errors import (
    InvalidDocumentName,
)


@pytest.mark.unit
class TestValidateDocsName:
    def test_validate_valid_doc(self):
        """Verifies validation succeeds without exception on valid document code."""
        validate_docs_name('DFP')  # Should pass silently

    def test_validate_invalid_doc(self):
        """Verifies InvalidDocumentName is raised upon supplying unverified strings."""
        with pytest.raises(InvalidDocumentName):
            validate_docs_name('INVALID_CODE')
```

> Types and exceptions belong within the focused modules of their owning source feature: for CVM inside `brazil.cvm.fundamental_stocks_data.core` and `brazil.cvm.fundamental_stocks_data.errors`; for B3 logical separation is segmented topically—entities in `models.py`, value objects in `years.py`/`processing.py`, path security validators in `filesystem.py`, asset services in `assets.py`, and exceptions in `errors.py`.

### Mock and Dependency Substitution Strategies

To decouple unit verification from live network servers or real storage file system IO, test fixtures substitute external adapters using duck-typed stubs or `monkeypatch.setattr`:

```python
from globaldatafinance.brazil.cvm.fundamental_stocks_data.client import (
    DownloadDocumentsUseCaseCVM,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.core import (
    DownloadResultCVM,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.http import (
    DownloadTaskCVM,
)


class MockRepository:
    def download_docs(
        self,
        tasks: list[DownloadTaskCVM],
        *,
        automatic_extractor: bool | None = None,
    ) -> DownloadResultCVM:
        return DownloadResultCVM(
            successful_downloads=['DFP_2023', 'ITR_2023'],
            failed_downloads={},
            elapsed_time=0.5,
        )


use_case = DownloadDocumentsUseCaseCVM(MockRepository())
result = use_case.execute(destination_path='/tmp/cvm')
assert result.success_count_downloads == 2
```

### Required engines and real proofs

PyArrow is the required production read/write engine. Pandas remains a
compatibility dependency for the legacy `ReadFilesAdapter`, while Polars is not
part of runtime dependencies. Unit tests may use fakes for project-owned
collaborators such as a resource monitor, parser, or filesystem seam. They do
not replace tests of a component that reads or writes Parquet: that component
also needs integration tests with real PyArrow, artifact reads, schema and type
checks, and temporary-file cleanup.

### Integration Testing Pattern

```python
import pytest
from globaldatafinance import FundamentalStocksDataCVM


@pytest.mark.integration
class TestFundamentalStocksDataIntegration:
    def test_get_available_docs(self):
        """Evaluates live instantiation and catalog mapping generation."""
        cvm = FundamentalStocksDataCVM()
        docs = cvm.get_available_docs()

        assert isinstance(docs, dict)
        assert len(docs) > 0
        assert 'DFP' in docs
```

______________________________________________________________________

## Standard Test Fixtures

```python
import pytest
from pathlib import Path


@pytest.fixture
def temp_dir(tmp_path):
    """Provides an isolated temporary directory per test execution."""
    return tmp_path


@pytest.fixture
def sample_zip_file(tmp_path):
    """Creates an automated mockup ZIP archive file fixture."""
    zip_path = tmp_path / 'test.zip'
    # Construct mockup ZIP structural headers...
    return zip_path
```

______________________________________________________________________

## Coverage Goals & Gates

Target: **>= 85% aggregated code coverage** (automatically enforced via
`fail_under = 85` in `[tool.coverage.report]` within `pyproject.toml`). This is
also the floor for newly introduced feature modules.

```bash
# Generate terminal missing line summary report
uv run --locked --no-sync pytest -m "not slow and not real_data and not perf" \
  --cov --cov-report=term-missing

# Compile interactive HTML diagnostic coverage tree
uv run --locked --no-sync pytest --cov --cov-report=html
open htmlcov/index.html
```

### Real-validation executor coverage

The `real_validation*.py` modules are operational development code and have a
coverage gate separate from product code. The `real-validation-coverage` hook,
at the `pre-push` stage, runs the deterministic executor tests and requires
`>= 85%` aggregate branch coverage:

```bash
uv run --locked --no-sync pytest -q \
  tests/tooling/test_real_validation.py \
  tests/tooling/test_real_validation_b3.py \
  tests/tooling/test_real_validation_cases.py \
  tests/tooling/test_real_validation_cvm.py \
  tests/tooling/test_real_validation_matrix.py \
  tests/tooling/test_real_validation_report.py \
  tests/tooling/test_real_validation_resume.py \
  tests/tooling/test_real_validation_runner.py \
  tests/tooling/test_real_validation_types.py \
  tests/tooling/test_real_validation_utils.py \
  --cov=scripts.real_validation \
  --cov=scripts.real_validation_b3 \
  --cov=scripts.real_validation_cases \
  --cov=scripts.real_validation_cvm \
  --cov=scripts.real_validation_matrix \
  --cov=scripts.real_validation_report \
  --cov=scripts.real_validation_resume \
  --cov=scripts.real_validation_runner \
  --cov=scripts.real_validation_types \
  --cov=scripts.real_validation_utils \
  --cov-report=term-missing --cov-fail-under=85
```

This gate does not change the 85% product floor for `src`; it prevents
timeouts, cleanup, reports, CVM classifications, B3 parity, or resume logic
from losing coverage without a separate signal. The same check runs as its own
step in the quality pipeline.

______________________________________________________________________

## Continuous Integration (CI/CD)

Automated quality verification gates execute on GitHub Actions during:

- Commit pushes targeting `main` or `develop` branches
- Every Pull Request opened against project target branches
- Tagged release build packaging workflows

______________________________________________________________________

## Next Steps

- [Contributing Guide](contributing.md) - Workflow expectations for contributors
- [Architecture Guide](architecture.md) - Deep structural design concepts
