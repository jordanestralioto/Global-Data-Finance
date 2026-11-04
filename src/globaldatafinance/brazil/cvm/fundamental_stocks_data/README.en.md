# CVM company document family

This package owns selection and policy for Brazilian public-company documents.
The consumer facade remains `FundamentalStocksDataCVM`.

## Responsibilities

| Module      | Responsibility                                                          |
| ----------- | ----------------------------------------------------------------------- |
| `core.py`   | Document catalog, first years, annual URLs, and available-year contract |
| `client.py` | Request validation, company destinations, and download orchestration    |
| `errors.py` | Company selection and validation exceptions                             |

Download, CSV preservation, output verification, destination ownership, and
transaction coordination live in [shared CVM ingestion](../ingestion/README.en.md).
That package never imports this family. Global HTTP, path/archive safety, and
transactional publication retain their existing foundation owners.

## Usage

```python
from globaldatafinance import FundamentalStocksDataCVM

result = FundamentalStocksDataCVM().download(
    destination_path='./data_cvm',
    list_docs=['DFP', 'ITR'],
    initial_year=2023,
    last_year=2023,
    automatic_extractor=True,
)
if result.has_errors():
    raise RuntimeError(result.failed_downloads)
```

## Current contracts

`DFP`, `ITR`, `FRE`, `FCA`, `CGVN`, `IPE`, and `VLMO` retain their selection,
first years, URLs, and `{DOC}/{YEAR}` destinations. Empty or omitted selections
still mean all company document types. Additional CVM families do not enter
this default selection.

The orchestrator and facade use `ingestion.http.CvmDownloadAdapter`; results are
`ingestion.models.DownloadResultCVM`, with `{DOC}_{YEAR}` keys.

ZIPs are retained. Fields remain text under `exact-text-v1`, and Parquet names
match CSV basenames. Replacement and preservation of existing files follow the
[inventory contract](https://jordanestralioto.github.io/Global-Data-Finance/en/user-guide/migration-cvm-exact-text/#output-inventory).

## Extension and validation

Another CVM family owns its catalog and period selection and may use the
shared extractor/downloader when the archive contract fits. It composes the
same mechanisms and preserves current source-identity metadata. A new dialect
or financial schema requires its own decision.

Company behavior tests remain under `tests/brazil/cvm/fundamental_stocks_data/`
and `tests/application/cvm_docs/`. Shared mechanics and independent-consumer
tests live under `tests/brazil/cvm/ingestion/`. See the
[CVM API reference](https://jordanestralioto.github.io/Global-Data-Finance/en/reference/cvm-api/) and
[architecture guide](https://jordanestralioto.github.io/Global-Data-Finance/en/dev-guide/architecture/).
