# Migration 0.2.0: PyArrow and ingestion integrity

Version `0.2.0` moves production ingestion paths to PyArrow, removes Polars
from library dependencies, and strengthens CVM and B3 integrity guarantees. The
three root public facades and their signatures remain stable:

```python
from globaldatafinance import (
    ExtractionResultB3,
    FundamentalStocksDataCVM,
    HistoricalQuotesB3,
)
```

## Consumer-facing changes

| Change | Required action |
| --- | --- |
| Strict B3 parser | Correct the source file or handle `ExtractionError`; invalid values no longer fall back to zero, an empty string, or null. |
| Polars removed | Install Polars explicitly if the application uses it to read Parquet. |
| `ExtractorAdapter.extract_csv_from_zip_to_parquet` removed | Migrate internal use to the CVM facade or another appropriate public interface. |
| Pandas metadata removed | Do not depend on physical `b'pandas'` metadata; use logical schemas and values. |
| Fully filtered B3 input | Treat an empty Parquet as a valid result when TPMERC filtering finds no assets. |
| Canonical archive namespace | Use `Settings.archive`; `Settings.archive_safety` no longer exists and has no compatibility alias. |
| Strict logging configuration | Use only documented `LoggingSettings` fields and environment variables; `LoggingSettings(structured=True)` and unknown `DATAFIN_LOG_*` variables now raise `ValidationError`. |
| Logging destination and context | Use a `log_file` under an application-approved directory; roots/protected directories are rejected, and common secret fields receive best-effort redaction. Do not send secrets to logging. |
| Exact CVM preservation | Regenerate Parquets as `exact-text-v1`; all columns are strings and numeric conversions are explicit. |
| B3 internal clean cut | Remove `data_writer` from integrations constructing `ExtractionServiceB3` and do not pass `resource_monitor` to `ParquetWriterB3`; use the current facades and signatures. |
| Reserved B3 sentinel | The literal `__GLOBALDATAFINANCE_NULL__` is not accepted as a value; use `None` for nulls. |

## CVM

The current CVM contract is `exact-text-v1`: string columns, empty fields as
`""`, original values preserved, and ZIP retention after extraction.
`QUOTE_NONE` keeps literal quotes and short rows receive trailing empty fields.
Multi-Parquet publication remains recoverable as a batch, with all records
verified before promotion. See the [CVM exact text migration](migration-cvm-exact-text.en.md)
for regeneration, explicit conversions, and lock inspection after interruption.

Library logging does not alter the application root logger. Before an explicit
`setup_logging()` call, the `globaldatafinance` namespace uses a `NullHandler`
and remains quiet; a handler reconfiguration failure preserves the previous
configuration.

## B3

### Notes for release 0.2.0

The text below is the prepared body for the 0.2.0 GitHub release. The
existing `.github/workflows/publish.yml` runs gates and publication from the
published-release event. Version, tag, and publication must await approval of
the acceptance evidence; this draft does not claim a release was published.

**Breaking COTAHIST contract changes:**

- The default selection now preserves every type-`01` quotation, including
  TPMERC `021` and unknown numeric markets. Omit `assets_list` or use `todos`;
  specify classes when a consumer requires a filter.
- Parquet moves to versioned schema `2` with 32 columns. The original 20 fields
  retain their order and values; the 12 additions include the omitted official
  fields, provenance, and the original 245 quotation bytes.
- Regenerate v1 Parquets from the original ZIP/TXT sources. Append and merge
  across incompatible schemas fail; converting v1 files cannot recover missing
  data. Follow the cutover and rollback procedures on this page.
- Specify an available annual range: any missing requested year or invalid
  record fails extraction, including a record in a filtered-out market.
- Publication requires complete staged-output readback and exact data and
  manifest verification. Failures preserve the previous output; consumers must
  check `success`, `schema_version`, and `integrity` before switching files.

The local acceptance corpus covers 2000–2026, with a snapshot ending on
2026-09-02. The release must attach final frozen-corpus evidence and checksum
manifests. These bounds are not independent confirmation of exchange coverage
or availability of every historical year.

Every `01` record is validated and converted before market selection. Blank
lines and `00`/`99` controls are counted, while every other nonempty identifier
fails. Both modes use canonical conversion and bounded CSV row batches through
Arrow. `fast` uses batches of up to 25,000 records and can process sources in
parallel; `slow` uses batches of up to 10,000 records and one worker. Both
preserve the same logical schema, order, and values.

### B3 schema v2 and regeneration

The persisted COTAHIST contract changed incompatibly to versioned schema `2`.
The default is now `assets_list=None`, equivalent to `assets_list=["todos"]`:
all type-`01` quotations with numeric TPMERC codes are preserved, including
`021` and codes that are not yet known. The output has 32 columns, adding the
five previously omitted official fields, source coordinates, and the original
245 bytes of each quote. Financial values use exact decimals;
`preco_exercicio_pontos` has scale 6.

Version 1 Parquets do not contain TPMERC `021` rows, all official fields, or
original source bytes. Do not convert or append these files into v2. Regenerate
from the raw ZIP/TXT sources and validate the output before switching consumers.

Cutover procedure:

1. Preserve the COTAHIST sources and record their hashes.
2. Choose the annual range actually available. Pass `initial_year` and
   `last_year`; defaults still cover 1986 through the current year, and any gap
   inside the requested range fails extraction.
3. Write to a separate destination using `assets_list=["todos"]` (or omit
   `assets_list`).
4. Require `result["success"] is True` and `result["schema_version"] == 2`.
   Review `selection_complete`, `source_complete`, counts, selected years, and
   `output_sha256` in `result["integrity"]` for the consumer's requirements.
5. Read the Arrow schema and adapt consumers to the 12 added columns and exact
   types in the [B3 v2 schema reference](../reference/b3-schema-v2.en.md).
6. Switch consumers to the verified output and retain v1 files until the
   cutover is accepted.

Rollback procedure:

1. Keep the previous package version, consumer configuration, and v1 Parquet
   paths together until accepting the migration. Record the SHA-256 of each
   previous output and generate v2 in a separate directory.
2. If acceptance fails, restore the previous package version and consumer
   configuration to read the retained v1 paths. Leave the original COTAHIST and
   separate v2 artifacts available for diagnosis.
3. Verify the retained v1 checksums and reopen them with the previous consumer.
   Do not overwrite v2 with v1 or append rows between schema versions.

The library publishes one caller-selected output; changing the consumer's
chosen path belongs to the application. A failed extraction preserves the
previous file at that output path and returns `output_file=""`. These guarantees
are exercised by `tests/application/b3_docs/test_publication_integrity.py` and
`tests/application/b3_docs/test_schema_migration.py`.

A filtered v2 Parquet may contain zero rows and still be complete for the
requested selection; review `selection_complete`, `source_complete`, and
intentional-exclusion counts. `source_complete=True` requires zero exclusions.
Reports include outer and uncompressed-content hashes, Base64 controls, trailer
convention, observed dates, row digest, and final Parquet hash. These facts
attest the supplied files; they do not confirm a trading calendar or instruments
outside the corpus. Years before 2000 require separate source files and are not
included in the locally audited corpus.

Integrations that depended on removed internal objects must migrate to the
facade flow. The B3 session now has an explicit lifecycle (`NEW` → `OPEN` →
`CLOSED`) and cannot be reopened after closing, including when final
validation fails.

Internal workers use only the canonical `CotahistParserB3` conversion, including
source replay and digest verification for subclasses. Custom factories that
provided only `parse_line()` must implement the complete parser contract; the
alternative dictionary path was removed. The internal `normalize_decimal_v99`
helper and unused `ZipProcessingResult`/`ProcessSingleFileResult` types were
removed. Use `normalize_decimal` with an explicit scale in internal extensions.

Text-reading interfaces and `ParquetWriterB3` with existing callers remain
available over the current implementation. Module documentation lives in
`README.md` and `README.en.md`; the stale `README.pt.md` copy was removed.

## Dependencies and measurement

`ReadFilesAdapter` was removed together with the automatic Pandas dependency;
consumers who still want DataFrames must install Pandas themselves. PyArrow is
the only production CSV/Parquet engine. Use
`scripts/benchmark_ingestion.py` for local fresh-process measurements; its
numbers depend on hardware, environment, and corpus, so they are not universal
time or RSS guarantees. The complete timeout, generic adapter, B3 catch-boundary,
and write-failure migration is documented in [Infrastructure clean cut](migration-infrastructure-clean-cut.en.md).
