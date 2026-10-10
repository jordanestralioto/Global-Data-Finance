# Usage examples

Start with examples 01 and 02. Each script uses the public
`globaldatafinance` API, reports where it saved the result, and exits with an
error if processing fails. Outputs use Parquet; you can read them with
PyArrow, which is installed with the library.

| Example                                                | What it does                                 | What you need to supply                     |
| ------------------------------------------------------ | -------------------------------------------- | ------------------------------------------- |
| [01_quickstart_cvm.py](01_quickstart_cvm.py)           | Downloads CVM DFP and converts it to Parquet | An internet connection                      |
| [02_quickstart_b3.py](02_quickstart_b3.py)             | Extracts quotes from stock markets           | A local COTAHIST file for the selected year |
| [03_advanced_options_b3.py](03_advanced_options_b3.py) | Selects stock, ETF, and options markets      | A local COTAHIST file for the selected year |

All three examples process **only 2023** by default. You can change the year,
range, and output directory through command-line options.

## Prepare the environment

Requirements: Python `>=3.12,<4.0` and `uv`. See the
[installation guide](../docs/user-guide/installation.en.md) if you have not
prepared your environment yet.

Run this from the **repository root**, where `pyproject.toml` is located:

```bash
uv sync --locked --all-extras --dev
```

Do this once. Subsequent commands use `--no-sync` to reuse the environment.
Relative paths such as `./dados_b3` are resolved from the directory where you
run the command.

## 1. Download CVM financial statements

```bash
uv run --locked --no-sync python examples/01_quickstart_cvm.py
```

The example downloads the 2023 **Standardized Financial Statements (DFP)** ZIP,
converts its CSVs to Parquet, and saves the files in `./dados_cvm`.
This selection includes statements from multiple companies and may take a few
minutes. A successful run removes the ZIP after conversion.

To choose a different period and destination:

```bash
uv run --locked --no-sync python examples/01_quickstart_cvm.py \
  --initial-year 2022 --last-year 2023 --destination-path ./dados_cvm
```

## 2. Extract B3 stock quotes

The library **processes local ZIP or TXT files**; it does not download B3
COTAHIST. Obtain the annual file as explained in the
[B3 guide](../docs/user-guide/b3-docs.en.md) and arrange the input like this:

```text
cotahist_b3/
└── COTAHIST_A2023.ZIP
```

You can also use `COTAHIST_A2023.TXT`. Preserve the official filename for each
year. Input files are not included in the examples.

```bash
uv run --locked --no-sync python examples/02_quickstart_b3.py
```

Default output: `./dados_b3/cotacoes_acoes_2023.parquet`. The example selects
quotes from cash (010) and fractional (020) markets. Selection is by market,
rather than a list of tickers; ETFs in those markets may also appear.

If your files are in another directory, use `--path-of-docs`. Quote paths that
contain spaces:

```bash
uv run --locked --no-sync python examples/02_quickstart_b3.py \
  --path-of-docs "/path/to/COTAHIST" \
  --initial-year 2022 --last-year 2023 --destination-path ./dados_b3
```

Every year in the range must be present in the directory. This command writes
`cotacoes_acoes_2022_2023.parquet`.

## 3. Select more markets and adjust processing

```bash
uv run --locked --no-sync python examples/03_advanced_options_b3.py
```

Default output: `./dados_b3/carteira_completa_2023.parquet`. This example passes
`assets_list=['ações', 'etf', 'opções']` to also include call and put options
markets.

Both B3 examples accept `--processing-mode fast` (the default, focused on
throughput) and `--processing-mode slow` (lower memory usage). To process 2022
and 2023 in `slow` mode:

```bash
uv run --locked --no-sync python examples/03_advanced_options_b3.py \
  --initial-year 2022 --last-year 2023 --processing-mode slow
```

When you supply only `--initial-year`, the final year follows it. For example,
`--initial-year 2022` processes only 2022 in all three scripts.

To preserve every market, omit `assets_list` or use `['todos']` in your own
code:

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs='./cotahist_b3',
    initial_year=2023,
    last_year=2023,
    assets_list=['todos'],
    destination_path='./dados_b3',
    output_filename='cotahist_completo_2023',
    verbose=False,
)
if not result['success'] or result['total_records'] == 0:
    raise SystemExit(f'Incomplete extraction: {result["errors"]}')
print(result['output_file'])
```

## Read the generated Parquet

After running example 02, open Python in the same environment:

```bash
uv run --locked --no-sync python
```

Paste this code to see the record count and the first five quotes without
loading the entire file:

```python
import pyarrow.parquet as pq

parquet = pq.ParquetFile('./dados_b3/cotacoes_acoes_2023.parquet')
print(f'Records: {parquet.metadata.num_rows}')
for batch in parquet.iter_batches(
    batch_size=5,
    columns=['data_pregao', 'ticker', 'preco_fechamento'],
):
    print(batch.to_pydict())
    break
```

Change the path to read another output. Pandas and Polars are optional readers;
the examples do not require them.

## Help and common problems

Each script lists its options and defaults with `--help`:

```bash
uv run --locked --no-sync python examples/01_quickstart_cvm.py --help
uv run --locked --no-sync python examples/02_quickstart_b3.py --help
uv run --locked --no-sync python examples/03_advanced_options_b3.py --help
```

- **`ModuleNotFoundError: globaldatafinance`**: prepare the environment and use
  the `uv run` commands above.
- **Missing COTAHIST or unavailable year**: check `--path-of-docs`, the names
  `COTAHIST_AYYYY.ZIP` or `COTAHIST_AYYYY.TXT`, and every requested year.
- **No selected records**: check whether the selected markets exist in the
  input file; an empty output is not reported as success.
- **CVM download failure**: read the diagnostic, check your connection and
  source file availability before trying again.

`cli.py` and `result_validation.py` are support modules; the runnable examples
are the three numbered scripts.

## Validate the examples

From the repository root:

```bash
uv run --locked --no-sync pytest tests/examples
```

Tests execute all three scripts with controlled inputs, read the generated
Parquet, and verify filters and failures. Local responses replace CVM HTTP in
the tests; they require neither the internet nor official COTAHIST files.
Running example 01 normally accesses the CVM source.

For the complete contracts, see the
[CVM guide](../docs/user-guide/cvm-docs.en.md),
[B3 guide](../docs/user-guide/b3-docs.en.md), and
[additional examples](../docs/user-guide/examples.en.md).
