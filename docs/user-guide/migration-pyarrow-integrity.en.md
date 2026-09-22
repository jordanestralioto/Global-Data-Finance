# Major migration: PyArrow and ingestion integrity

This major version moves production ingestion paths to PyArrow, removes Polars
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
| Nullable CVM integers | A signed nullable column may be persisted as `int64`; do not depend on automatic promotion to `float64`. |
| B3 internal clean cut | Remove `data_writer` from integrations constructing `ExtractionServiceB3` and do not pass `resource_monitor` to `ParquetWriterB3`; use the current facades and signatures. |
| Reserved B3 sentinel | The literal `__GLOBALDATAFINANCE_NULL__` is not accepted as a value; use `None` for nulls. |

## CVM

CVM CSV keeps `QUOTE_NONE`: quotes are literal text, not RFC quoting. Short
rows receive trailing nulls only, excess rows fail, and a header-only file
produces an empty Parquet. Publication of the several Parquets from one ZIP is
failure-atomic and recoverable through a manifest, staging, backup, and lock.
It does not provide instant atomic visibility of every filename to concurrent
readers.

Library logging does not alter the application root logger. Before an explicit
`setup_logging()` call, the `globaldatafinance` namespace uses a `NullHandler`
and remains quiet; a handler reconfiguration failure preserves the previous
configuration.

## B3

Only selected `01` records are converted. Blank lines and `00`/`99` controls
are counted, while every other nonempty identifier fails. Extraction validates
width, dates, required texts, integers, and decimals before persistence. `fast`
and `slow` preserve the same logical schema, order, and values; they differ
only in concurrency and memory-pressure policy.

Integrations that depended on removed internal objects must migrate to the
facade flow. The B3 session now has an explicit lifecycle (`NEW` → `OPEN` →
`CLOSED`) and cannot be reopened after closing, including when final
validation fails.

## Dependencies and measurement

`ReadFilesAdapter` was removed together with the automatic Pandas dependency;
consumers who still want DataFrames must install Pandas themselves. PyArrow is
the only production CSV/Parquet engine. Use
`scripts/benchmark_ingestion.py` for local fresh-process measurements; its
numbers depend on hardware, environment, and corpus, so they are not universal
time or RSS guarantees. The complete timeout, generic adapter, B3 catch-boundary,
and write-failure migration is documented in [Infrastructure clean cut](migration-infrastructure-clean-cut.en.md).
