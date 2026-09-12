# Practical Examples

This page provides end-to-end operational code examples illustrating how to implement Global-Data-Finance in real-world data engineering scripts and analytical workflows.

______________________________________________________________________

## Example 1: Full DFP Regulatory Ingestion

Download standardized annual financial statements directly from CVM servers and normalize them into columnar Apache Parquet artifacts.

```python
from globaldatafinance import FundamentalStocksDataCVM

# Instantiate public client
cvm = FundamentalStocksDataCVM()

# Trigger download with automated Parquet conversion
cvm.download(
    destination_path="/home/user/financial_data/dfp",
    list_docs=["DFP"],
    initial_year=2020,
    last_year=2023,
    automatic_extractor=True  # Automatically converts downloaded tables into Parquet
)

print("✓ Ingestion and extraction completed successfully!")
```

______________________________________________________________________

## Example 2: High-Performance Equities and ETF Extraction

Extract historical exchange trading quotes for equities and ETFs across the spot
(010) and fractional (020) markets, utilizing multi-threaded vectorization.

```python
from globaldatafinance import HistoricalQuotesB3
import time

# Instantiate public client
b3 = HistoricalQuotesB3()

# Track execution duration
start_time = time.time()

# Extract historical transactions
result = b3.extract(
    path_of_docs="/home/user/cotahist",
    assets_list=["ações", "etf"],
    initial_year=2021,
    last_year=2023,
    destination_path="/home/user/quotes",
    output_filename="equities_etf_2021_2023",
    processing_mode="fast"
)

elapsed = time.time() - start_time

# Display execution diagnostics
if result['success']:
    print(f"✓ Extraction complete in {elapsed:.2f}s")
    print(f"  Processed records: {result['total_records']:,}")
    print(f"  Average throughput: {result['total_records']/elapsed:,.0f} records/sec")
    print(f"  Consolidated artifact: {result['output_file']}")
```

______________________________________________________________________

## Example 3: Unified Automated Processing Pipeline

An integrated ingestion script compiling corporate fundamental disclosures from CVM alongside historical exchange quotes from B3.

```python
from globaldatafinance import FundamentalStocksDataCVM, HistoricalQuotesB3
import os


# Configure target filesystem repositories
base_dir = "/home/user/financial_data"
cvm_dir = os.path.join(base_dir, "cvm")
cotahist_dir = os.path.join(base_dir, "cotahist")
output_dir = os.path.join(base_dir, "processed")

# === PHASE 1: CVM Ingestion ===
print("=" * 60)
print("PHASE 1: Downloading CVM Financial Filings")
print("=" * 60)

cvm = FundamentalStocksDataCVM()
cvm.download(
    destination_path=cvm_dir,
    list_docs=["DFP", "ITR"],
    initial_year=2022,
    last_year=2023,
    automatic_extractor=True
)

# === PHASE 2: B3 Processing ===
print("\n" + "=" * 60)
print("PHASE 2: Normalizing B3 Historical Market Quotes")
print("=" * 60)

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs=cotahist_dir,
    assets_list=["ações", "etf"],
    initial_year=2022,
    last_year=2023,
    destination_path=output_dir,
    output_filename="market_quotes_2022_2023"
)

# === PHASE 3: Execution Summary ===
print("\n" + "=" * 60)
print("FINAL PIPELINE SUMMARY")
print("=" * 60)
print(f"✓ Pipeline execution completed!")
print(f"✓ Corporate CVM archives deposited at: {cvm_dir}")
print(f"✓ Consolidated B3 market quotes persisted at: {result['output_file']}")
```

______________________________________________________________________

## Example 4: Analytical Exploration with Pandas

Load and evaluate extracted historical exchange quotes using traditional Pandas dataframes.

```python
import pandas as pd
from globaldatafinance import HistoricalQuotesB3

# 1. Trigger extraction
b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=2023,
    output_filename="stocks_2023"
)

# 2. Load extracted Parquet dataset
df = pd.read_parquet(result['output_file'])

# 3. Perform baseline analytical evaluations
print("=" * 60)
print("EXPLORATORY DATA ANALYSIS")
print("=" * 60)

print(f"\nTotal historical rows: {len(df):,}")
print(f"Time series interval: {df['data_pregao'].min()} to {df['data_pregao'].max()}")
print(f"Unique instrument tickers: {df['ticker'].nunique()}")

# Calculate Top 10 traded equities by cumulative monetary volume
top_volume = df.groupby('ticker')['volume_total'].sum().nlargest(10)
print("\nTop 10 instruments by trading volume:")
for ticker, volume in top_volume.items():
    print(f"  {ticker}: R$ {volume/1e9:.2f}B")

# Display statistical distribution of closing execution prices
print(f"\nStatistical metrics for closing quote executions:")
print(df['preco_fechamento'].describe())
```

______________________________________________________________________

## Example 5: Bounded PyArrow Batch Processing

Use PyArrow to process Parquet data in bounded batches.

```python
import pyarrow.compute as pc
import pyarrow.parquet as pq
from globaldatafinance import HistoricalQuotesB3

# Extract transaction records
b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=2020,
    last_year=2023
)

# Project and filter without loading the entire artifact
parquet = pq.ParquetFile(result['output_file'])
for batch in parquet.iter_batches(
    batch_size=200_000,
    columns=['ticker', 'preco_minimo', 'preco_maximo'],
):
    petr4 = batch.filter(pc.equal(batch.column('ticker'), 'PETR4'))
    if petr4.num_rows:
        print(petr4)
```

______________________________________________________________________

## Example 6: Command-Line Automation Script

A self-contained CLI script designed for scheduled cron executions and unattended batch data harvesting.

```python
#!/usr/bin/env python3
"""
Automated CLI batch harvester for downloading and normalizing financial data.
"""

import argparse
import sys
from pathlib import Path
from globaldatafinance import FundamentalStocksDataCVM, HistoricalQuotesB3

def main():
    parser = argparse.ArgumentParser(description="Automated financial data harvester")
    parser.add_argument("--source", choices=["cvm", "b3", "both"], required=True, help="Target repository data source")
    parser.add_argument("--destination", type=str, required=True, help="Root target output folder")
    parser.add_argument("--start-year", type=int, default=2022, help="Initial historical fiscal year")
    parser.add_argument("--end-year", type=int, default=2023, help="Ending fiscal year")
    parser.add_argument("--verbose", action="store_true", help="Enable verbose console debugging output")

    args = parser.parse_args()

    # Verify and initialize destination repository tree
    dest_path = Path(args.destination)
    dest_path.mkdir(parents=True, exist_ok=True)

    try:
        if args.source in ["cvm", "both"]:
            print("Downloading CVM corporate regulatory archives...")
            cvm = FundamentalStocksDataCVM()
            cvm.download(
                destination_path=str(dest_path / "cvm"),
                list_docs=["DFP", "ITR"],
                initial_year=args.start_year,
                last_year=args.end_year,
                automatic_extractor=True
            )

        if args.source in ["b3", "both"]:
            print("Extracting B3 historical exchange quotes...")
            b3 = HistoricalQuotesB3()
            result = b3.extract(
                path_of_docs=str(dest_path / "cotahist"),
                assets_list=["ações", "etf"],
                initial_year=args.start_year,
                last_year=args.end_year,
                destination_path=str(dest_path / "quotes")
            )

            if result['success']:
                print(f"✓ Normalized and consolidated {result['total_records']:,} transaction rows")

        print("✓ Automated batch processing script finished cleanly!")
        return 0

    except Exception as exc:
        print(f"✗ Fatal execution exception encountered: {exc}", file=sys.stderr)
        return 1

if __name__ == "__main__":
    sys.exit(main())
```

**Execution Examples**:

```bash
# Execute only CVM regulatory harvesting
python harvester.py --source cvm --destination /data --start-year 2022

# Execute only B3 market quote processing
python harvester.py --source b3 --destination /data --start-year 2020 --end-year 2023

# Execute comprehensive harvesting across both sources
python harvester.py --source both --destination /data --verbose
```

______________________________________________________________________

## Example 7: Jupyter Notebook Interactive Visualizations

Harnessing Global-Data-Finance inside interactive Jupyter notebook sessions to generate financial charting analytics.

!!! note "Optional Dependencies"

    Visualization libraries used in this example (`matplotlib`, `seaborn`) are optional external packages:

    ```bash
    pip install matplotlib seaborn
    ```

```ipython
# Cell 1: Package imports and visual configuration
from globaldatafinance import HistoricalQuotesB3
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

sns.set_style("darkgrid")
%matplotlib inline

# Cell 2: Trigger historical quotes extraction
b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=2023
)

# Cell 3: Load Parquet dataset and isolate instrument records
df = pd.read_parquet(result['output_file'])
petr4 = df[df['ticker'] == 'PETR4']

# Cell 4: Plot historical closing quote trajectories
plt.figure(figsize=(14, 6))
plt.plot(petr4['data_pregao'], petr4['preco_fechamento'], color='#1f77b4', linewidth=1.5)
plt.title('PETR4 - Daily Closing Quotes (2023)', fontsize=16, fontweight='bold')
plt.xlabel('Session Date')
plt.ylabel('Execution Price (R$)')
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()

# Cell 5: Plot daily cumulative monetary turnover volume
plt.figure(figsize=(14, 6))
plt.bar(petr4['data_pregao'], petr4['volume_total'] / 1e6, alpha=0.7, color='#2ca02c')
plt.title('PETR4 - Daily Traded Financial Volume (2023)', fontsize=16, fontweight='bold')
plt.xlabel('Session Date')
plt.ylabel('Turnover Volume (Millions R$)')
plt.tight_layout()
plt.show()
```

______________________________________________________________________

## Next Steps

- 📄 **[CVM Documents](cvm-docs.md)** - Deep dive into corporate filings and reporting standards
- 📈 **[B3 Quotes](b3-docs.md)** - Exhaustive reference covering historical exchange extraction
- ❓ **[FAQ](faq.md)** - Answers to frequent architectural and deployment questions
- 🔧 **[Advanced Usage](../dev-guide/advanced-usage.md)** - Optimization patterns and system tuning
