# Quickstart

After [installing the library](installation.md), choose a source. CVM requires
internet access; B3 uses local files. The examples below process only 2023.

## Download CVM filings

```python
from globaldatafinance import FundamentalStocksDataCVM

result = FundamentalStocksDataCVM().download(
    destination_path="./data_cvm",
    list_docs=["DFP"],
    initial_year=2023,
    last_year=2023,
    automatic_extractor=True,
)
if result.error_count_downloads > 0 or result.success_count_downloads == 0:
    raise RuntimeError(result.failed_downloads)
print(result.successful_downloads)
```

The download saves the original ZIP and converts its CSV files to Parquet in
the selected directory. CVM columns contain text; convert dates and numbers in
your analysis when needed. To download ZIPs without conversion, use
`automatic_extractor=False`.

See the [CVM guide](cvm-docs.md) to choose documents and handle partial failures.

## Extract B3 quotes

Obtain files from the [official B3 page](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/)
and place the desired year in the input directory. The extractor accepts
local ZIP or TXT files named `COTAHIST_A{YYYY}.ZIP` or `COTAHIST_A{YYYY}.TXT`.
The library does not download these files. For this example, supply 2023:

```text
cotahist/
└── COTAHIST_A2023.ZIP
```

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="./cotahist",
    destination_path="./data_b3",
    assets_list=["ações"],
    initial_year=2023,
    last_year=2023,
)
if not result["success"]:
    raise RuntimeError(result["errors"])
print(result["output_file"], result["total_records"])
```

`ações` selects spot and fractional markets. The result is a dictionary of
status and metadata; data is stored in the Parquet at `output_file`.
See the [B3 guide](b3-docs.md) for other markets, years, and processing modes.

## Read the Parquet

Use the path returned by the preceding B3 extraction. To inspect a small sample
without loading the entire file:

```python
import pyarrow.parquet as pq

parquet = pq.ParquetFile(result["output_file"])
print(parquet.schema_arrow)
for batch in parquet.iter_batches(batch_size=5):
    print(batch.to_pydict())
    break
```

To run repository examples with the included synthetic B3 samples, see
[practical examples](examples.md).
