# Global-Data-Finance

[![PyPI](https://img.shields.io/pypi/v/globaldatafinance)](https://pypi.org/project/globaldatafinance/)
[![Python](https://img.shields.io/pypi/pyversions/globaldatafinance)](https://pypi.org/project/globaldatafinance/)
[![CI](https://github.com/jordanestralioto/Global-Data-Finance/actions/workflows/pipeline.yml/badge.svg?branch=main)](https://github.com/jordanestralioto/Global-Data-Finance/actions/workflows/pipeline.yml)
[![License](https://img.shields.io/pypi/l/globaldatafinance)](https://github.com/jordanestralioto/Global-Data-Finance/blob/main/LICENSE)

[Português](https://github.com/jordanestralioto/Global-Data-Finance/blob/develop/README.md) · **English**

A Python library for downloading Brazilian CVM regulatory filings and
converting B3 historical market quotes to Parquet files. Its API lets
applications select sources and years, validate data, and persist results in
directories of their choice.

[Documentation](https://jordanestralioto.github.io/Global-Data-Finance/en/)
· [Package on PyPI](https://pypi.org/project/globaldatafinance/)
· [Examples](https://github.com/jordanestralioto/Global-Data-Finance/tree/develop/examples)
· [Release history](https://github.com/jordanestralioto/Global-Data-Finance/releases)

**Status:** beta. Requires Python `>=3.12,<4.0`, with CI checks on
Python 3.12, 3.13, and 3.14.

## Sources and features

| Source  | Input                                                                                  | Output                                                 |
| ------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| **CVM** | Download by document type (`DFP`, `ITR`, `FRE`, `FCA`, `CGVN`, `VLMO`, `IPE`) and year | Original ZIP and, optionally, one Parquet file per CSV |
| **B3**  | Local annual COTAHIST files in ZIP or TXT format                                       | Consolidated Parquet with market selection             |

- **Data integrity:** source and artifact validation before publishing Parquet files.
- **Verifiable results:** status, counts, and diagnostics for applications to check each operation.
- **Synchronous or asynchronous execution:** interfaces for scripts, notebooks, and applications with an active event loop.
- **Reading with PyArrow:** included as a dependency; Pandas and Polars can be installed separately for analysis.

## Installation

In a virtual environment with a compatible Python version:

```bash
python -m pip install globaldatafinance
```

In a project managed with uv:

```bash
uv add globaldatafinance
```

See the [installation guide](https://jordanestralioto.github.io/Global-Data-Finance/en/user-guide/installation/)
for environment setup and installation checks.

## Quickstart

The examples use only 2023 to keep the scope of the first run explicit.
The start and end years are inclusive.

### Download CVM filings

Downloading requires internet access. This example downloads annual financial
statements (`DFP`) and converts their CSV files to Parquet:

```python
from globaldatafinance import FundamentalStocksDataCVM

result = FundamentalStocksDataCVM().download(
    destination_path="./data/cvm",
    list_docs=["DFP"],
    initial_year=2023,
    last_year=2023,
    automatic_extractor=True,
)
if result.error_count_downloads > 0 or result.success_count_downloads == 0:
    raise RuntimeError(result.failed_downloads)
print(result.successful_downloads)
```

Files are saved under `data/cvm/DFP/2023/`, and the original ZIP is retained.
`successful_downloads` contains identifiers such as `DFP_2023`; failure
diagnostics are available in `failed_downloads`. Check the result, as a batch
can contain both successes and failures.

**CVM columns are preserved as text**, including leading zeros, decimal
separators, and empty fields. Convert dates and numbers explicitly during
analysis. To save only the ZIP files, use `automatic_extractor=False`,
which is the default.

### Extract B3 quotes

Obtain the files from the [official B3 page](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/)
and place them in an input directory. The library accepts local ZIP or TXT
files named `COTAHIST_A{YYYY}.ZIP` or `COTAHIST_A{YYYY}.TXT` and requires every
requested year. Users download B3 files themselves.

To run the example, prepare:

```text
cotahist/
└── COTAHIST_A2023.ZIP
```

Save and run the following code as a Python script:

```python
from globaldatafinance import HistoricalQuotesB3


def main() -> None:
    b3 = HistoricalQuotesB3()
    result = b3.extract(
        path_of_docs="./cotahist",
        destination_path="./data/b3",
        assets_list=["ações"],
        initial_year=2023,
        last_year=2023,
        output_filename="quotes_2023",
    )
    if not result["success"]:
        raise RuntimeError(result["errors"])
    print(result["output_file"], result["total_records"])


if __name__ == "__main__":
    main()
```

The output is `data/b3/quotes_2023.parquet`. The return value follows the
`ExtractionResultB3` contract: a dictionary with extraction status and metadata.
`ações` selects the spot market (`010`) and the fractional market (`020`);
omitting `assets_list` selects all valid markets. The filter selects markets
rather than individual tickers.

The B3 Parquet uses exact decimal prices and includes provenance information.
The default mode, `fast`, limits concurrency according to available resources;
`processing_mode="slow"` uses one worker to reduce memory use.
According to the [B3 source description](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/),
quotes are provided without adjustments for inflation or corporate actions.

## Read the Parquet

After running the B3 extraction above, inspect the schema and a small sample
without loading the entire file into memory:

```python
import pyarrow.parquet as pq

parquet = pq.ParquetFile("./data/b3/quotes_2023.parquet")
print(parquet.schema_arrow)
for batch in parquet.iter_batches(batch_size=5):
    print(batch.to_pydict())
    break
```

## Documentation

| Goal                                       | Reference                                                                                                         |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| Run your first extraction                  | [Quickstart](https://jordanestralioto.github.io/Global-Data-Finance/en/user-guide/quickstart/)                    |
| Select documents and handle CVM results    | [CVM guide](https://jordanestralioto.github.io/Global-Data-Finance/en/user-guide/cvm-docs/)                       |
| Prepare COTAHIST files and select markets  | [B3 guide](https://jordanestralioto.github.io/Global-Data-Finance/en/user-guide/b3-docs/)                         |
| Look up arguments, results, and exceptions | [API reference](https://jordanestralioto.github.io/Global-Data-Finance/en/dev-guide/api-reference/)               |
| Run examples with synthetic B3 samples     | [Repository examples](https://github.com/jordanestralioto/Global-Data-Finance/blob/develop/examples/README.en.md) |

In notebooks and applications with an active event loop, use
`await cvm.async_download(...)` or `await b3.extract_async(...)`. Each source
guide describes the arguments and failure handling.

## Contributing

Code, test, and documentation contributions are welcome. Start with the
[contribution guide](https://github.com/jordanestralioto/Global-Data-Finance/blob/develop/CONTRIBUTING.md)
for the branch and pull request workflow, testing rules, and quality gates.

After cloning the repository, set up the development environment with the
versioned lockfile and install the hooks:

```bash
uv sync --locked --all-extras --dev
uv run --locked --no-sync pre-commit install --install-hooks
```

Participation follows the [Code of Conduct](https://github.com/jordanestralioto/Global-Data-Finance/blob/develop/CODE_OF_CONDUCT.md).

## Support and security

To report bugs or suggest improvements, open a
[GitHub issue](https://github.com/jordanestralioto/Global-Data-Finance/issues)
with the library version, Python version, and a reproducible example.
For vulnerabilities, follow the private reporting channel in the
[security policy](https://github.com/jordanestralioto/Global-Data-Finance/blob/develop/SECURITY.md).

## License

Distributed under the [Apache 2.0 license](https://github.com/jordanestralioto/Global-Data-Finance/blob/main/LICENSE).
Data usage is subject to the terms of the respective sources.
