# Migration: infrastructure clean cut

This major version removes obsolete generic APIs and the automatic Pandas
dependency. The root facades, public CVM/B3 signatures, output names, Parquet
schemas, and transactional publication semantics remain unchanged. The cut is
deliberately incompatible: no alias, warning, shim, or fallback is retained for
removed names.

## Download timeout

Before:

```text
from globaldatafinance.macro_exceptions import TimeoutError
```

After:

```python
from globaldatafinance.macro_exceptions import DownloadTimeoutError

try:
    download()
except DownloadTimeoutError:
    recover_or_report()
```

`DownloadTimeoutError` keeps the former `(doc_name, timeout=None)` constructor
and human-readable message format. The old name is no longer importable.
Python's built-in `TimeoutError` remains an internal transport failure handled
by the CVM adapter; it is not the domain exception.

## Removed generic adapters

`ExtractorAdapter` and `ReadFilesAdapter` are no longer part of
`globaldatafinance.macro_infra`. The modules
`globaldatafinance.macro_infra.extractor_file` and
`globaldatafinance.macro_infra.read_files` were removed.

Before:

```python
from globaldatafinance.macro_infra import ExtractorAdapter, ReadFilesAdapter
```

After, use the source boundary that owns the data contract:

```python
from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    ParquetExtractorAdapterCVM,
)

cvm_extractor = ParquetExtractorAdapterCVM()
convert_zip = cvm_extractor.extract
convert_zip('download.zip', 'cvm-output')
```

For B3 files, use the `HistoricalQuotesB3` facade and the source-owned
components documented in [B3 Historical Quotes](b3-docs.en.md). Do not recreate
a generic adapter for the removed modules: CVM and B3 have different format
rules, year floors, and diagnostics.

## Pandas is no longer installed automatically

The library runtime uses PyArrow for CSV and Parquet. A consumer that still
needs DataFrames must declare the dependency independently:

```bash
python -m pip install pandas
```

For the recommended memory-bounded reader, no additional package is needed:

```python
import pyarrow.parquet as pq

for batch in pq.ParquetFile('cotahist.parquet').iter_batches(
    batch_size=200_000
):
    consume(batch)
```

Pandas and Polars may still be used as optional downstream readers, but they are
not installed or imported by the package.

## B3 catch boundary

Concrete B3 exceptions preserve their own types and now inherit from `B3Error`:

```python
from globaldatafinance.brazil.b3_data.historical_quotes.errors import B3Error

try:
    run_b3_operation()
except B3Error as error:
    handle_b3_input_or_processing_error(error)
```

`B3Error` is source-local and is not exported from `globaldatafinance` or used
as a global base. Year policies remain separate: B3 still has its 1986 minimum,
and each source retains its own `InvalidFirstYear` and `InvalidLastYear`
classes.

## CVM Parquet write failures

Filesystem failures during staged Parquet creation, writing, closing, or
reopening are now `ParquetWriteError`, with the original cause preserved.
`ENOSPC` remains `DiskFullError`; CSV, Arrow, schema, row-count, corrupt-ZIP,
and combined rollback failures remain `ExtractionError` where that is the
appropriate contract.

Download aggregation records a recognized failure as:

```text
ParquetWrite: Failed to write Parquet file '...'
```

The source ZIP is retained for diagnosis. Consumers that previously treated all
`ExtractionError` values alike can catch `ParquetWriteError` explicitly when
they need to distinguish an infrastructure failure from bad source content.

## Destinations and internal temporary files

CVM and B3 share only invariant destination normalization and preparation. The
source owner remains responsible for creating directories, and the transactional
publisher does not create the destination. Downloads and Parquet writers reserve
hidden temporary files beside the destination so publication remains eligible
on the same filesystem.
