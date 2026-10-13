# B3 Historical Quotes

Complete user documentation guide for employing the `HistoricalQuotesB3` API to parse and process official historical market exchange COTAHIST archives from B3 (Brazilian Stock Exchange).

## Overview

The `HistoricalQuotesB3` class provides a high-performance engine capable of ingesting official COTAHIST bundle archives from B3, extracting precise historical transactions across diverse market asset classes, and compiling them directly into columnar Apache Parquet storage.

### Highlights

- ✅ Targeted extraction spanning multiple exchange asset classes
- ✅ Processing modes with different batch and concurrency limits
- ✅ Automatic structural type normalization into Apache Parquet
- ✅ Deep historical compatibility dating back to fiscal year **1986**
- ✅ Granular asset filtering syntax to exclude unnecessary instrument types
- ✅ File progress bars during validation and processing

## Supported Asset Categories

B3 archives historical financial transactions under the following standard categories:

| Parameter Keyword    | Professional Classification  | Included TPMERC Codes                         |
| -------------------- | ---------------------------- | --------------------------------------------- |
| **ações**            | Stocks & Equities            | Spot market (010) and fractional market (020) |
| **etf**              | Exchange Traded Funds (ETFs) | Spot market (010) and fractional market (020) |
| **opções**           | Options Contracts            | Option Calls (070) and Option Puts (080)      |
| **termo**            | Term-market contracts        | Term financial agreements (030)               |
| **exercicio_opcoes** | Option Exercises             | Option Exercise Calls (012) and Puts (013)    |
| **forward**          | Forward Contracts            | Forward c/ Gain (050) and Movement (060)      |
| **leilao**           | Auction Market Records       | Auction clearing executions (017)             |
| **lote_bloco**       | Block lot                    | [BBT](https://www.b3.com.br/en_us/solutions/block-trading-solutions/book-of-block-trade-bbt/) and [Midpoint](https://www.b3.com.br/en_us/solutions/block-trading-solutions/midpoint-order-book/) (021) |
| **todos**            | Complete selection           | Every valid three-digit numeric TPMERC         |

> `ações` and `etf` are selection aliases in the COTAHIST parser sharing spot (010) and fractional (020) TPMERC codes.

BDRs and Futures are **Planned** and are not accepted by the current
`HistoricalQuotesB3` runtime contract. The `todos` selector also preserves
unknown numeric TPMERC codes and reports them as unknown. Portuguese strings
in the table are canonical API values and must be passed exactly as shown.

!!! info "Historical Depth"
    B3 COTAHIST historical quote archives cover market transaction activity continuously from **1986** through the present day.

## Basic Usage

Before calling `extract()`, place official `COTAHIST_A{YYYY}.ZIP` or
`COTAHIST_A{YYYY}.TXT` files in the existing `path_of_docs` directory; the
library does not download or populate it. Obtain files from the [official B3
Historical Quotes page](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/); ZIP takes precedence when both formats exist for one year.
A selected input must contain at least one type-`01` quote record; an empty
file or one containing only a header/trailer is not a valid extraction.

### Quickstart Example

```python
from pathlib import Path
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()

# Extract historical stock quotes from a closed historical year
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=2023,
    last_year=2023,
)

if not result['success']:
    raise SystemExit(result['errors'])
print(f"✓ Successfully processed {result['total_records']:,} transaction records")
```

## Core Public Methods

### `extract()`

Parses COTAHIST archives (ZIP bundles or plain positional TXT files) and exports filtered records into a unified Parquet file.

#### Method Signature

```python
def extract(
    self,
    path_of_docs: str,
    assets_list: list[str] | None = None,
    initial_year: int | None = None,
    last_year: int | None = None,
    destination_path: str | None = None,
    output_filename: str = "cotahist_extracted",
    processing_mode: str = "fast",
    verbose: bool = True,
) -> ExtractionResultB3:
    ...
```

#### Parameters

| Parameter          | Type          | Mandatory | Description                                                        |
| ------------------ | ------------- | --------- | ------------------------------------------------------------------ |
| `path_of_docs`     | `str`         | ✅ Yes    | Filesystem path pointing to raw COTAHIST archives (ZIP or TXT)     |
| `assets_list`      | `list[str] \| None` | ❌ No | `None` (`["todos"]`) | Asset classes; `"todos"` selects every valid numeric TPMERC |
| `initial_year`     | `int \| None` | ❌ No     | Starting historical year (default: 1986)                           |
| `last_year`        | `int \| None` | ❌ No     | Ending historical year (default: current system year)              |
| `destination_path` | `str \| None` | ❌ No     | Destination output directory (default: matches `path_of_docs`)     |
| `output_filename`  | `str`         | ❌ No     | Base filename of the target Parquet artifact; optional `.parquet` suffix       |
| `processing_mode`  | `str`         | ❌ No     | Execution concurrency profile: `"fast"` or `"slow"`                |
| `verbose`          | `bool`        | ❌ No     | When `True` (default), prints the final summary; progress bars also appear with `False` |

See the [progress and final summary](../reference/b3-api.en.md#extract) details.

#### Return Contract (`ExtractionResultB3`)

| Dictionary Key    | Type             | Description                                          |
| ----------------- | ---------------- | ---------------------------------------------------- |
| `success`         | `bool`           | `True` if extraction pipeline completed cleanly      |
| `message`         | `str`            | Human-readable summary of the execution outcome      |
| `total_files`     | `int`            | Total input files processed (ZIP or TXT)             |
| `success_count`   | `int`            | Number of input files successfully parsed and merged |
| `error_count`     | `int`            | Number of input files encountering format exceptions |
| `total_records`   | `int`            | Cumulative count of consolidated Parquet records     |
| `output_file`     | `str`            | Absolute filesystem path of the produced `.parquet`  |
| `errors`          | `dict[str, str]` | Dictionary mapping failed files to error messages    |
| `assets`          | `list[str]`      | Asset category strings included during extraction    |
| `processing_mode` | `str`            | Processing mode utilized (`"fast"` or `"slow"`)      |
| `elapsed_time`    | `float`          | Elapsed execution duration in seconds                |
| `schema_version`  | `int`            | Parquet schema version (`2`)                         |
| `integrity`       | `B3IntegrityReport` | Coverage, selection, source, verification, warning, and output-hash evidence |

`assets_list=None` is equivalent to `["todos"]`. This selector includes every
three-digit ASCII TPMERC, including unknown numeric codes, which are listed in
`integrity.unknown_market_counts`. `lote_bloco` selects `021`; `ações` and
`etf` remain selection aliases for `010` and `020`, and do not independently
classify an instrument's financial category. Overlapping aliases do not
duplicate source occurrences.

Every field in each `01` quote is validated before applying an asset filter.
Invalid TPMERC and malformed fields fail even when a quote would be excluded.
Blank lines and `00`/`99` controls are counted and omitted from the Parquet.
Only the two observed trailer totals are accepted: quote count plus two control
records, or quote count alone; the latter produces a structured warning.

`success=True` requires every requested year, validated sources, all selected
rows written and verified by a complete Parquet readback, and completed
publication. A missing year or incomplete verification fails without publishing
a new output. A valid filtered request may produce zero rows; the report
distinguishes `selection_complete` from `source_complete` and records intentional
exclusions. Results include input, uncompressed-content, and published-Parquet
hashes.

See [cleanup warnings and cancellation](../reference/b3-api.en.md).

The default year range remains 1986 through the current year. For a local
subset, pass its available year range explicitly. Real-data coverage describes
the files supplied and does not confirm dates outside them.

#### Usage Examples

**Example 1: Core Stock Extraction**

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=2022,
    last_year=2023,
)

if not result['success']:
    raise SystemExit(result['errors'])
print(f"✓ Generated Parquet file: {result['output_file']}")
print(f"✓ Total consolidated rows: {result['total_records']:,}")
```

**Example 2: Multi-Asset Ingestion**

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações", "etf", "opções"],
    initial_year=2020,
    last_year=2023,
    output_filename="multi_assets_2020_2023",
)
```

**Example 3: Low-Footprint Background Execution**

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=2023,
    processing_mode="slow",  # Minimizes active system memory footprint
)
```

**Example 4: Custom Export Routing**

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist_zips",
    destination_path="/data/processed_quotes",
    assets_list=["ações", "etf"],
    initial_year=2023,
    output_filename="stocks_etf_2023",
)
# Resulting artifact persisted at: /data/processed_quotes/stocks_etf_2023.parquet
```

### `get_available_assets()`

Returns an exhaustive list of valid asset string identifiers supported by the extraction filters.

#### Method Signature

```python
def get_available_assets(self) -> list[str]:
    ...
```

#### Return Value

A list containing permissible asset filtering strings.

#### Example Execution

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
assets = b3.get_available_assets()
# ['ações', 'etf', 'opções', 'termo', 'exercicio_opcoes', 'forward', 'leilao', 'lote_bloco', 'todos']
print(f"Available {len(assets)} asset classes")
```

### `get_available_years()`

Returns dictionary containing extreme boundaries of supported historical time horizons.

#### Method Signature

```python
def get_available_years(self) -> dict[str, int]:
    ...
```

#### Return Value

A dictionary detailing `minimal_year` (1986) and `current_year`.

#### Example Execution

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
years = b3.get_available_years()
# `current_year` is the current execution year.
print(f"B3 data from {years['minimal_year']} through {years['current_year']}")
```

## Processing Execution Modes

The extraction pipeline provides distinct computational operational modes:

### Fast Mode (Default) ⚡

Uses the canonical parser and Arrow writes in batches of up to 25,000 records.
It can process sources concurrently, bounded by CPU count, available memory,
and source file count; the default limit is four workers.

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    processing_mode="fast",  # Default configuration
)
```

### Slow Mode 🐢

Uses the same canonical parser and schema, with batches of up to 10,000 records
and one extraction worker. Both modes use bounded source reads and verify all
data before publication.

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    processing_mode="slow",
)
```

### Performance Benchmark Comparison

*Historical measurement of implementation v3: 27 files (2000–2026) and 22,303,577 records, excluding 2,283 TPMERC `021` quotations. It does not describe schema v2 and is not directly comparable. See the [benchmark details](../dev-guide/benchmarks.en.md).*

| Processing Profile | Measured Throughput | Measured Peak RSS | Default Parallelism                                          | Guidance                |
| ------------------ | ------------------- | ----------------- | ------------------------------------------------------------ | ----------------------- |
| **fast**           | 34,313.8 rows/s     | 429.88 MiB        | Up to 4 workers, bounded by CPU count, available memory, and source files | ✅ Prioritize throughput |
| **slow**           | 29,759.9 rows/s     | 331.11 MiB        | 1 worker                                                     | Reduce memory use       |

RSS and time depend on the workload; `fast` does not guarantee a shorter time
than `slow`. See [current measurements and conditions](../dev-guide/cotahist-performance.en.md).

## Advanced Recipes & Implementations

### Complete Market Selection

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()

# `todos` includes unknown numeric TPMERC codes as well as known categories
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["todos"],
    initial_year=2023,
    last_year=2023,
    output_filename="complete_market_2023"
)

if not result['success']:
    raise SystemExit(result['errors'])
print(f"✓ Extracted {result['total_records']:,} rows; unknown markets: {result['integrity']['unknown_market_counts']}")
```

### Year-by-Year Partitioned Ingestion

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
base_path = "/data/cotahist"
output_dir = "/data/extracted_quotes"

# Process historical epochs individually to yield segregated Parquet files per year
for year in range(2020, 2024):
    output_file = f"equities_{year}"

    result = b3.extract(
        path_of_docs=base_path,
        destination_path=output_dir,
        assets_list=["ações"],
        initial_year=year,
        last_year=year,
        output_filename=output_file
    )

    if not result['success']:
        raise SystemExit(result['errors'])
    print(f"✓ {year}: {result['total_records']:,} transaction rows extracted")
```

### Pre-Execution Integrity & Path Verification

```python
import os
import re
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
path_docs = "/data/cotahist"

# 1. Confirm source repository accessibility
if not os.path.exists(path_docs):
    print(f"✗ Target repository inaccessible: {path_docs}")
    exit(1)

# 2. Confirm COTAHIST naming contract presence (ZIP or TXT with 4-digit year)
pattern = re.compile(r"^COTAHIST_A\d{4}\.(?:ZIP|TXT)$", re.IGNORECASE)
files = [f for f in os.listdir(path_docs) if pattern.match(f)]
if not files:
    print(f"✗ Zero compliant COTAHIST archives found within {path_docs}")
    exit(1)

print(f"✓ Discovered {len(files)} COTAHIST candidate archives")

# 3. Validate requested asset list
requested_assets = ["ações", "etf"]
available_assets = b3.get_available_assets()
invalid_assets = [a for a in requested_assets if a not in available_assets]
if invalid_assets:
    print(f"✗ Discarding unverified asset strings: {invalid_assets} (valid: {available_assets})")
    exit(1)

# 4. Trigger extraction pipeline
result = b3.extract(
    path_of_docs=path_docs,
    assets_list=requested_assets,
    initial_year=2023
)
```

## Error Handling & Exceptions

### Custom Exception Hierarchy

| Exception Class       | Trigger Condition                         | Recommended Handling Pattern                   |
| --------------------- | ----------------------------------------- | ---------------------------------------------- |
| `EmptyAssetListError` | Provided `assets_list` parameter is empty | Supply at least one recognized asset string    |
| `InvalidAssetsName`   | An asset string falls outside whitelist   | Query valid terms via `get_available_assets()` |
| `InvalidFirstYear`    | `initial_year` parameter below 1986 floor | Specify temporal lower bounds >= 1986          |
| `InvalidLastYear`     | End year prior to start year              | Confirm monotonic temporal ordering            |
| `EmptyDirectoryError` | Input directory is physically empty     | Provide an existing directory with COTAHIST files |
| `ExtractionError`     | Corruption detected in positional layout  | Verify COTAHIST file integrity                 |

If any requested annual file is missing, the API returns `success=False`,
lists the gap in `integrity.missing_years`, and does not publish a new output.

## Official COTAHIST File Formats

### File Naming Contract

Official B3 archive downloads adhere to the standard pattern `COTAHIST_A{YYYY}.ZIP` (e.g., `COTAHIST_A2023.ZIP`), where `{YYYY}` denotes a four-digit fiscal year. The local scanner also supports raw uncompressed text files matching `COTAHIST_A{YYYY}.TXT`. If ZIP and TXT for the same year coexist, only ZIP is selected deterministically.

### Internal Archive Structure

Within each historical ZIP bundle sits a fixed-width positional ASCII text file:

```
COTAHIST_A2023.ZIP
└── COTAHIST_A2023.TXT  (Fixed-width positional historical transaction ledger)
```

Historical archives may also contain `COTAHIST.A{YYYY}` (for example,
`COTAHIST.A2000`) or the extensionless historical member `COTAHIST_A{YYYY}`
(for example, `COTAHIST_A2001`). The reader requires exactly one non-nested
candidate member whose internal year matches the external filename; missing,
ambiguous, or wrong-year members are rejected. Quote record `01` must be
exactly 245 characters, and fixed-width trailing spaces are preserved.
TXT inputs and a ZIP's selected member must contain at least one `01` record;
header/trailer-only content is rejected before parsing.

Before consuming a ZIP, the library validates its metadata and limits for size,
members, expansion, and compression. Global-Data-Finance processes accepted
layouts and converts them to Parquet; a structurally unsafe or corrupted
archive fails with `ExtractionError`/`CorruptedZipError` rather than yielding a
successful result.

The parser is strict: blank lines and official `00`/`99` controls are counted
only; a nonempty identifier other than `01`, `00`, or `99` aborts extraction.
Every field of every `01` quotation is validated before TPMERC filtering,
including quotations that will be excluded. Invalid data never yields a default
financial value.

The literal `__GLOBALDATAFINANCE_NULL__` is reserved by the internal writer and
is rejected as input data in both records and canonical rows. Use `None` for a
null value. The internal session has `NEW`, `OPEN`, and `CLOSED` states; after
closing, including after a validation failure, it cannot be reopened.

## Extracted Parquet Schema

The default schema is version `2`. The 20 historical fields keep their order;
v2 adds official fields, the record type, provenance, and original bytes. Every
field is required except `data_vencimento`. The footer carries the integrity
manifest and logical schema fingerprint.

See the [B3 v2 schema reference](../reference/b3-schema-v2.en.md) for the full
field list, data types, reading guidance, and provenance. Schema v1 files must
be regenerated from original COTAHIST sources using the
[v2 migration guide](migration-pyarrow-integrity.en.md#b3-schema-v2-and-regeneration).
For operational recommendations, partitioning, and artifact consumption, see
[B3 Operational Practices](b3-operations.en.md).
