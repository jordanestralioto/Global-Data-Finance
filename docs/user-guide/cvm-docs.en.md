# CVM filings

Use `FundamentalStocksDataCVM` to download CVM filings by document type and year.
Downloads require internet access; Parquet conversion is optional.

## Choose documents and years

| Code | Content | First year |
| --- | --- | --- |
| `DFP` | Annual financial statements | 2010 |
| `ITR` | Quarterly information | 2011 |
| `FRE` | Reference form | 2010 |
| `FCA` | Registration form | 2010 |
| `CGVN` | Governance report | 2018 |
| `VLMO` | Traded and held securities | 2018 |
| `IPE` | Periodic and occasional documents | 2003 |

Start and end years are inclusive. In mixed selections, each document respects
its first year. `get_available_docs()` returns codes and descriptions;
`get_available_years()` returns the limits by group and the current year.

## Download and convert

```python
from globaldatafinance import FundamentalStocksDataCVM

result = FundamentalStocksDataCVM().download(
    destination_path="./data_cvm",
    list_docs=["DFP", "ITR"],
    initial_year=2023,
    last_year=2023,
    automatic_extractor=True,
)
if result.error_count_downloads > 0 or result.success_count_downloads == 0:
    raise RuntimeError(result.failed_downloads)
print(result.successful_downloads)
```

Choose a small range for the first run. The destination can be relative or
absolute and must allow writing.

| Option | Behavior |
| --- | --- |
| `list_docs` | List of codes. `None` or `[]` selects all types. |
| `initial_year` / `last_year` | Inclusive limits. Without explicit limits, selection uses the available minimums and the current year. |
| `automatic_extractor=False` | Default: saves ZIPs. |
| `automatic_extractor=True` | Saves ZIPs and converts their CSV files to Parquet. |

The [CVM reference](../reference/cvm-api.md) contains the full signature,
year limits, and exceptions.

## Understand the generated files

Original ZIPs are retained, including attachments that are not CSV. Extraction
creates one Parquet per CSV with the same base name. ZIPs and Parquets go under
`{destination_path}/{DOC}/{YEAR}/`, for example:

```text
data_cvm/DFP/2023/
├── dfp_cia_aberta_2023.zip
└── dfp_cia_aberta_BPA_con_2023.parquet
```

Each Parquet name depends on the CSV files present in the ZIP.

Under the `exact-text-v1` contract, **all CVM columns contain text**. Leading
zeros, decimal separators, and literal tokens are preserved; empty fields are
`""`. Convert dates and numbers explicitly in your analysis. A header-only CSV
produces an empty Parquet with the defined columns.

Content is verified before publication. The Parquet batch can be recovered
after a failure; concurrent readers do not receive an instantaneous swap of
the whole directory. Details are in the [CVM reference](../reference/cvm-api.md)
and the [publication protocol](../reference/transactional-publication.md).

## Check success and handle failures

The return value is a `DownloadResultCVM`, not a data table:

- `successful_downloads` lists completed identifiers, such as `DFP_2023`.
- `failed_downloads` maps failures to their diagnostics.
- `success_count_downloads` and `error_count_downloads` summarize the batch.

Individual file failures are recorded in the result and may coexist with
completed downloads. Check these fields before continuing your analysis.
Parameter or path errors can raise exceptions immediately; see the
[documented exceptions](../reference/cvm-api.md).

In notebooks or applications with an active event loop, use
`await cvm.async_download(...)` with the same arguments and result, as described
in the [async API](../reference/cvm-api.md#async_download).

To adjust logs and attempts, see [logging](../dev-guide/logging-system.md)
and [retry](../dev-guide/retry-strategy.md). If you previously consumed Parquets
with inferred types, follow the [exact-text migration](migration-cvm-exact-text.md).

## Resume downloads with a checkpoint

Set `base_path` to a directory where the application has write access.

Record `successful_downloads` in an application-owned checkpoint. A year directory may remain after a failure. Request each pending year separately to respect gaps in history:

```python
import json
from pathlib import Path

from globaldatafinance import FundamentalStocksDataCVM

cvm = FundamentalStocksDataCVM()
base_path = Path("/data/cvm")
checkpoint = base_path / "completed-downloads.json"
completed_downloads = set()
if checkpoint.is_file():
    completed_downloads.update(json.loads(checkpoint.read_text(encoding="utf-8")))
current_year = cvm.get_available_years().current_year
refresh_years = {current_year}
for year in range(2020, current_year + 1):
    identifier = f"DFP_{year}"
    if identifier in completed_downloads and year not in refresh_years:
        continue
    result = cvm.download(
        destination_path=str(base_path), list_docs=["DFP"],
        initial_year=year, last_year=year, automatic_extractor=True,
    )
    if identifier in result.successful_downloads:
        completed_downloads.add(identifier)
        pending = checkpoint.with_suffix(".tmp")
        pending.write_text(json.dumps(sorted(completed_downloads)), encoding="utf-8")
        pending.replace(checkpoint)
    if result.has_errors():
        print(result.failed_downloads)
```

The example uses a checkpoint owned by a single process and refreshes the current year on each run. CVM may also revise earlier years: include them in `refresh_years` according to your application's policy. The checkpoint records previous successes; revalidate local artifacts before reusing them and remove identifiers whose files are missing or corrupted.
