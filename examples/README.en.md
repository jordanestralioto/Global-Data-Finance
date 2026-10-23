# Usage examples

To use an example, **open the file, change the values in its `SETTINGS` block,
save it, and run the command shown below**. You can use your usual text editor.
The options you need to change are grouped near the start of each file.

| File                                                   | What it does                      | What you need                    |
| ------------------------------------------------------ | --------------------------------- | -------------------------------- |
| [01_quickstart_cvm.py](01_quickstart_cvm.py)           | Downloads CVM financial documents | Internet access                  |
| [02_quickstart_b3.py](02_quickstart_b3.py)             | Reads quotes from stock markets   | Samples bundled with the project |
| [03_advanced_options_b3.py](03_advanced_options_b3.py) | Also reads options markets        | Samples bundled with the project |

## 1. Prepare the environment once

You need Python `>=3.12,<4.0` and `uv`. If you have not installed them, follow
the [installation guide](../docs/user-guide/installation.en.md).

Open a terminal in the **main project directory**, which contains
`pyproject.toml`, and run:

```bash
uv sync --locked --all-extras --dev
```

Use this same directory when running the examples. A path such as `./dados_b3`
means the `dados_b3` folder inside it. The library creates the output directory
when needed.

You can also run an example as a module, using `-m` and dots between names:

```bash
uv run --locked --no-sync python -m examples.01_quickstart_cvm
uv run --locked --no-sync python -m examples.02_quickstart_b3
uv run --locked --no-sync python -m examples.03_advanced_options_b3
```

Run only the example you need. With `-m`, use `examples.example_name`,
without `/` or the `.py` extension. To use the `examples/file.py` path,
run without `-m`, as shown in the commands below.

## 2. Choose what to process

The variable names are in English, matching the files. Use this table to find
which value to change:

| Variable              | Meaning                                                    | How to fill it in                                                                                               |
| --------------------- | ---------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `INITIAL_YEAR`        | First year                                                 | A number without quotes, such as `2023`                                                                         |
| `LAST_YEAR`           | Last year, included in processing                          | Use the first year again to process just one year                                                               |
| `DESTINATION_PATH`    | Folder where results are saved                             | A quoted path, such as `'./meus_dados'`                                                                         |
| `DOCUMENTS`           | CVM document types, in example 01                          | `['DFP']` for annual statements; `['DFP', 'ITR']` to include quarterly statements; `[]` for all available types |
| `AUTOMATIC_EXTRACTOR` | Convert CVM documents to Parquet                           | `True` converts them; `False` only downloads the ZIPs                                                           |
| `PATH_OF_DOCS`        | Folder containing B3 files                                 | A quoted folder path, without the ZIP or TXT filename                                                           |
| `ASSETS`              | B3 market groups                                           | `['ações']`, `['ações', 'opções']`, or `['todos']`                                                              |
| `OUTPUT_NAME`         | Initial part of the B3 filename                            | Text without a folder, extension, or year, such as `'minhas_cotacoes'`                                          |
| `PROCESSING_MODE`     | B3 processing mode                                         | `'fast'` for higher speed; `'slow'` for lower memory usage                                                      |
| `VERBOSE`             | Also show markets, processing mode, and B3 extraction time | `True` shows them; `False` keeps the basic summary                                                              |

B3 examples display file progress bars during validation and processing with
either `VERBOSE = True` or `False`. This variable controls only extra details
in the final summary. After the processing bar, the library still consolidates
and verifies the Parquet before reporting that extraction is complete.

Change only the value **to the right of `=`**. Keep quotes around text,
brackets around lists, and commas between list items. Write `True` and `False`
without quotes and with the first letter capitalized. After editing, **save
the file** before running it.

### Example 01: CVM documents

To start with just the annual statements for 2023, set the block to:

```python
INITIAL_YEAR = 2023
LAST_YEAR = 2023
DESTINATION_PATH = './dados_cvm'
DOCUMENTS = ['DFP']
AUTOMATIC_EXTRACTOR = True
```

Run:

```bash
uv run --locked --no-sync python examples/01_quickstart_cvm.py
```

Files are saved in `dados_cvm`. Parquet is the data format created by the
conversion; the original ZIPs are also retained. The documents cover multiple
companies, and downloading them may take a few minutes.

The file is configured for **2010 through 2026**, with
`DOCUMENTS = []` for all types. Use the block above for a smaller first run.

### Example 02: B3 quotes

The library reads local files. The repository includes two small synthetic
samples, ready to run the examples after preparing the environment:

```text
cotahist_b3/
├── COTAHIST_A2022.ZIP
└── COTAHIST_A2023.ZIP
```

Each sample contains **21 fictional quotes**: seven instrument and market
combinations across three dates. The dates are January 17, 18, and 19 in 2022
and January 16, 17, and 18 in 2023. All sample tickers, names, ISINs, and prices
are for demonstration; they do not represent official trades.

| Ticker    | Name        | Instrument / market                            |
| --------- | ----------- | ---------------------------------------------- |
| `ALFA4`   | ALFA        | Preferred stock in the cash market (010)       |
| `BETA3`   | BETA        | Common stock in the cash market (010)          |
| `INDX11`  | INDICE DEMO | ETF in the cash market (010)                   |
| `ALFA4F`  | ALFA        | Preferred stock in the fractional market (020) |
| `ALFAA30` | ALFA        | Call option (070)                              |
| `ALFAM30` | ALFA        | Put option (080)                               |
| `ALFA4`   | ALFA        | Stock in the forward market (030)              |

Prices vary across instruments, dates, and years. Each quote represents four
trades of equal size; volume equals the average price times the total
quantity. Options have a strike price and maturity; cash stocks and the ETF
have no maturity. ISINs distinguish instruments, while `ALFA4`, `ALFA4F`, and
the forward position in `ALFA4` share the same stock identifier. Options in
different years have different ISINs.

These files are generated by
[`scripts/generate_example_cotahist.py`](../scripts/generate_example_cotahist.py);
edit the generator and regenerate the ZIPs to change the samples.

For real datasets, follow the [B3 guide](../docs/user-guide/b3-docs.en.md),
keep the files in `cotahist_b3_local/`, and adjust the example's
`PATH_OF_DOCS` and years. That folder is Git-ignored. Uncompressed TXT also
works; keep the official `COTAHIST_AYYYY.ZIP` or `.TXT` name and supply every
requested year.

Example 02 is already configured for 2023. If your input is in another folder,
replace the `PATH_OF_DOCS` line with something like:

```text
PATH_OF_DOCS = '/home/usuario/Minha pasta/COTAHIST'
```

Quotes also allow paths containing spaces. Run:

```bash
uv run --locked --no-sync python examples/02_quickstart_b3.py
```

The default result is `dados_b3/cotacoes_acoes_2023.parquet`. To process 2022
and 2023, change `INITIAL_YEAR` to `2022` and `LAST_YEAR` to `2023`. The name
automatically becomes `cotacoes_acoes_2022_2023.parquet`.
The bundled sample and default settings produce **12 quotes**:
four instruments across three dates.

`ASSETS = ['ações']` selects cash (010) and fractional (020) markets. ETFs in
these markets may also appear. This option selects **markets**; it does not
select companies by ticker codes such as PETR4.

### Example 03: more B3 markets

Use this file to include options. It works the same way as example 02; the
initial selection is `ASSETS = ['ações', 'opções']`. The `ações` alias includes
markets 010 and 020, which also include ETFs. Adding the `etf` alias would
select those same markets.

The file is configured for **2022 through 2023**, with local inputs in
`./cotahist_b3`. The folder must contain the files for both years. To try just
2023, change both years to `2023`. To change the folder, edit `PATH_OF_DOCS`
as in example 02.

Run:

```bash
uv run --locked --no-sync python examples/03_advanced_options_b3.py
```

With the current settings, the result is
`dados_b3/carteira_completa_2022_2023.parquet`. With both years set to 2023,
it becomes `dados_b3/carteira_completa_2023.parquet`. To include every market
in either B3 example, change `ASSETS` to `['todos']`.
The bundled samples produce **36 quotes** with example 03's default settings:
six instruments across three dates in each year. The samples' forward market
(030) is excluded by that selection. With `ASSETS = ['todos']`, the output has
**42 quotes**, including the forward market.

## 3. Check the result

When finished, each example shows the output directory or file and the number
of processed files. The B3 examples also show the quote count and a preview
of the first six rows, including date, ticker, market, name, closing price,
and ISIN. The preview reads only a small Parquet batch. If processing fails
or produces no data, the script prints a diagnostic and exits with an error.

The same ticker can appear on different dates or in different markets.
Consider `data_pregao`, `ticker`, and `tipo_mercado` together to understand
those rows. That combination never repeats in the samples. The name ALFA also
appears on the options because they refer to the same issuer; their ISINs
differ from the stock's ISIN.

To see five quotes from example 02, open Python from the terminal:

```bash
uv run --locked --no-sync python
```

Paste the following code. PyArrow is already installed with the library:

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

If you changed the folder, name, or years, adjust the quoted path to match the
generated file. This code reads a small sample without loading all quotes into
memory.

## If an error appears

- **Library not found:** prepare the environment and use `uv run` as shown
  above.
- **COTAHIST not found or year unavailable:** check `PATH_OF_DOCS`, the
  `COTAHIST_AYYYY.ZIP` or `.TXT` names, and that every year has a file.
- **No quotes selected:** check `ASSETS` and whether the chosen markets exist
  in the input.
- **CVM download failed:** check your connection and read which documents
  failed in the diagnostic before retrying.
- **Error after editing:** check quotes, brackets, commas, and that the last
  year is greater than or equal to the first year.
- **Message asking you to edit `SETTINGS`:** remove extra command options,
  change the values in the file, save it, and run it again.

The file `support.py` handles result checks and messages for the examples.
To use or customize the examples, edit the three numbered files.

## Validate the examples

From the main project directory:

```bash
uv run --locked --no-sync pytest tests/examples
```

To regenerate the two versioned samples, or verify that they match the
generator without modifying them:

```bash
uv run --locked --no-sync python scripts/generate_example_cotahist.py
uv run --locked --no-sync python scripts/generate_example_cotahist.py --check
```

The generator replaces only the 2022 and 2023 ZIPs in `cotahist_b3/`. ZIP
timestamps are fixed to avoid changes caused by the generation date. Tests
also execute the scripts with the bundled samples without editing their
settings or requiring local annual datasets.

Tests use local ZIP, TXT, CSV, and Parquet files created for validation. CVM
HTTP is replaced with local responses without downloading real data.

See the [CVM](../docs/user-guide/cvm-docs.en.md) and
[B3](../docs/user-guide/b3-docs.en.md) guides for the full contracts.
