# Test execution tiers and local COTAHIST validation

**Status:** Accepted
**Date:** 2026-08-30
**Scope:** repository tests and quality gates

## Decision

The test suite assigns exactly one primary tier to every test:

- `unit`: isolated behavior using pure functions, fakes, stubs, or controlled
  local collaborators;
- `integration`: a flow crossing two or more real production components,
  including deterministic local filesystem, ZIP, CSV, Parquet, and `tmp_path`
  behavior;
- `perf`: a benchmark or a time, memory, or resource measurement, always
  opt-in.

`unit` and `integration` are mutually exclusive. The structural checker
`scripts/check_test_quality.py` rejects tests with no tier or with more than
one tier.
It is a structural heuristic: it checks classification and an accepted
observation in the test's direct executable body without descending into nested
helpers, lambdas, or classes. It does not replace review that an assertion
protects a regression or prove the absence of every semantic tautology.

The `slow`, `asyncio`, and `real_data` markers are orthogonal qualifiers:

- `slow` identifies heavy or time-sensitive work;
- `asyncio` identifies a test that needs the async plugin;
- `real_data` identifies caller-owned COTAHIST input and may only accompany
  the `integration` tier.

The deterministic default gate is:

```bash
uv run --locked --no-sync pytest -m "not slow and not real_data and not perf" \
  --cov --cov-report=xml --cov-report=term-missing
```

Repository-created integrations stay in this gate when they are neither
`slow` nor `real_data`. Performance and real-data suites are outside the
default gate:

```bash
uv run --locked --no-sync pytest -m unit
uv run --locked --no-sync pytest -m "integration and not slow and not real_data and not perf"
uv run --locked --no-sync pytest tests/perf -m perf -o addopts=''
```

## Local COTAHIST

The directory configured in `COTAHIST_PATH` is always caller-owned.
`cotahist_b3_local/` is ignored by Git and is never downloaded by the suite.
The two versioned synthetic samples in `cotahist_b3/` belong to the examples
and deterministic validation under `tests/examples`, without `real_data`. The
fixture in
`tests/brazil/b3_data/historical_quotes/conftest.py`, consumed by
`integration/test_real_cotahist.py`, enforces these rules:

1. Without `COTAHIST_PATH`, only the suite explicitly selected with
   `-m real_data` is skipped, with an actionable instruction. The default gate
   does not select it.
2. With `COTAHIST_PATH`, a missing, unreadable, empty path, a path without a
   valid `COTAHIST_A{YYYY}.ZIP` or `COTAHIST_A{YYYY}.TXT`, or a missing selected
   year fails; it does not skip.
3. When present, `COTAHIST_TEST_YEAR` must contain exactly four digits. When
   absent, the fixture infers a year only when the catalog contains one year;
   with multiple years it fails with an actionable instruction and never picks
   the largest year.
4. Extraction receives the resolved year explicitly. It never uses the
   system's current year and never downloads data during the test.
5. In the current implementation, the catalog fully preflights every available
   file: years, ZIP limits, members, hashes, and every record. This setup also
   runs with `real_data and not slow`; that selection avoids Parquet extraction
   but does not guarantee a short source read.
6. Limited parity derives a non-empty sample of up to 20,000 real `01` records
   in `tmp_path` and compares `fast` and `slow` across all 32 Arrow fields with
   exact types and values. Because it runs both modes, it is marked `slow`.
7. An annual `fast` proof validates the Arrow schema, record count, and date
   bounds. Another annual `slow` proof compares counts, schema, and table
   equality or a logical digest between `fast` and `slow`.

Run the catalog check and processing proofs with:

```bash
COTAHIST_PATH=./cotahist_b3_local COTAHIST_TEST_YEAR=2000 \
  uv run --locked --no-sync pytest -m "real_data and not slow"
COTAHIST_PATH=./cotahist_b3_local COTAHIST_TEST_YEAR=2000 \
  uv run --locked --no-sync pytest -m "real_data and slow"
COTAHIST_PATH=./cotahist_b3_local COTAHIST_TEST_YEAR=2024 \
  uv run --locked --no-sync pytest -m "real_data and not slow"
COTAHIST_PATH=./cotahist_b3_local COTAHIST_TEST_YEAR=2024 \
  uv run --locked --no-sync pytest -m "real_data and slow"
```

## Official-data trigger

A future official annual sample becomes mandatory in CI only after an explicit
release decision provides a repository-versioned fixture or a published CI
artifact under a compatible license. Until that trigger exists, official data
remain opt-in and caller-owned. Mandatory adoption must update provenance and
licensing, the expected schema, the CI fixture, the corresponding job, and
this decision together.

## Consequences and non-goals

This decision makes test selection predictable, keeps CI deterministic, and
allows parity validation without placing external financial data in Git. The
persisted COTAHIST v2 contract with 32 fields is defined by the PyArrow
integrity cutover decision; this decision keeps official data opt-in and
caller-owned.
