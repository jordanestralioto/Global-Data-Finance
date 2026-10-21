# B3 operational practices

Guidance for processing local `COTAHIST_A{YYYY}.ZIP` or
`COTAHIST_A{YYYY}.TXT` files and consuming Parquet output. The API accepts ZIP
and TXT; see the [B3 guide](b3-docs.md) for input preparation.

## Plan the year range and resources

Set both ends of the range: every requested year must have a valid source.
An omitted final year uses the current year; an omitted initial year requests
from 1986 onward. Extraction does not download missing sources.

`fast` allows concurrent sources within CPU, memory, and file-count limits.
`slow` uses one source worker and smaller batches. Both modes validate the
same data and publish the same schema. [COTAHIST measurements](../dev-guide/cotahist-performance.md)
identify the corpus and environment for each comparison.

## Separate markets when needed

`ações` and `etf` are aliases for the same TPMERC codes, `010` and `020`.
Writing a file for each alias duplicates that selection; the filter does not
distinguish stocks from ETFs within these markets. Consumers need an external
registry to separate instruments. The example below separates the cash and
fractional markets from options markets, using explicit year ranges:

```python
from globaldatafinance import HistoricalQuotesB3


def main() -> None:
    b3 = HistoricalQuotesB3()
    for asset, filename in [("ações", "cash_2023"), ("opções", "options_2023")]:
        result = b3.extract(
            path_of_docs="./cotahist_b3",
            assets_list=[asset],
            initial_year=2023,
            last_year=2023,
            output_filename=filename,
            processing_mode="fast",
        )
        if not result["success"]:
            raise RuntimeError(result["errors"] or result["message"])
        print(result["output_file"])


if __name__ == "__main__":
    main()
```

## Reserve space for temporary files and publication

Storage must cover the inputs, per-source temporary Parquets, and consolidated
output; recoverable publication also preserves previous output when it exists.
Required capacity depends on the data and compression. Check the destination
filesystem and reduce the requested range when necessary. `slow` limits
concurrency and memory; it does not reduce the requested data or the space
used by the corresponding artifacts.

```python
import shutil

free_bytes = shutil.disk_usage("./cotahist_b3").free
print(f"Available storage: {free_bytes / 1024**3:.2f} GiB")
```

## Read output in batches

Check the result before opening its output file. For analysis that does not
need the whole table in memory, use PyArrow batches and choose a suitable
`batch_size`:

```python
import pyarrow.parquet as pq

for batch in pq.ParquetFile("./cotahist_b3/cash_2023.parquet").iter_batches(
    batch_size=200_000
):
    print(batch.num_rows)
```

Polars and pandas are optional readers installed separately by the consumer.
See the [B3 API](../reference/b3-api.md), [v2 schema](../reference/b3-schema-v2.md),
[examples](examples.md), and [FAQ](faq.md).
