# CVM failure-atomic batch commit

**Status:** Accepted
**Date:** 2026-08-31
**Scope:** automatic CVM ZIP CSV-to-Parquet extraction

> **Partially superseded (2026-09-10):** the
> [PyArrow ingestion and transactional-integrity cutover](pyarrow-ingestion-integrity-cutover.en.md)
> retains the failure-atomic commitment, but replaces this CVM-local mechanism
> with shared publication backed by a durable manifest, lock, and recovery.

## Context

One CVM ZIP can generate multiple Parquet files in a caller-owned directory.
Writing directly to the destination lets a failure on the second CSV alter or
delete a Parquet that existed before the call. A temporary file for each output
prevents individual corruption, but still exposes a partially updated batch.

## Decision

`CvmFailureAtomicBatchCommit` is the internal module executing extraction. It:

1. validates the ZIP and lists every CSV before writing;
2. rejects ZIPs with no CSV and basename collisions before creating outputs;
3. creates a hidden staging area inside the destination directory so it stays
   on the same filesystem;
4. converts every CSV only in that area and validates staged Parquet size,
   footer, and rows;
5. backs up every pre-existing target before changing any target, preferring a
   hard link and falling back to metadata-preserving copy;
6. applies `os.replace()` in deterministic order;
7. on failure, removes new outputs and restores backups in reverse order;
8. removes staging and backups only after a complete commit or normal rollback.

If restoration itself fails, the recovery area is preserved and the
`ExtractionError` includes its path, the original failure, and the restore
failure. This avoids deleting the only recoverable copy and retains the
diagnostic cause.

## Consequences

- The contract is a **failure-atomic, recoverable batch commit**, not a
  multi-file transaction with instant atomic visibility.
- Concurrent readers and simultaneous writes to the same destination remain
  unsupported; the directory is caller-owned and may contain unrelated files,
  so it is never swapped as a whole.
- The public `ParquetExtractorAdapterCVM.extract(...)->None` signature, output
  names, and persisted schemas remain unchanged.
- CSV, disk, staged-validation, replace, and corrupted-ZIP failures preserve
  pre-existing Parquets whenever normal rollback completes.
