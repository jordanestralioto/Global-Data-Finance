# Quick Start

Welcome to **Global-Data-Finance**! This introductory guide will help you build your foundational financial extraction scripts using clear, executable code examples.

______________________________________________________________________

## Prerequisites

Before running the code examples below, confirm that you have:

- ✅ Installed Global-Data-Finance ([see installation guide](installation.md))
- ✅ Verified Python >=3.12,<4.0 is running
- ✅ An active internet connection for communicating with regulatory and market feeds

______________________________________________________________________

## Example 1: Downloading CVM Regulatory Filings

Let's begin by downloading fundamental corporate financial disclosures directly from CVM (Securities and Exchange Commission of Brazil).

### Minimal Script

```python
from globaldatafinance import FundamentalStocksDataCVM

# 1. Instantiate the CVM public client
cvm = FundamentalStocksDataCVM()

# 2. Download DFP (Standardized Annual Financial Statements)
cvm.download(
    destination_path="/home/user/data_cvm",
    list_docs=["DFP"],
    initial_year=2022,
    last_year=2023
)
```

### What Happens Behind the Scenes?

1. **Client Initialization**: Prepares the CVM client equipped with custom retry policies and adaptive concurrency throttling.
2. **Download Execution**: Asynchronously downloads official DFP archives spanning fiscal years 2022 through 2023.
3. **Persisted Output**: Validates file integrity and persists raw ZIP files into `/home/user/data_cvm`.

### Expected Console Summary

```text
📥 CVM Documents Download
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Documents downloaded successfully!

📊 Summary:
  • Total files: 2
  • Success: 2
  • Errors: 0
  • Elapsed time: 45.3s

📁 Downloaded files:
  ✓ DFP - 2022
  ✓ DFP - 2023
```

______________________________________________________________________

## Example 2: Extracting B3 Historical Market Quotes

Next, let's extract and normalize official market exchange quotes from B3 (Brazilian Stock Exchange).

!!! note "Obtaining B3 COTAHIST Files"

    Unlike CVM filings which are downloaded automatically via HTTP, B3 historical quotes archives must be obtained beforehand from the official B3 portal ([B3 Historical Quotes](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/)).
    Download the official annual ZIP files named `COTAHIST_A{YYYY}.ZIP` (e.g., `COTAHIST_A2023.ZIP` and `COTAHIST_A2024.ZIP`) and place them in your input directory (e.g., `/home/user/cotahist_zips`). `path_of_docs` is this existing input directory; the library does not download or populate it. The extractor also accepts the uncompressed `COTAHIST_A{YYYY}.TXT`; when ZIP and TXT for the same year coexist, ZIP is selected.

### Minimal Script

```python
from globaldatafinance import HistoricalQuotesB3

# 1. Instantiate the B3 public client
b3 = HistoricalQuotesB3()

# 2. Extract stock-class quotes from COTAHIST files
result = b3.extract(
    path_of_docs="/home/user/cotahist_zips",
    assets_list=["ações"],
    initial_year=2023,
    destination_path="/home/user/extracted_quotes"
)
```

### What Happens Behind the Scenes?

1. **Client Initialization**: Prepares the B3 processing client.
1. **Parsing & Extraction**: Reads official positional COTAHIST archives (ZIP or TXT) inside `/home/user/cotahist_zips`, filtering the stock class (`ações`) across spot (010) and fractional (020) market records.
2. **Columnar Normalization**: Converts raw records into typed, columnar schema structures.
3. **Persisted Output**: Atomically writes a consolidated Apache Parquet file (`.parquet`) containing all filtered historical quotes into `/home/user/extracted_quotes`.

### Expected Console Summary

```text
📊 B3 Historical Quotes Extraction
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Extraction completed successfully!

📈 Summary:
  • Processed files: 2
  • Total records: 836,978
  • Asset classes: ações
  • Processing mode: fast
  • Elapsed time: 77.9s

💾 Generated file:
  /home/user/extracted_quotes/cotahist_extracted.parquet
```

______________________________________________________________________

## Discovering Available Metadata and Assets

Before initiating large data extraction jobs, programmatically query the available document types and historical time windows.

### Inspecting CVM Document Catalogs

```python
from globaldatafinance import FundamentalStocksDataCVM

cvm = FundamentalStocksDataCVM()

# Retrieve descriptions for all supported document codes
docs = cvm.get_available_docs()
for code, description in docs.items():
    print(f"{code}: {description}")

# Check supported historical range
years = cvm.get_available_years()
print(f"\nData available spanning from {years.general_min_year} to {years.current_year}")
```

**Console Output**:

```
DFP: Demonstração Financeira Padronizada
ITR: Informação Trimestral
FRE: Formulário de Referência
FCA: Formulário Cadastral
...

Data available spanning from 2010 to current year
```

### Inspecting B3 Asset Classes

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()

# List supported asset filtering strings
assets = b3.get_available_assets()
print("Supported asset categories:")
for asset in assets:
    print(f"  • {asset}")

# Check permitted historical range
years = b3.get_available_years()
print(f"\nQuotes available spanning from {years['minimal_year']} to {years['current_year']}")
```

**Console Output**:

```
Supported asset categories:
  • ações
  • etf
  • opções
  • termo
  • exercicio_opcoes
  • forward
  • leilao

Quotes available spanning from 1986 to current year
```

______________________________________________________________________

## Comprehensive Example: Automated Financial Pipeline

Here is an end-to-end processing pipeline illustrating combined regulatory and market data ingestion:

```python
from globaldatafinance import FundamentalStocksDataCVM, HistoricalQuotesB3

# === PART 1: CVM Regulatory Ingestion ===
print("=" * 60)
print("PHASE 1: Ingesting CVM Financial Statements")
print("=" * 60)

cvm = FundamentalStocksDataCVM()
cvm.download(
    destination_path="/home/user/financial_data/cvm",
    list_docs=["DFP", "ITR"],
    initial_year=2022,
    last_year=2023,
    automatic_extractor=True  # Automatically extracts ZIP files into columnar Parquet datasets
)

# === PART 2: B3 Quotes Processing ===
print("\n" + "=" * 60)
print("PHASE 2: Normalizing B3 Historical Market Quotes")
print("=" * 60)

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/home/user/financial_data/raw_cotahist",
    assets_list=["ações", "etf"],
    initial_year=2022,
    last_year=2023,
    destination_path="/home/user/financial_data/quotes",
    output_filename="stocks_etfs_2022_2023",
    processing_mode="fast"
)

# === PART 3: Diagnostic Results ===
print("\n" + "=" * 60)
print("EXECUTION SUMMARY")
print("=" * 60)

if result['success']:
    print(f"✓ Pipeline finished successfully!")
    print(f"✓ Total consolidated records written: {result['total_records']:,}")
    print(f"✓ Persisted Parquet artifact: {result['output_file']}")
else:
    print(f"✗ Exceptions encountered during processing")
    if 'errors' in result and result['errors']:
        for file_name, message in result['errors'].items():
            print(f"  • {file_name}: {message}")
```

______________________________________________________________________

## Working with Extracted Data

Once extracted into columnar Parquet format, read datasets with PyArrow, the
engine used by the library to produce artifacts. Pandas is an optional
downstream choice; install it separately (`python -m pip install pandas`) when
DataFrame workflows are needed.

### Reading batches with PyArrow

```python
import pyarrow.parquet as pq

# Read without materializing every row at once
parquet = pq.ParquetFile(
    "/home/user/extracted_quotes/cotahist_extracted.parquet"
)

for batch in parquet.iter_batches(batch_size=100_000, columns=["ticker"]):
    print(batch.slice(0, min(5, batch.num_rows)))
```

### Analyzing with Pandas (optional)

```python
import pandas as pd

# Load the generated Parquet file
df = pd.read_parquet("/home/user/extracted_quotes/cotahist_extracted.parquet")

# Preview initial rows
print(df.head())

# Display basic dataset diagnostics
print(f"\nTotal records: {len(df):,}")
print(f"Columns: {list(df.columns)}")
print(f"Time series interval: {df['data_pregao'].min()} to {df['data_pregao'].max()}")
```

Polars is not installed as a library dependency. Install it explicitly in the
consumer environment if it is the preferred downstream reader.

______________________________________________________________________

## Tips for Beginners

!!! tip "Start with a Narrow Scope"

    When developing scripts or running validation tests, request small temporal intervals (e.g., 1 fiscal year) to verify pipeline behavior before triggering multi-decade batch jobs.

!!! tip "Use Fast Mode for Market Data"

    When extracting B3 quotes, `processing_mode="fast"` leverages in-memory parallelization and provides superior processing speed for most standard hardware configurations.

!!! tip "Verify Free Disk Space"

    Historical COTAHIST datasets and multi-year corporate regulatory filings consume substantial storage. Verify adequate local disk capacity prior to extensive historical downloads.

______________________________________________________________________

## Next Steps

Now that you are familiar with foundational operations, dive deeper into detailed reference guides:

- 📄 **[CVM Documents](cvm-docs.md)** - Deep dive into regulatory financial filings
- 📈 **[B3 Quotes](b3-docs.md)** - Detailed specifications for market quote processing
- 💻 **[Practical Examples](examples.md)** - Real-world quantitative recipes and pipelines
- ❓ **[FAQ](faq.md)** - Frequently asked questions and troubleshooting

______________________________________________________________________

!!! success "Congratulations!"

    You have completed the quick start guide! You are now prepared to build production-grade financial extraction scripts with Global-Data-Finance. 🚀
