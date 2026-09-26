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
`cotahist_b3/` is ignored by Git and is never downloaded by the suite. The
fixture in
`tests/brazil/b3_data/historical_quotes/integration/test_real_cotahist.py`
enforces these rules:

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
5. The catalog inspects every available external file, its years, central
   directories, ZIP limits, and internal-member resolution without processing
   all records in every file.
6. Limited parity derives a non-empty sample of up to 20,000 real `01` records
   in `tmp_path` and compares `fast` and `slow` on all 20 columns, exact dtypes,
   and deterministic ordering. Because it runs both modes, it is marked
   `slow`.
7. An annual `fast` proof validates the Arrow schema, record count, and date
   bounds. Another annual `slow` proof compares counts, schema, and table
   equality or a logical digest between `fast` and `slow`.

Run the catalog check and processing proofs with:

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

## Official-data trigger

A future official annual sample becomes mandatory in CI only after an explicit
release decision provides a repository-versioned fixture or a published CI
artifact under a compatible license. Until that trigger exists, official data
remain opt-in and caller-owned. Mandatory adoption must update provenance and
licensing, the expected schema, the CI fixture, the corresponding job, and
this decision together.

## Consequences and non-goals

This decision makes test selection predictable, keeps CI deterministic, and
allows parity validation without placing external financial data in Git. It
does not change the public API, facade signatures, extraction semantics,
output names, or persisted schema of the library.
