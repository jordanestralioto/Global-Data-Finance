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

## CVM

CVM CSV keeps `QUOTE_NONE`: quotes are literal text, not RFC quoting. Short
rows receive trailing nulls only, excess rows fail, and a header-only file
produces an empty Parquet. Publication of the several Parquets from one ZIP is
failure-atomic and recoverable through a manifest, staging, backup, and lock.
It does not provide instant atomic visibility of every filename to concurrent
readers.

## B3

Only selected `01` records are converted. Blank lines and `00`/`99` controls
are counted, while every other nonempty identifier fails. Extraction validates
width, dates, required texts, integers, and decimals before persistence. `fast`
and `slow` preserve the same logical schema, order, and values; they differ
only in concurrency and memory-pressure policy.

## Dependencies and measurement

Pandas remains installed for the public compatibility of `ReadFilesAdapter`,
with a deferred import. PyArrow is the only production CSV/Parquet engine. Use
`scripts/benchmark_ingestion.py` for local fresh-process measurements; its
numbers depend on hardware, environment, and corpus, so they are not universal
time or RSS guarantees.
