# CVM Regulatory Documents

Comprehensive documentation guide for utilizing the `FundamentalStocksDataCVM` class to download corporate fundamental financial filings from CVM (Securities and Exchange Commission of Brazil).

______________________________________________________________________

## Overview

The `FundamentalStocksDataCVM` class exposes a clean, highly extensible interface designed to retrieve official filings directly from regulatory servers, including annual financial statements, quarterly disclosures, corporate governance forms, and reference reports of Brazilian public companies.

### Highlights

- ✅ Automated processing across diverse document types and categories
- ✅ Flexible temporal parameter boundaries
- ✅ Native automated conversion into columnar Apache Parquet files (optional)
- ✅ Concurrent asynchronous down-streaming (3–5x faster than linear requests)
- ✅ Resilient connection exception handling and automated retry policies
- ✅ Transparent structured tracking and status console output

______________________________________________________________________

## Available Document Types

CVM publishes official disclosures under the following classifications:

| Document Code | Complete Portuguese Title           | Description                                    | Available Since |
| ------------- | ----------------------------------- | ---------------------------------------------- | --------------- |
| **DFP**       | Demonstração Financeira Padronizada | Standardized Annual Financial Statements       | 2010            |
| **ITR**       | Informação Trimestral               | Quarterly Interim Financial Reports            | 2011            |
| **FRE**       | Formulário de Referência            | Complete Reference Form Disclosures            | 2010            |
| **FCA**       | Formulário Cadastral                | Corporate Cadastral Registration Forms         | 2010            |
| **CGVN**      | Código de Governança                | Corporate Governance Practices Reports         | 2018            |
| **VLMO**      | Valores Mobiliários                 | Securities Trading and Holding Declarations    | 2018            |
| **IPE**       | Informações Periódicas e Eventuais  | Periodic and Eventual Filings (Material Facts) | 2010            |

!!! info "Historical Data Depth"

    The major structural financial forms (`DFP`, `FRE`, `FCA`, `IPE`) span from fiscal year 2010 onward, while `ITR` disclosures start in 2011 and `CGVN`/`VLMO` commence in 2018.

______________________________________________________________________

## Basic Usage

### Library Import

```python
from globaldatafinance import FundamentalStocksDataCVM
```

### Instantiate Public Client

```python
cvm = FundamentalStocksDataCVM()
```

### Minimal Download Script

```python
# Download DFP archives covering the past 3 fiscal years
cvm.download(
    destination_path="/home/user/cvm_data",
    list_docs=["DFP"],
    initial_year=2021,
    last_year=2023
)
```

______________________________________________________________________

## Core Public Methods

### `download()`

Downloads regulatory CVM archives directly into a designated filesystem destination.

#### Method Signature

```python
def download(
    self,
    destination_path: str,
    list_docs: list[str] | None = None,
    initial_year: int | None = None,
    last_year: int | None = None,
    automatic_extractor: bool = False,
) -> DownloadResultCVM:
    ...
```

#### Parameters

| Parameter             | Type                | Mandatory | Description                                                                                |
| --------------------- | ------------------- | --------- | ------------------------------------------------------------------------------------------ |
| `destination_path`    | `str`               | ✅ Yes    | Target filesystem directory where downloaded bundles are saved                             |
| `list_docs`           | `list[str] \| None` | ❌ No     | Specific document codes to fetch. Defaults to all codes when `None`                        |
| `initial_year`        | `int \| None`       | ❌ No     | Starting historical fiscal year (inclusive). Defaults to minimal supported year            |
| `last_year`           | `int \| None`       | ❌ No     | Ending fiscal year (inclusive). Defaults to current operating year                         |
| `automatic_extractor` | `bool`              | ❌ No     | When set to `True`, automatically unpacks and normalizes ZIP bundles into Parquet datasets |

#### Return Value

Returns a `DownloadResultCVM` object with the following attributes and methods:

- `success_count_downloads: int` — Total number of successfully downloaded bundles.
- `error_count_downloads: int` — Total number of failed download tasks.
- `successful_downloads: list[str]` — List of completed document identifiers in `{DOC}_{YEAR}` format (e.g., `"DFP_2023"`).
- `failed_downloads: dict[str, str]` — Dictionary mapping failed items to error messages.
- `elapsed_time: float` — Total execution duration in seconds.
- `has_errors() -> bool` — Returns `True` if one or more downloads failed.

#### Usage Examples

**Example 1: Basic DFP Download**

```python
cvm = FundamentalStocksDataCVM()
cvm.download(
    destination_path="/data/cvm",
    list_docs=["DFP"],
    initial_year=2020,
    last_year=2023
)
```

**Example 2: Downloading Multiple Document Types**

```python
cvm.download(
    destination_path="/data/cvm",
    list_docs=["DFP", "ITR", "FRE"],
    initial_year=2022
)
```

**Example 3: Download with Automated Parquet Extraction**

```python
cvm.download(
    destination_path="/data/cvm",
    list_docs=["DFP"],
    initial_year=2022,
    automatic_extractor=True  # Automatically normalizes ZIP records directly into Apache Parquet
)
```

**Example 4: Full Spectrum Download**

```python
# Omitting list_docs retrieves every supported document category in parallel
cvm.download(
    destination_path="/data/cvm_complete",
    initial_year=2023
)
```

______________________________________________________________________

### `get_available_docs()`

Retrieves a mapped catalog containing all supported regulatory document types along with descriptive definitions.

#### Method Signature

```python
def get_available_docs(self) -> dict[str, str]:
    ...
```

#### Return Value

A dictionary mapping acronym document codes to their full professional titles.

#### Example Execution

```python
cvm = FundamentalStocksDataCVM()
docs = cvm.get_available_docs()

for code, description in docs.items():
    print(f"{code}: {description}")
```

**Console Output**:

```
DFP: Demonstração Financeira Padronizada
ITR: Informação Trimestral
FRE: Formulário de Referência
FCA: Formulário Cadastral
CGVN: Código de Governança
VLMO: Valores Mobiliários
IPE: Informações Periódicas e Eventuais
```

______________________________________________________________________

#### `get_available_years()`

Returns descriptive information detailing permissible temporal intervals across supported filings.

#### Method Signature

```python
def get_available_years(self) -> AvailableYearsInfoCVM:
    ...
```

#### Return Value (`AvailableYearsInfoCVM`)

A structural `NamedTuple` container describing historical floor boundaries:

| Attribute Name       | Type  | Description                                                  |
| -------------------- | ----- | ------------------------------------------------------------ |
| `general_min_year`   | `int` | Minimum historical starting year for general filings (2010)  |
| `itr_min_year`       | `int` | Minimum historical year for ITR quarterly disclosures (2011) |
| `cgvn_vlmo_min_year` | `int` | Minimum historical year for governance disclosures (2018)    |
| `current_year`       | `int` | Real-time operational system year                            |

#### Example Execution

```python
cvm = FundamentalStocksDataCVM()
years = cvm.get_available_years()

print(f"General disclosures available since: {years.general_min_year}")
print(f"Interim statements (ITR) available since: {years.itr_min_year}")
print(f"Active operating system year: {years.current_year}")
```

______________________________________________________________________

## Advanced Implementations

### Incremental Data Synchronizer

Execute selective historical synchronization to avoid re-downloading existing archives, respecting the partitioned directory hierarchy:

```python
import os
from globaldatafinance import FundamentalStocksDataCVM

cvm = FundamentalStocksDataCVM()
base_path = "/data/cvm"

# Inspect existing partitioned local storage subdirectories {base_path}/DFP/{YEAR}/
existing_years = set()
dfp_dir = os.path.join(base_path, "DFP")
if os.path.exists(dfp_dir):
    for entry in os.listdir(dfp_dir):
        if entry.isdigit() and os.path.isdir(os.path.join(dfp_dir, entry)):
            existing_years.add(int(entry))

# Download only missing historical fiscal periods
current_year = cvm.get_available_years().current_year
all_years = set(range(2020, current_year + 1))
missing_years = all_years - existing_years

if missing_years:
    min_year = min(missing_years)
    max_year = max(missing_years)

    cvm.download(
        destination_path=base_path,
        list_docs=["DFP"],
        initial_year=min_year,
        last_year=max_year
    )
```

### Pre-execution Input Validation

Validate parameters prior to initiating heavy network downloads:

```python
from globaldatafinance import FundamentalStocksDataCVM

cvm = FundamentalStocksDataCVM()

# Validate document parameter compliance
requested_docs = ["DFP", "ITR", "FRE"]
available_docs = cvm.get_available_docs()

valid_docs = [doc for doc in requested_docs if doc in available_docs]
invalid_docs = [doc for doc in requested_docs if doc not in available_docs]

if invalid_docs:
    print(f"⚠️  Discarding unsupported document strings: {invalid_docs}")
    print(f"✓ Authorized processing items: {valid_docs}")

# Safety guard: empty list would trigger downloading all documents
if not valid_docs:
    raise ValueError("No valid document codes provided.")

# Validate temporal input limits
years_info = cvm.get_available_years()
requested_year = 2015

if requested_year < years_info.general_min_year:
    print(f"⚠️  Requested fiscal period {requested_year} is prior to floor {years_info.general_min_year}")
else:
    # Trigger safe downstream extraction
    cvm.download(
        destination_path="/data/cvm",
        list_docs=valid_docs,
        initial_year=requested_year
    )
```

______________________________________________________________________

## Error Handling & Exceptions

### Synchronous Exceptions

The CVM module enforces fail-fast error behavior by validating parameters at public boundaries:

| Exception Class               | Trigger Condition                             | Recommended Handling Pattern                    |
| ----------------------------- | --------------------------------------------- | ----------------------------------------------- |
| `InvalidDocumentName`         | Provided document string is unrecognized      | Validate inputs via `get_available_docs()`      |
| `InvalidFirstYear`            | Requested initial year below historical floor | Inspect boundaries with `get_available_years()` |
| `InvalidLastYear`             | End year is prior to start year or invalid    | Validate parameters prior to invocation         |
| `InvalidDestinationPathError` | Target filesystem path fails safety check     | Confirm folder write and creation access        |

> Transient network failures during asynchronous downloads are automatically managed via retry policies. Unresolved errors are consolidated in the `failed_downloads` dictionary of the returned `DownloadResultCVM` object.

______________________________________________________________________

## Directory & File Layout

### Download Repository Hierarchy

Persisted ZIP archives are systematically grouped within individual category folders:

```
destination_path/
    DFP/
        2020/
            dfp_cia_aberta_2020.zip
        2021/
            dfp_cia_aberta_2021.zip
        ...
    ITR/
        2020/
            itr_cia_aberta_2020.zip
        ...
    FRE/
        2020/
            fre_cia_aberta_2020.zip
        ...
```

### Internal ZIP Structure

Each downloaded archive encloses separate structured tables covering distinct accounting dimensions:

```
dfp_cia_aberta_2023.zip
├── dfp_cia_aberta_2023.csv # General company metadata
├── dfp_cia_aberta_BPA_con_2023.csv # Consolidated Balance Sheet - Active Assets
├── dfp_cia_aberta_BPP_con_2023.csv # Consolidated Balance Sheet - Liabilities & Equity
├── dfp_cia_aberta_DRE_con_2023.csv # Income Statement (Profit & Loss)
├── dfp_cia_aberta_DFC_MD_con_2023.csv # Statement of Cash Flows (Direct Method)
├── dfp_cia_aberta_DFC_MI_con_2023.csv # Statement of Cash Flows (Indirect Method)
├── dfp_cia_aberta_DVA_con_2023.csv # Value Added Statement
└── ...
```

### Automated Parquet Extraction Output

When initializing requests with `automatic_extractor=True`, all enclosed files are unpacked and transformed into high-performance Parquet format:

```
destination_path/
├── DFP/
    2023/
    │ ├── dfp_cia_aberta_2023.parquet
    │ ├── dfp_cia_aberta_BPA_con_2023.parquet
    │ ├── dfp_cia_aberta_BPP_con_2023.parquet
    │ └── ...
└── ...
```

### Extraction integrity and recovery

Every ZIP is validated before consumption. The PyArrow pipeline makes two
passes: it validates structure and a global schema, then writes typed row
groups. Encoding comes from full-member validation (UTF-8, UTF-8 BOM, CP1252,
or Latin-1); invalid structure never silently drops rows.

The dialect remains `QUOTE_NONE`: quotes are literal and multiline is disabled.
Short rows receive trailing nulls only, excess rows abort, and a header-only CSV
becomes an empty Parquet with ordered Arrow `null` fields and no `b'pandas'`
metadata.

One ZIP can create several Parquets. Staging, a manifest, backups, and a lock
provide a **failure-atomic batch commit**: artifacts are validated before
deterministic replacement, and the next operation recovers an interruption.
There is no instant atomic visibility for concurrent readers or concurrent
writes to one destination; a live-process or other-host lock is rejected. An
existing raw ZIP is replaced only after successful transfer and validation.

See the [major migration note](migration-pyarrow-integrity.en.md) for the consumer compatibility table and required actions.

## Best Practices

### 1. Partition Long Temporal Intervals

```python
# ❌ Avoid sweeping multidecade synchronous downloads
cvm.download(
    destination_path="/data",
    list_docs=["DFP"],
    initial_year=2010,  # 25+ years requested at once!
    last_year=2023
)

# ✅ Execute segmented, highly predictable batch slices
cvm.download(
    destination_path="/data",
    list_docs=["DFP"],
    initial_year=2020,  # Controlled 3–4 year slices
    last_year=2023
)
```

### 2. Verify Available Filesystem Space

```python
import shutil

# Measure accessible filesystem capacity
stats = shutil.disk_usage("/data")
free_gb = stats.free / (1024**3)

if free_gb < 10:
    print(f"⚠️  Insufficient workspace capacity detected: {free_gb:.2f} GB")
else:
    cvm.download(
        destination_path="/data/cvm",
        list_docs=["DFP"],
        initial_year=2023
    )
```

### 3. Rely on Parquet for Quantitative Processing

```python
# Whenever downstream statistical workloads are intended, enforce automatic Parquet extraction
cvm.download(
    destination_path="/data/cvm",
    list_docs=["DFP"],
    initial_year=2022,
    automatic_extractor=True  # Massively accelerates dataframe loading
)
```

## Performance & Optimization

### Asynchronous Concurrency

The CVM implementation utilizes `AsyncDownloadAdapterCVM` by default, delivering significant throughput improvements:

- ⚡ **3–5x Faster** than linear synchronous sequential script executions
- 🔄 **Automated Fault Recovery** utilizing exponential retry backoff loops
- 📊 **Real-time Diagnostic Logs** detailing active concurrent thread transfers
- 🧵 **Multi-threaded Worker Execution** (defaulting to 8 concurrent worker queues)

### Benchmark Comparisons

**Full pipeline: download + CSV→Parquet extraction (2026-08-06):**

| Docs                | Period    | ZIPs | Parquets | Extracted Rows |    Output |     Time |  Peak RSS | Errors |
| ------------------- | --------- | ---: | -------: | -------------: | --------: | -------: | --------: | -----: |
| DFP, ITR, FRE, etc. | 2010-2024 |   88 |    1,392 |     63,300,208 | 337.93 MB | 505.04 s | 459.18 MB |      0 |

Estimated duration required to fetch 1 complete annual DFP archive bundle:

| Ingestion Method         | Execution Duration | Relative Throughput |
| ------------------------ | ------------------ | ------------------- |
| Sequential standard HTTP | ~60s               | 1x (Baseline)       |
| AsyncDownloadAdapterCVM  | ~15s               | **4x Faster**       |

## Next Steps

- 📈 **[B3 Quotes](b3-docs.md)** - Explore historical market exchange extraction
- 💻 **[Practical Examples](examples.md)** - Review comprehensive production code workflows
- 🔧 **[API Reference](../reference/cvm-api.md)** - Inspect technical signatures and contracts
- ❓ **[FAQ](faq.md)** - Answers to common setup and troubleshooting questions

______________________________________________________________________

!!! tip "Performance Best Practice"

    For analytical pipeline integrations, consistently specify `automatic_extractor=True`. Columnar Parquet data structures bypass repetitive textual CSV decoding overhead during dataframe initialization.
