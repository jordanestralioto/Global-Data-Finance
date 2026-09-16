# B3 Historical Quotes

Complete user documentation guide for employing the `HistoricalQuotesB3` API to parse and process official historical market exchange COTAHIST archives from B3 (Brazilian Stock Exchange).

## Overview

The `HistoricalQuotesB3` class provides a high-performance engine capable of ingesting official COTAHIST bundle archives from B3, extracting precise historical transactions across diverse market asset classes, and compiling them directly into columnar Apache Parquet storage.

### Highlights

- ✅ Targeted extraction spanning multiple exchange asset classes
- ✅ Dual processing engines (in-memory `fast` and incremental `slow` mode)
- ✅ Automatic structural type normalization into Apache Parquet
- ✅ Deep historical compatibility dating back to fiscal year **1986**
- ✅ Granular asset filtering syntax to exclude unnecessary instrument types
- ✅ Comprehensive execution tracking and diagnostic console outputs

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

> `ações` and `etf` are selection aliases in the COTAHIST parser sharing spot (010) and fractional (020) TPMERC codes.

BDRs and Futures are **Planned** and are not accepted by the current
`HistoricalQuotesB3` runtime contract. The Portuguese strings in the table are
canonical API values and must be passed exactly as shown.

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
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()

# Extract historical stock quotes from a closed historical year
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=2023,
)

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
    assets_list: list[str],
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
| `assets_list`      | `list[str]`   | ✅ Yes    | Selected asset filtering category strings                          |
| `initial_year`     | `int \| None` | ❌ No     | Starting historical year (default: 1986)                           |
| `last_year`        | `int \| None` | ❌ No     | Ending historical year (default: current system year)              |
| `destination_path` | `str \| None` | ❌ No     | Destination output directory (default: matches `path_of_docs`)     |
| `output_filename`  | `str`         | ❌ No     | Base filename of the target Parquet artifact; optional `.parquet` suffix       |
| `processing_mode`  | `str`         | ❌ No     | Execution concurrency profile: `"fast"` or `"slow"`                |
| `verbose`          | `bool`        | ❌ No     | When `True` (default), prints formatted console summary            |

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

For a selected COTAHIST input, `success=True` requires a generated Parquet
artifact, including when every type-`01` record is filtered by the requested
asset classes. That valid case produces zero rows with the explicit B3 schema.
An input with no type-`01` record remains invalid; a selected type-`01` record
with an invalid length, date, text, integer, or decimal fails with contextual
`ExtractionError` rather than turning an invalid financial value into zero or
null.

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

if result['success']:
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
# ['ações', 'etf', 'opções', 'termo', 'exercicio_opcoes', 'forward', 'leilao']
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

- **Performance Profile**: Maximum analytical speed
- **CPU Utilization**: Multi-core concurrent vectorization
- **RAM Allocation**: Higher in-memory footprint
- **Recommended Use**: Dedicated data processing servers and moderate-to-large analytical jobs

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

- **Performance Profile**: Moderated incremental throughput
- **CPU Utilization**: Low single-core processing
- **RAM Allocation**: Low stream memory consumption
- **Recommended Use**: Memory-constrained environments, shared hardware, or background cron processing

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

*Measured benchmark on complete annual dataset (general peak RAM ranges between ~2 GB to 4.2 GB in `fast` mode and ~500 MB to 1.5 GB in `slow` mode depending on dataset span and hardware).*

| Processing Profile | Measured Throughput | CPU Impact | Peak RAM (Benchmark) | Guidance                   |
| ------------------ | ------------------- | ---------- | -------------------- | -------------------------- |
| **fast**           | ~12,317 rows/s      | High       | ~4,260 MB            | ✅ Recommended Default     |
| **slow**           | ~8,557 rows/s       | Low        | ~1,571 MB            | Memory-Constrained Servers |

## Advanced Recipes & Implementations

### All Currently Supported Asset Categories

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()

# Dynamically fetch all currently supported asset categories
all_assets = b3.get_available_assets()

# Extract every currently supported category simultaneously
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=all_assets,
    initial_year=2023,
    output_filename="complete_market_2023"
)

print(f"✓ Extracted {result['total_records']:,} rows spanning {len(all_assets)} supported categories")
```

### Year-by-Year Partitioned Ingestion

```python
from globaldatafinance import HistoricalQuotesB3
import os

b3 = HistoricalQuotesB3()
base_path = "/data/cotahist"
output_path = "/data/extracted_quotes"

# Process historical epochs individually to yield segregated Parquet files per year
for year in range(2020, 2024):
    output_file = f"equities_{year}"

    result = b3.extract(
        path_of_docs=base_path,
        destination_path=output_path,
        assets_list=["ações"],
        initial_year=year,
        last_year=year,
        output_filename=output_file
    )

    if result['success']:
        print(f"✓ {year}: {result['total_records']:,} transaction rows extracted")
    else:
        print(f"✗ {year}: Extraction exception detected")
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
| `EmptyDirectoryError` | Source folder lacks COTAHIST files        | Inspect folder contents prior to invocation    |
| `ExtractionError`     | Corruption detected in positional layout  | Verify COTAHIST file integrity                 |

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
TPMERC filtering happens before conversion of the remaining fields. Records
outside the filter are counted as filtered, while an invalid selected record
never yields a default financial value.

The literal `__GLOBALDATAFINANCE_NULL__` is reserved by the internal writer and
is rejected as input data in both records and canonical rows. Use `None` for a
null value. The internal session has `NEW`, `OPEN`, and `CLOSED` states; after
closing, including after a validation failure, it cannot be reopened.

## Extracted Parquet Schema

### Consolidated Column Architecture

The resulting consolidated Parquet file surfaces the following structured schema:

| Column Name            | Data Type | Description                                    |
| ---------------------- | --------- | ---------------------------------------------- |
| `data_pregao`          | `date`    | Trading session calendar date                  |
| `codigo_bdi`           | `string`  | BDI market execution classification code       |
| `ticker`               | `string`  | Instrument symbol / ticker (e.g., PETR4)       |
| `tipo_mercado`         | `string`  | Market clearing segment code                   |
| `nome_resumido`        | `string`  | Corporate issuer short name                    |
| `especificacao_papel`  | `string`  | Security equity specification (e.g., ON, PN)   |
| `preco_abertura`       | `decimal` | Session open trading price                     |
| `preco_maximo`         | `decimal` | Session intraday maximum price                 |
| `preco_minimo`         | `decimal` | Session intraday minimum price                 |
| `preco_medio`          | `decimal` | Volume-weighted intraday average price         |
| `preco_fechamento`     | `decimal` | Session closing execution price                |
| `melhor_oferta_compra` | `decimal` | Highest bid quotation at session close         |
| `melhor_oferta_venda`  | `decimal` | Lowest ask quotation at session close          |
| `numero_negocios`      | `int`     | Cumulative quantity of trade executions        |
| `quantidade_total`     | `int`     | Cumulative quantity of traded contracts/shares |
| `volume_total`         | `decimal` | Total monetary session trading turnover        |
| `data_vencimento`      | `date`    | Contract expiration maturity date              |
| `fator_cotacao`        | `int`     | Price quotation lot scaling factor             |
| `codigo_isin`          | `string`  | International Securities Identification Number |
| `numero_distribuicao`  | `int`     | Corporate action distribution sequence number  |

### Reading

Use `pandas.read_parquet()` to load a complete table. For memory-bounded work,
use `pyarrow.parquet.ParquetFile(...).iter_batches()` with
`batch_size=200_000`; PyArrow is the production engine, while Pandas remains
for the legacy CSV adapter contract.

## Best Practices

### 1. Harness Fast Mode for Extensive Datasets

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
# ✅ Highly recommended for processing extensive historical ranges
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=1986,  # Complete historical depth
    processing_mode="fast",
)
```

### 2. Segment Output Files by Asset Category

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
# ✅ Recommended: generate segmented parquet artifacts per asset category
for asset in ["ações", "etf", "opções"]:
    result = b3.extract(
        path_of_docs="/data/cotahist",
        assets_list=[asset],
        initial_year=2023,
        output_filename=f"{asset}_2023",
    )
```

### 3. Monitor Free Filesystem Capacity

```python
import shutil

stats = shutil.disk_usage("/data")
free_gb = stats.free / (1024**3)

if free_gb < 5:
    print(f"⚠️  Low storage detected: {free_gb:.2f} GB available")
    # Toggle processing_mode="slow" or process narrowed annual chunks
else:
    pass
```

## Next Steps

- 📄 **[CVM Documents](cvm-docs.md)** - Guide to downloading CVM regulatory financial statements
- 💻 **[Practical Examples](examples.md)** - Explore actionable quantitative analytics workflows
- 🔧 **[API Reference](../reference/b3-api.md)** - Review comprehensive structural API definitions
- ❓ **[FAQ](faq.md)** - Answers to common installation and architectural inquiries

!!! tip "Analytical Best Practice"
    For large analysis jobs, consume Parquet in PyArrow batches to bound memory.
    Polars can be installed separately by consumers who prefer it as a
    downstream reader.
