# ADR: shared infrastructure clean cut

## Status

Accepted

## Context

- The repository retained generic ZIP/CSV adapters with no active owning
  contract, duplicated destination preparation in CVM and B3, and duplicated
  temporary-file reservation.
- Pandas remained a runtime dependency only for the legacy CSV reader, although
  the productive CVM/B3 pipelines already use PyArrow.
- CVM and B3 have different formats, year floors, diagnostics, and ownership.
- This is a deliberate breaking release. Root facades, Parquet schemas, output
  names, and transactional publication must remain stable.
- Dominant attributes: data correctness, path safety, changeability, failure
  traceability, and low operational cost.

## Decision

Extract only true invariants: destination normalization/preparation in
`core.utils.destination_paths` and same-directory temporary reservation in
`macro_infra.temporary_files`. CVM and B3 retain ownership of orchestration,
year validation, formats, and source-specific messages.

`ExtractorAdapter`, `ReadFilesAdapter`, their modules, and the direct Pandas
dependency are removed without an alias, warning, shim, or fallback.
`DownloadTimeoutError` replaces the old custom timeout class. `B3Error` is a
B3-only domain base; no `GlobalDataFinanceError` or other global catch-all base
will be introduced. CVM staged filesystem write failures become
`ParquetWriteError`, except `ENOSPC`, which remains `DiskFullError`.

There is no OpenSpec change: this is a release and accepted-contract cleanup,
not a new shared specification lifecycle.

## Alternatives considered

- **Keep local helpers and legacy adapters:** rejected because it preserves
  divergence, an unnecessary runtime dependency, and an unowned surface.
- **Force CVM and B3 into one extractor/year validator:** rejected because it
  mixes source rules, year floors, diagnostics, and responsibilities.
- **Extract only invariant primitives and hard-cut obsolete adapters:** chosen
  because it removes duplication without inventing a domain abstraction while
  preserving same-filesystem publication.

## Consequences

### Positive

- One internal contract normalizes and prepares destinations, checks safety
  before `mkdir`, and revalidates after creation.
- One temporary reservation mechanism keeps `.part` and `.parquet.tmp` suffixes
  and cleans only the file created by the current call.
- Fewer dependencies and no automatic Pandas installation.
- Explicit B3 catch boundary without polluting the global hierarchy; CVM write
  failures distinguish infrastructure from source-content failures.

### Negative and mitigation

- Consumers of the old adapters or timeout class break immediately; the
  migration guide provides before/after imports and source-owned alternatives.
- Consumers who need DataFrames must install Pandas; PyArrow is the documented
  default, and real artifact tests cover schemas and values.
- The shared helpers become internal cross-owner contracts; direct unit tests
  cover races, chained causes, temporary files, and permissions.

## Migration/rollback note

Migration is a single next-major-release cut: replace the timeout import, remove
generic adapter imports, and declare Pandas in the consumer project when needed.
Incremental compatibility is intentionally absent. Reverting requires restoring
the modules, tests, dependency, and lockfile together; restoring only an alias
would recreate a partial and ambiguous contract.

## Revisit trigger

Revisit when a third source needs source-independent destination preparation or
sibling temporary files with different semantics. Evaluate a new source-owned
boundary then; do not extend these helpers with CVM- or B3-specific rules.
