# ADR: CVM archive ingestion ownership

## Status

Accepted

## Context

Other CVM families need download, conversion, and publication without depending
on the company catalog. These mechanics know CVM CSV, ZIP, Parquet, and metadata
contracts; global foundations serve multiple sources.

## Decision

- `brazil/cvm/ingestion/` owns reusable mechanics. An import contract prevents
  dependencies on `fundamental_stocks_data/`.
- `fundamental_stocks_data/` owns company catalogs, URLs, years, and destinations.
  The facade composes `ingestion.http.CvmDownloadAdapter`; extraction uses
  `ingestion.extract.CvmParquetExtractor`, and results belong to
  `ingestion.models.DownloadResultCVM`.
- Configuration, safety, and transactional publication use their existing
  owners in `core/` and `macro_infra/`.
- Inventory associates outputs with their source through `cvm.source-archive`,
  without inferring ownership from Parquet filenames. The [inventory guide](../user-guide/migration-cvm-exact-text.en.md#output-inventory)
  defines replacement, preservation, and rejection of existing files.

## Alternatives considered

- Promoting the entire pipeline globally would spread CVM-specific contracts
  across other sources.
- Keeping mechanics under companies or copying them into each family would
  preserve coupling or duplication.
- Sharing within CVM separates these responsibilities and retains canonical
  owners without imposing common parsing or schemas on B3.

## Consequences

Compatible new families use the mechanics without consulting the company catalog.
The `exact-text-v1` contract, output names, and public signatures remain.
Integrating another family's official archives requires validating its format
and rules. This change does not add public support for FIIs.

Automatic extraction checks inventory before and after the collaborator; the
transaction checks direct extraction before publication. The default path scans
three times, with cost proportional to destination files. A supplied extractor
owns its writes and transaction; the later check does not undo arbitrary effects.

The `.cvm-write-lock` and publisher lock retain their lifecycles and concurrency
limits. Relocation does not expand those guarantees.

## Migration and rollback

Internal consumers use canonical `ingestion/` modules without aliases or
forwarding modules. Filename inference present in `develop` was removed before
reaching releases. Destinations with unidentified data require explicit
preparation as described in the inventory guide.

A rollback restores implementation, imports, and checkers together, retaining
one owner of writer state.

## Revisit triggers

Revisit when another source needs the same operations and guarantees, or a CVM
family requires a different dialect, schema, or publication lifecycle.
