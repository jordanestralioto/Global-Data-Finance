# Shared CVM archive ingestion

This package processes CVM archives compatible with `exact-text-v1`, without
depending on company document codes, URLs, or years.

## Components

| Component                                                      | Responsibility                                                    |
| -------------------------------------------------------------- | ----------------------------------------------------------------- |
| `http.py`                                                      | `CvmDownloadAdapter`: bounded downloads, retry, and finalization  |
| `extract.py`                                                   | `CvmParquetExtractor`: owned, transactional extraction            |
| `csv_pipeline/`                                                | Encoding, CSV records, text schema, and batch writing             |
| `source_inventory.py`                                          | Source identity and exact output inventory                        |
| `content_fingerprint.py`, `parquet_validation.py`              | Compare source records with persisted data                        |
| `destination_io.py`, `write_ownership.py`, `transaction_io.py` | Opened directories, exclusive writers, and transaction operations |
| `transaction.py`                                               | Coordinate shared recoverable publication                         |
| `models.py`                                                    | Result of a CVM download operation                                |

## Contract and dependencies

CSV uses `;` between fields, one record per physical line, and literal quotes.
All Parquet fields are `string`; empty values stay empty strings. The package
preserves ZIPs, basenames, `cvm.*` metadata, and complete verification before
publication. Arrow loads only when processing needs it.

The `core/` and `macro_infra/` foundations retain configuration, safety, HTTP,
temporary files, and transactional publication. The `.cvm-write-lock` protects
download and extraction with a lifecycle distinct from the publisher lock.

## Composition and output identity

Each family selects its catalog and periods outside this package and uses
`CvmDownloadAdapter` and `CvmParquetExtractor` directly. Results belong to
`ingestion.models.DownloadResultCVM`.

Automatic extraction checks the inventory and source identity before invoking
the extractor and again after it returns. Obsolete outputs identified by
`cvm.source-archive` metadata prevent the collaborator from running, preserving
existing outputs. A supplied extractor owns its writes and transaction; the
later check detects violations but does not undo arbitrary side effects.

Callers prepare destinations and follow the
[inventory contract](../../../../../docs/user-guide/migration-cvm-exact-text.en.md#output-inventory)
for existing files. The company facade validates and prepares destinations for
its operations.

## Validation

`tests/brazil/cvm/ingestion/` covers shared mechanics and reuse by an independent
synthetic family. Regressions preserve public facades and current data integrity.
An import contract forbids this package from depending on the company family.
See the [ownership decision](../../../../../docs/decisions/cvm-ingestion-ownership.en.md).
