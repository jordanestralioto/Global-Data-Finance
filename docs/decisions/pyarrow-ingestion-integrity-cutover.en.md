# PyArrow ingestion and transactional-integrity cutover

**Status:** Accepted
**Date:** 2026-09-10
**Scope:** CVM and B3 extraction, Parquet publication, and runtime imports
**Decisions:** Q1, Q2, Q3, Q4

## Context

The package loaded ingestion engines during import globaldatafinance, including
for consumers that only queried the API. The CVM path inferred types per chunk
and could encounter a decimal after fixing a column as an integer. The B3 path
retained large dictionary buffers, rewrote Parquet during append, and accepted
some invalid financial fields with silent defaults.

The existing CVM commit reduces the chance of a partially published batch but
does not preserve a durable manifest or automatically recover an interruption
between backups and replacements. That compromises financial-artifact integrity
and recovery.

## Decision

### Q1 — Source-owned PyArrow pipelines

Productive CVM and B3 pipelines remain independent and use PyArrow for Parquet
reading, conversion, and writing. CVM preserves its QUOTE_NONE CSV dialect; B3
uses a strict fixed-width parser. The sources do not share inference, parsing,
financial schemas, or filter rules.

Keeping only lazy imports around the existing pipelines was rejected because it
does not correct local CVM inference, B3 buffering, or permissive parsing. A
single generic framework was also rejected because the sources own different
formats, lifecycles, and diagnostics.

### Q2 — Runtime imports and dependencies

Polars will be removed from runtime, the lockfile, tests, and scripts. PyArrow
is the sole productive engine and loads only in the first operational path that
needs it. Pandas remains mandatory only for the legacy ReadFilesAdapter
contract, with a local import in reader methods.

Public facades and __init__.py files remain lightweight. Constructing a facade,
querying B3 assets/years, or downloading CVM without extraction must not load
pandas, NumPy, PyArrow, or Polars. The three root exports and public signatures
remain unchanged.

### Q3 — Recoverable, failure-atomic publication

The internal macro_infra/transactional_publication/ facility provides
same-filesystem staging, durable JSON manifests, directory locks,
hard-link-or-copy backups, rollback, and recovery on the next call. It knows
artifacts and paths only; it does not know source fields, schemas, filters, or
formats.

The manifest records OPEN, VALIDATED, BACKUPS_READY, PUBLISHING, COMMITTED,
CLEANUP_PENDING, ROLLING_BACK, and ROLLED_BACK. Every manifest path remains
below the destination or staging area. A concurrent write to the same
destination is rejected; a lock from another host or a live process is never
removed merely because it is old.

The resulting contract is recoverable, failure-atomic batch commit. It does not
offer instantly atomic visibility to concurrent readers of multiple CVM
Parquets because multiple names cannot be replaced by one operation.

### Q4 — Per-source integrity rules

CVM performs a global text validation/inference pass followed by a second pass
with an explicit schema. Short rows are padded at the end only; extra rows,
missing headers, and ambiguous structures fail without publishing. A
header-only CSV produces an empty Parquet with null fields, header order, and
no pandas metadata.

B3 accepts only blank, 00, 99, and exactly 245-character 01 records. Records
selected by TPMERC must have valid dates, text, integers, and decimals; invalid
values never become zero, an empty string, or null. Records outside the filter
are counted but not persisted. Fully filtered valid sources publish an empty
Parquet with the explicit B3 schema.

## Consequences

- This is a major release: strict B3 parsing, Polars removal, and removal of
  the internal legacy CSV path can require consumer migration.
- CVM can reopen a source for multiple passes and create a transactional UTF-8
  spool for CP1252 or Latin-1.
- Publication now needs staging, manifests, backups, locks, and fsync where the
  platform supports it.
- Fast and slow B3 retain logical equivalence but can use different memory and
  concurrency limits.
- Input ZIPs and TXTs are never removed on failure; only transaction-derived
  artifacts can be cleaned up.

## Non-goals

- Do not change root exports, signatures, defaults, output names, logical
  schemas, or the Parquet format.
- Do not add a service, queue, external process, web framework, or feature flag.
- Do not support RFC quoted/multiline CSV alongside QUOTE_NONE in this cutover.
- Do not retain a productive pandas/Polars fallback pipeline.
- Do not make the annual COTAHIST corpus mandatory in CI before a licensed
  fixture exists.
- Do not promise serializable isolation to concurrent CVM batch readers.
