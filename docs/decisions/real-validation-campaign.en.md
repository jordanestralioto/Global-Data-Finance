# Auditable real-data validation campaign

**Status:** Accepted
**Date:** 2026-09-01
**Scope:** opt-in validation of external data and library artifacts

## Decision

Complete COTAHIST and CVM validation is executed by
`scripts/real_validation.py`, an opt-in development command outside the
library API. The executor is split into case-matrix construction, isolated
workers, source validators, and evidence persistence.

The command requires explicit paths. COTAHIST is always caller-owned and is
never downloaded; CVM contacts only the official endpoints in the matrix.
Reports, work artifacts, and CVM output must be outside the repository. The
campaign does not implicitly read `.env` and does not add financial data to
Git.

Each case uses the corresponding public facade (`HistoricalQuotesB3` or
`FundamentalStocksDataCVM`) as its only processing path. The worker validates
the input, executes the case, reads produced Parquet files with the real
engines, and checks schema, counts, minimum content, and cleanup. One process
per case limits leaked state and enables timeout with explicit classification.

The external report contains `manifest.json`, one current result per case in
`results.jsonl`, individual logs, artifact evidence, and `summary.json`.
Statuses are `passed`, `failed`, `skipped`, `external_failure`, and
`not_published`. Exit code zero is reserved for a fully classified campaign
with no failures, no pending external dependency, and no orphan-process
finding. `--resume` uses the existing manifest and reruns only external
failures or cases not yet executed.

Every `--report`, `--cvm-output`, and persisted `campaign.cvmOutput` from the
manifest passes through the shared sensitive-destination policy. The original
path text is retained so drive-relative, root-relative, and UNC semantics are
validated even on a POSIX host. Validation occurs before `mkdir`, `mkdtemp`, a
manifest, or an artifact. When resuming COTAHIST, the executor revalidates the
catalog, compares each input's size and SHA-256 with the manifest, and hashes
each shared path only once. Drift raises `ReportFormatError` with the
`caseId`, requires a new campaign, and leaves existing results neither rerun
nor overwritten.

Persisted results are caller-owned evidence, not a signed attestation. When a
pass/fail conclusion must serve as evidence, resume requires a trusted report
directory.

When resuming CVM, the executor first reads, normalizes, and validates
`campaign.cvmOutput` with the same policy. It then rebuilds every case from the
official document/year matrix and requires `caseId`, source, document, year,
mode, `inputPath`, `url`, and `outputRoot` to match the campaign destination
before a worker is created. A tampered `outputRoot` is rejected before
`mkdir`, `mkdtemp`, a worker, or an HTTP client. The publication probe uses only
the canonical HTTPS URL, does not follow redirects, and never writes the
response body. The compressed-ZIP limit is applied before a write from
`Content-Length`, when present, and by the facade stream counter.
The recorded size and SHA-256 are observed on the ZIP that the public facade
passes to extraction, rather than on a separately downloaded copy.

The executor scripts have deterministic coverage separate from `src`, with an
independent 85% floor in pre-push and in the quality pipeline.

## Consequences

This boundary keeps network access, large datasets, execution time, and
reports outside the library runtime. The matrix can prove real availability
without treating CVM or DNS unavailability as approval. The campaign is slower
than the deterministic suite and requires the caller to provide the COTAHIST
dataset and an external CVM output directory.

Detailed source rules remain owned by their source areas: COTAHIST cataloging
and member resolution belong to `brazil/b3_data/historical_quotes/`; CVM
download, extraction, and commit behavior belong to
`brazil/cvm/fundamental_stocks_data/`.
