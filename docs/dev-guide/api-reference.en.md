# API Reference

Signatures and results for the public Global-Data-Finance API. The
[CVM](../reference/cvm-api.md) and [B3](../reference/b3-api.md) references
describe validation and persistence in detail.

______________________________________________________________________

## Module `globaldatafinance` (Public Root Exports)

Import the main clients and the B3 result type from the package root:

```python
from globaldatafinance import (
    FundamentalStocksDataCVM,
    HistoricalQuotesB3,
    ExtractionResultB3,
)
```

______________________________________________________________________

### `FundamentalStocksDataCVM`

Downloads CVM regulatory filings and optionally extracts them to Parquet.

#### Methods

**`__init__()`**

```python
def __init__(self, *, settings: Settings | None = None) -> None:
    ...
```

Creates a CVM client with the standard download and validation components.

`settings` accepts an immutable `Settings` snapshot imported from
`globaldatafinance.core.config`. With `None`, each client reads a fresh snapshot
of the current environment; the `settings` property exposes the snapshot used.

**`download()`**

```python
def download(
    self,
    destination_path: str,
    list_docs: list[str] | None = None,
    initial_year: int | None = None,
    last_year: int | None = None,
    automatic_extractor: bool = False,
) -> DownloadResultCVM:
    ...
```

Downloads regulatory CVM archives directly into a local filesystem directory.

**Parameters**:

- `destination_path` (`str`): Target destination storage directory.
- `list_docs` (`list[str]`, optional): Selected document type codes (e.g., `["DFP", "ITR"]`). Defaults to all supported document categories when omitted.
- `initial_year` (`int`, optional): First year, inclusive. `None` uses the first supported year for each document type.
- `last_year` (`int`, optional): Last year, inclusive. `None` uses the current system year.
- `automatic_extractor` (`bool`): Extract downloaded ZIP archives to Apache Parquet. Default: `False`.

When enabled, the CVM extractor uses PyArrow and `QUOTE_NONE`, with Arrow
`string` columns and exact text preservation, including empty fields as `""`.
The original ZIP is retained and every record is checked before publication.
Header-only CSVs keep string columns and zero rows. See the
[CVM exact text migration](../user-guide/migration-cvm-exact-text.en.md) for the
persisted contract and consumer changes.

**Returns**:

- `DownloadResultCVM`: Structured result object containing:
  - `success_count_downloads` (`int`): Count of successfully downloaded archives.
  - `error_count_downloads` (`int`): Count of failed downloads.
  - `successful_downloads` (`list[str]`): List of completed document identifiers in `{DOC}_{YEAR}` format (e.g., `DFP_2023`). These values are logical identifiers, not full filesystem paths or filenames.
  - `failed_downloads` (`dict[str, str]`): Mapping of failed document identifiers to failure messages.
  - `elapsed_time` (`float`): Total wall-clock execution time in seconds.
  - `has_errors()` (`bool`): Helper method returning `True` if any download failed.

**`async_download()`**

```python
async def async_download(
    self,
    destination_path: str,
    list_docs: list[str] | None = None,
    initial_year: int | None = None,
    last_year: int | None = None,
    automatic_extractor: bool = False,
) -> DownloadResultCVM:
    ...
```

Asynchronous counterpart to `download()`. Use when calling from inside an existing `asyncio` event loop to avoid nested loop runtime errors.

**`get_available_docs()`**

```python
def get_available_docs(self) -> dict[str, str]:
    ...
```

Returns document codes (`"DFP"`, `"ITR"`, `"FCA"`, `"FRE"`, `"CGVN"`, `"VLMO"`, `"IPE"`) and their descriptions.

**`get_available_years()`**

```python
def get_available_years(self) -> AvailableYearsInfoCVM:
    ...
```

Returns an `AvailableYearsInfoCVM` named tuple with the first supported years
and the current system year:

- `general_min_year` (`int`): Minimum available year for standard documents (e.g. 2010).
- `itr_min_year` (`int`): Minimum available year for quarterly ITR filings (e.g. 2011).
- `cgvn_vlmo_min_year` (`int`): Minimum available year for CGVN / VLMO filings (e.g. 2018).
- `current_year` (`int`): Current system year.
- `ipe_min_year` (`int`, property): First IPE year, 2003.

`years._asdict()` contains the four tuple fields; `ipe_min_year` is an
additional property accessed through its attribute.

______________________________________________________________________

### `HistoricalQuotesB3`

Extracts and consolidates historical B3 quotations from local COTAHIST files.

#### Methods

**`__init__()`**

```python
def __init__(self, *, settings: Settings | None = None) -> None:
    ...
```

Creates a B3 client with the standard parser and extraction components.

`settings` accepts an immutable `Settings` snapshot imported from
`globaldatafinance.core.config`. With `None`, each client reads a fresh snapshot
of the current environment; the `settings` property exposes the snapshot used.

**`extract()`**

```python
def extract(
    self,
    path_of_docs: str,
    assets_list: list[str] | None = None,
    initial_year: int | None = None,
    last_year: int | None = None,
    destination_path: str | None = None,
    output_filename: str = "cotahist_extracted",
    processing_mode: str = "fast",
    verbose: bool = True,
) -> ExtractionResultB3:
    ...
```

Parses COTAHIST ZIP or TXT files (`COTAHIST_A{YYYY}.ZIP` or `.TXT`), filters
quotations by market type, and writes one consolidated Parquet file. It returns
an `ExtractionResultB3` mapping containing status, counts, errors, and the
output path.

**Parameters**:

- `path_of_docs` (`str`): Directory containing local COTAHIST ZIP or TXT files.
- `assets_list` (`list[str] | None`): Asset categories; `None` selects `todos`, every valid numeric TPMERC.
- `initial_year` (`int`, optional): First year, inclusive. `None` uses 1986.
- `last_year` (`int`, optional): Last year, inclusive. `None` uses the current system year.
- `destination_path` (`str`, optional): Custom directory destination for the generated Parquet artifact (defaults to `path_of_docs` when omitted).
- `output_filename` (`str`): Base output filename for the created Parquet file (must be a basename without path separators; a `.parquet` suffix is optional and is appended when omitted). Default: `"cotahist_extracted"`.
- `processing_mode` (`str`): Both modes use bounded batches and the same Parquet schema. `"fast"` allows concurrent sources within resource limits; `"slow"` uses one source worker and smaller batches. Default: `"fast"`.
- `verbose` (`bool`): When `True` (default), prints a formatted summary to stdout.

**Returns**:

- `ExtractionResultB3` (`TypedDict`): A result mapping with these keys:
  - `success` (`bool`): `True` if extraction completed without errors.
  - `message` (`str`): Human-readable execution outcome summary.
  - `total_files` (`int`): Number of annual inputs resolved for the request.
  - `success_count` (`int`): Number of sources included in committed output.
  - `error_count` (`int`): Number of entries in `errors`.
  - `total_records` (`int`): Committed output row count.
  - `output_file` (`str`): Newly committed output path; empty on failure.
  - `assets` (`list[str]`): Asset categories filtered during run.
  - `processing_mode` (`str`): Execution mode selected (`"fast"` or `"slow"`).
  - `elapsed_time` (`float`): Elapsed execution time in seconds.
  - `schema_version` (`int`): Parquet schema version (`2`).
  - `integrity` (`B3IntegrityReport`): Requested coverage, sources, counts,
    verification, warnings, and published-artifact hash. See the
    [complete key contract](../reference/b3-api.md#integrity-report).
- `errors` (`dict[str, str]`): Dictionary mapping failed files to failure error messages. The key is always present and may be empty.

Official B3 downloads use ZIP archives, but the API accepts both
`COTAHIST_A{YYYY}.ZIP` and the uncompressed `COTAHIST_A{YYYY}.TXT`. When both
formats exist for the same year, both are fully validated. ZIP is selected
only when their uncompressed contents are identical; different contents cause
failure.
`output_filename` must be a basename without path separators; the `.parquet`
suffix is optional and is appended only when omitted.

A missing requested year returns `success=False`, lists missing years in
`integrity.missing_years`, and does not publish a new output. An empty directory
reports zero resolved files and every requested year as missing.

If every requested source is valid and the filter excludes all quotations,
extraction publishes an empty result (`success=True`). On preflight failure,
`integrity` retains previously validated sources and missing years;
`success_count` and `total_records` remain zero.

All `01` records are validated before filtering. TPMERC `021` is selected with
`lote_bloco`; `todos` also includes unknown numeric codes. Every requested year
must be present, and the complete output is read back before publication. See
the [B3 v2 schema reference](../reference/b3-schema-v2.en.md) and
[migration guide](../user-guide/migration-pyarrow-integrity.en.md).

**`extract_async()`**

```python
async def extract_async(
    self,
    path_of_docs: str,
    assets_list: list[str] | None = None,
    initial_year: int | None = None,
    last_year: int | None = None,
    destination_path: str | None = None,
    output_filename: str = "cotahist_extracted",
    processing_mode: str = "fast",
    verbose: bool = True,
) -> ExtractionResultB3:
    ...
```

Asynchronous counterpart to `extract()`. Use when calling from inside an existing `asyncio` event loop.

**`get_available_assets()`**

```python
def get_available_assets(self) -> list[str]:
    ...
```

Returns the supported asset filter aliases:

- `'ações'`: Equities (cash and fractional market)
- `'etf'`: Exchange Traded Funds
- `'opções'`: Options (call and put)
- `'termo'`: Term-market contracts
- `'exercicio_opcoes'`: Options exercise
- `'forward'`: Forward contracts (TPMERC 050 and 060)
- `'leilao'`: Auction market
- `'lote_bloco'`: Block lot (TPMERC `021`)
- `'todos'`: Every valid numeric TPMERC

The Portuguese strings above are canonical `assets_list` values; validation
lowercases the input. The aliases `bdr` and `futuro` are not in this catalog;
filtering selects market types rather than classifying issuers or instruments
within a TPMERC code.

**`get_available_years()`**

```python
def get_available_years(self) -> dict[str, int]:
    ...
```

Returns a dictionary with `minimal_year` (`1986`) and `current_year` (the current
system year).

______________________________________________________________________

## Related References

For detailed contracts, see:

- [CVM API](../reference/cvm-api.md) — Inputs, results, and extraction behavior
- [B3 API](../reference/b3-api.md) — Local inputs, filtering, results, and execution
- [Exceptions](../reference/exceptions.md) — Exception types and returned failures
