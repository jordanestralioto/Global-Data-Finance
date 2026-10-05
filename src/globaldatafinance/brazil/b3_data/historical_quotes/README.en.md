# B3 historical quotations

This directory owns COTAHIST discovery, validation, and transformation. The
public API is the `HistoricalQuotesB3` facade in `application/`.

## Responsibilities

| Module or package                                                   | Responsibility                                                                     |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `catalog.py`                                                        | Shared annual catalog, complete validation, ZIP/TXT equivalence, and missing years |
| `source_validation/`                                                | Record order, controls, counts, and immutable source facts                         |
| `layout.py`                                                         | Fields, offsets, and conversions for schema v2                                     |
| `cotahist_parser/`                                                  | Exact conversion of all fields before market selection                             |
| `assets.py`                                                         | Aliases and TPMERC codes; `todos` preserves unknown numeric codes                  |
| `zip_reader.py`, `member_resolver.py`                               | Bounded ZIP/TXT reading and safe annual member resolution                          |
| `extraction_service/`                                               | Scheduling, workers, transient retries, merge, and transactional publication       |
| `parquet_writer/`                                                   | Arrow schema, bounded writing, and complete private artifact verification          |
| `source_evidence.py`, `integrity_report.py`                         | Shared evidence for the footer and public result                                   |
| `row_digest.py`                                                     | Ordered digest of logical values and selected occurrences                          |
| `client.py`, `models.py`                                            | Use cases and prepared configuration                                               |
| `filesystem.py`, `input_validation.py`, `years.py`, `processing.py` | Parameter, path, year, and processing mode validation                              |

Default extraction selects all markets. Each document must contain a header
`00`, at least one valid quotation `01`, and a consistent trailer `99`. ZIP is
preferred only when both annual ZIP and TXT are fully valid and their
uncompressed contents are identical. Conflicting inputs fail before destination
creation.

External inputs use `COTAHIST_A{YEAR}.ZIP` or `COTAHIST_A{YEAR}.TXT`.
`DocsToExtractorB3` is a data object and does not validate direct construction.
`CreateDocsToExtractUseCaseB3` validates parameters and constructs prepared
configuration; `documents_to_download` contains resolved absolute paths.
`ações`, `etf`, and `opções` are asset classes selected through their aliases.

The `fast` and `slow` modes retain distinct batch and concurrency limits and the same
integrity validation. Full private Parquet readback verifies schema, metadata,
counts, provenance, original bytes, and digests before publication. Failures
return zero output counters and preserve the previous published result.

Every worker uses canonical conversion and verifies source replay and the
ordered digest, including when its factory returns a parser subclass. The
alternative path accepting only `parse_line()` was removed. Internal extensions
must implement the complete `CotahistParserB3` contract.

`iter_lines()`, `read_lines_from_zip()`, and `ParquetWriterB3` remain available
to their existing callers. Text reading derives from the original bytes;
writing uses the same Arrow sessions and current schema. These interfaces do
not retain an alternative production parser or engine.

Inputs must remain unchanged during execution. Final checksum verification and
publication run in the same worker, with a cancellation checkpoint before the
publication decision. Verification does not lock changes by external processes.
The API reference contains the details.

## Contracts and validation

- [B3 API](../../../../../docs/reference/b3-api.en.md)
- [Schema v2](../../../../../docs/reference/b3-schema-v2.en.md)
- [Migration guide](../../../../../docs/user-guide/migration-pyarrow-integrity.en.md)
- [Testing and real campaigns](../../../../../docs/dev-guide/testing.en.md)

Tests mirror this owner under `tests/brazil/b3_data/historical_quotes/`. The
independent oracle in `scripts/cotahist_oracle/` defines its own offsets,
conversions, and types; the native `scripts/real_validation.py` campaign compares
each original occurrence with Parquet and checks exact parity between modes.
