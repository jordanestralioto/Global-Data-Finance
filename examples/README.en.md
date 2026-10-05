# GlobalDataFinance Usage Examples

This folder contains executable examples for extracting Brazilian regulatory
and market data with `globaldatafinance`.

## Source differences

- **CVM (`FundamentalStocksDataCVM`)** downloads financial statements from CVM
  over HTTP and converts them to Parquet.
- **B3 (`HistoricalQuotesB3`)** reads local `COTAHIST_A{YYYY}.ZIP` or `.TXT`
  files, filters or preserves quote records, and writes Parquet. The library
  does not download B3 COTAHIST archives.

## Run the examples

Use `uv` to run the examples in the locked project environment.

From the repository root, prepare the environment once before running the
examples. The subsequent `--no-sync` commands require this setup to have
completed:

```bash
uv sync --locked --all-extras --dev
```

See the [installation guide](../docs/user-guide/installation.en.md) for
dependencies and supported Python versions.

### CVM quickstart

```bash
uv run --locked --no-sync python examples/01_quickstart_cvm.py
```

### B3 stock selection

```bash
uv run --locked --no-sync python examples/02_quickstart_b3.py
```

This processes only the selected stock markets for the explicit year 2023.

### B3 selected classes

```bash
uv run --locked --no-sync python examples/03_advanced_options_b3.py
```

This processes the requested stock, ETF, and options markets for 2022–2023.

### Complete B3 market selection

Omit `assets_list` or pass `assets_list=["todos"]` to preserve every valid
numeric TPMERC, including unknown numeric codes. Specify the year range present
in the local directory; a missing requested year makes the extraction fail.

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs='./cotahist_b3',
    initial_year=2023,
    last_year=2023,
    assets_list=['todos'],
    destination_path='./dados_b3',
    output_filename='cotahist_complete_2023',
    verbose=False,
)

if not result['success']:
    raise SystemExit(result['errors'])
assert result['schema_version'] == 2
print(result['integrity']['unknown_market_counts'])
```

## Output files

Outputs are Parquet files read with PyArrow. Pandas and Polars are optional
downstream dependencies that consumers install if needed:

```bash
python -m pip install pandas  # optional DataFrames
python -m pip install polars  # optional Polars queries
```

- `./dados_cvm/`: Parquet files for each CVM report type.
- `./dados_b3/`: Consolidated Parquet files named with `output_filename`.

## Further documentation

For API details and advanced parameters, see:

- [CVM user guide](../docs/user-guide/cvm-docs.en.md).
- [B3 user guide](../docs/user-guide/b3-docs.en.md).
- [Detailed examples](../docs/user-guide/examples.en.md).
