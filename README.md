# Global-Data-Finance

Python library for downloading Brazilian CVM filings and converting local B3
historical quotes to Parquet. Requires Python `>=3.12,<4.0`.

[Documentation in Portuguese](https://jordanestralioto.github.io/Global-Data-Finance/)
· [Documentation in English](https://jordanestralioto.github.io/Global-Data-Finance/en/)
· [PyPI](https://pypi.org/project/globaldatafinance/)

## Install

```bash
python -m pip install globaldatafinance
```

For a virtual environment or a project managed with uv, see
[installation](docs/user-guide/installation.en.md).

## Download CVM filings

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
```

This downloads the selected annual ZIP and converts its CSV files to Parquet.
The original ZIP is retained. CVM fields remain text; convert dates and numbers
in your analysis when needed. See the [CVM guide](docs/user-guide/cvm-docs.en.md)
for document types and result handling.

## Extract B3 quotes

B3 accepts local ZIP or TXT files named `COTAHIST_A{YYYY}.ZIP` or
`COTAHIST_A{YYYY}.TXT`. Obtain the files before calling the extractor and
provide every year requested. The library does not download B3 data.

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="./cotahist",
    destination_path="./data/b3",
    assets_list=["ações"],
    initial_year=2023,
    last_year=2023,
)
if not result["success"]:
    raise RuntimeError(result["errors"])
print(result["output_file"])
```

`ações` selects spot and fractional markets. Omit `assets_list` to retain all
valid markets. The result contains status and artifact metadata; the data is
written to Parquet. See the [B3 guide](docs/user-guide/b3-docs.en.md) for inputs,
filters, and processing modes.

## Find the right guide

| Task                                   | Read                                               |
| -------------------------------------- | -------------------------------------------------- |
| Run a first extraction                 | [Quickstart](docs/user-guide/quickstart.en.md)     |
| Customize runnable examples            | [Examples](examples/README.en.md)                  |
| Look up arguments, results, or schemas | [API overview](docs/dev-guide/api-reference.en.md) |
| Reproduce performance measurements     | [Benchmarks](docs/dev-guide/benchmarks.en.md)      |
| Contribute code or documentation       | [Contributing](CONTRIBUTING.md)                    |

The public package exports `FundamentalStocksDataCVM`, `HistoricalQuotesB3`,
and `ExtractionResultB3`. PyArrow is included; Pandas and Polars are optional
readers installed by the consumer.

Report bugs through [GitHub Issues](https://github.com/jordanestralioto/Global-Data-Finance/issues).
For vulnerabilities, follow [SECURITY.md](SECURITY.md). Participation follows
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Licensed under [Apache 2.0](LICENSE).
