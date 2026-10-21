# B3 historical quotes

Use `HistoricalQuotesB3` to convert local annual COTAHIST files into one
consolidated Parquet. The library returns extraction status and metadata.

## Prepare the files

The extractor accepts local ZIP or TXT files named `COTAHIST_A{YYYY}.ZIP` or
`COTAHIST_A{YYYY}.TXT`. Obtain them from the
[official B3 page](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/)
and place them in an existing directory. The library does not download them.

```text
cotahist/
├── COTAHIST_A2022.ZIP
└── COTAHIST_A2023.TXT
```

Supply **every requested year**. If ZIP and TXT coexist for a year, both are
fully validated; ZIP is chosen only when their decompressed contents are
identical. Different contents cause failure. Keep the files unchanged during
extraction.

Inside a ZIP, exactly one COTAHIST member must be at the root, named
`COTAHIST_A{YYYY}.TXT`, `COTAHIST.A{YYYY}`, or `COTAHIST_A{YYYY}` with the
same year as the outer file. Missing, nested, ambiguous, or wrong-year members
are rejected. Sources must contain at least one valid `01` record in addition
to their controls.

## Extract quotes

```python
from globaldatafinance import HistoricalQuotesB3


def main() -> None:
    b3 = HistoricalQuotesB3()
    result = b3.extract(
        path_of_docs="./cotahist",
        destination_path="./data_b3",
        assets_list=["ações", "opções"],
        initial_year=2022,
        last_year=2023,
        output_filename="quotes_2022_2023",
        processing_mode="fast",
    )
    if not result["success"]:
        raise RuntimeError(result["errors"])
    print(result["output_file"], result["total_records"])


if __name__ == "__main__":
    main()
```

This example creates `data_b3/quotes_2022_2023.parquet` after validating the
sources and verifying the final file. Years are inclusive. Set them explicitly;
the defaults span 1986 through the current year.

## Choose markets

Values in `assets_list` are aliases for COTAHIST markets. They do not select
companies by ticker. `ações` and `etf` use the same codes and include the spot
market (010) and fractional market (020).

| API value | Selection |
| --- | --- |
| `ações`, `etf` | Spot and fractional: `010`, `020` |
| `opções` | Call and put: `070`, `080` |
| `termo` | Term: `030` |
| `exercicio_opcoes` | Exercise: `012`, `013` |
| `forward` | Forward: `050`, `060` |
| `leilao` | Auction: `017` |
| `lote_bloco` | Block lot: `021` |
| `todos` | Every valid numeric TPMERC, including unknown codes |

The default `assets_list=None` means `todos`; an empty list is invalid.
`get_available_assets()` lists the accepted aliases. API values stay in
Portuguese, including when the rest of the program uses another language.

## Choose a mode and destination

| Option | When to use it |
| --- | --- |
| `processing_mode="fast"` | Default: processes files with concurrency bounded by CPU, memory, and source count. |
| `processing_mode="slow"` | Uses one worker and reduces memory use. |
| `destination_path` | Output directory; defaults to `path_of_docs`. |
| `output_filename` | Base name without directories; `.parquet` is optional and appended when absent. |
| `verbose=False` | Hides the final summary; progress bars remain visible. |

Both modes apply the same data and integrity rules. For worker and resource
settings, see [advanced usage](../dev-guide/advanced-usage.md).

## Check and consume the result

The main `ExtractionResultB3` fields are below. The complete list and exceptions
are in the [B3 reference](../reference/b3-api.md).
Inside an active event loop, use `await b3.extract_async(...)`; arguments and
results are identical. In scripts processing several sources with processes,
protect the call with `if __name__ == '__main__':`, as shown in the
[parallel processing example](../dev-guide/advanced-usage.md).

| Field | How to use it |
| --- | --- |
| `success` | Check before consuming the output. |
| `errors` | Failure diagnostics by source or stage. |
| `output_file` | Path to the newly published Parquet; empty on failure. |
| `total_records` | Number of published rows. |
| `integrity` | Annual coverage, validation, provenance, and warnings. |

A missing year or invalid source returns failure and publishes no new output.
If all sources are valid but the filter selects no quotes, the result is
successful with an empty Parquet. Zero rows alone do not indicate an error.

Parquet uses [B3 schema v2](../reference/b3-schema-v2.md): exact decimal prices,
provenance fields, and the original record. Read it with PyArrow as shown in
the [quickstart](quickstart.md). For files produced by earlier versions, see
the [migration guide](migration-pyarrow-integrity.md).
