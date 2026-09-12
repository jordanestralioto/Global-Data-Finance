# API Reference

Complete high-level architectural documentation reference covering the public surface of Global-Data-Finance.

______________________________________________________________________

## Module `globaldatafinance` (Public Root Exports)

The primary entrypoint classes and contracts are exposed directly at the top-level package boundary:

```python
from globaldatafinance import (
    FundamentalStocksDataCVM,
    HistoricalQuotesB3,
    ExtractionResultB3,
)
```

______________________________________________________________________

### `FundamentalStocksDataCVM`

Public interface facade responsible for managing regulatory CVM financial filing downloads and Parquet extractions.

#### Methods

**`__init__()`**

```python
def __init__(self) -> None:
    ...
```

Initializes the CVM client facade configuring standard async down-streaming adapters and underlying use case pipelines.

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
- `initial_year` (`int`, optional): Starting historical fiscal year (inclusive). If `None`, defaults to the earliest available year for each document type.
- `last_year` (`int`, optional): Ending fiscal year (inclusive). Defaults to the active system year.
- `automatic_extractor` (`bool`): When set to `True`, deconstructs downloaded ZIP archives into columnar Apache Parquet files. Default: `False`.

When enabled, the CVM extractor uses PyArrow and the `QUOTE_NONE` CSV dialect.
Short rows receive trailing nulls only, excess rows fail, and a header-only CSV
produces an empty Parquet with Arrow `null` fields. Its multi-Parquet batch is
recoverably published; concurrent readers do not get instant visibility
atomicity.

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

Returns an introspectable dictionary mapping permissible document acronym codes (e.g., `"DFP"`, `"ITR"`, `"FCA"`, `"FRE"`, `"CGVN"`, `"VLMO"`, `"IPE"`) to their descriptive Portuguese legal classifications.

**`get_available_years()`**

```python
def get_available_years(self) -> AvailableYearsInfoCVM:
    ...
```

Returns an `AvailableYearsInfoCVM` namedtuple summarizing permissible temporal starting floors and current operating system year limits across distinct document categories:

- `general_min_year` (`int`): Minimum available year for standard documents (e.g. 2010).
- `itr_min_year` (`int`): Minimum available year for quarterly ITR filings (e.g. 2011).
- `cgvn_vlmo_min_year` (`int`): Minimum available year for CGVN / VLMO filings (e.g. 2018).
- `current_year` (`int`): Active system calendar year.

Also supports dictionary conversion via `years._asdict()`.

______________________________________________________________________

### `HistoricalQuotesB3`

Public interface facade governing historical market exchange quote extraction from official B3 COTAHIST repositories.

#### Methods

**`__init__()`**

```python
def __init__(self) -> None:
    ...
```

Initializes the B3 extraction facade and registers underlying asset classification mappers and extraction service pipelines.

**`extract()`**

```python
def extract(
    self,
    path_of_docs: str,
    assets_list: list[str],
    initial_year: int | None = None,
    last_year: int | None = None,
    destination_path: str | None = None,
    output_filename: str = "cotahist_extracted",
    processing_mode: str = "fast",
    verbose: bool = True,
) -> ExtractionResultB3:
    ...
```

Parses COTAHIST ZIP or TXT archives (`COTAHIST_A{YYYY}.ZIP` or `.TXT`), extracts transaction registers corresponding to selected asset classifications, and compiles them directly into a consolidated Apache Parquet output file. The public method returns an `ExtractionResultB3` mapping with operation status, counts, errors, and the output artifact path; it does not return a DataFrame as its primary contract.

**Parameters**:

- `path_of_docs` (`str`): Source directory enclosing target raw COTAHIST archives (`COTAHIST_A{YYYY}.ZIP` or `.TXT`).
- `assets_list` (`list[str]`): Required asset category filtering tags (e.g., `["ações", "etf"]`).
- `initial_year` (`int`, optional): Historical beginning fiscal year (lower bound floor: 1986).
- `last_year` (`int`, optional): Ending fiscal year (defaults to current system operational year).
- `destination_path` (`str`, optional): Custom directory destination for the generated Parquet artifact (defaults to `path_of_docs` when omitted).
- `output_filename` (`str`): Base output filename for the created Parquet file (must be a basename without path separators; a `.parquet` suffix is optional and is appended when omitted). Default: `"cotahist_extracted"`.
- `processing_mode` (`str`): Computational execution mode: `"fast"` (multi-threaded in-memory processing) or `"slow"` (minimal RAM incremental stream processing). Default: `"fast"`.
- `verbose` (`bool`): When `True` (default), prints a formatted summary to stdout.

**Returns**:

- `ExtractionResultB3` (`TypedDict`): A diagnostic mapping containing runtime confirmation metrics:
  - `success` (`bool`): `True` if extraction completed without errors.
  - `message` (`str`): Human-readable execution outcome summary.
  - `total_files` (`int`): Total number of input files processed (ZIP or TXT).
  - `success_count` (`int`): Count of successfully parsed input files.
  - `error_count` (`int`): Count of input files that failed during processing.
  - `total_records` (`int`): Total number of transaction rows extracted.
  - `output_file` (`str`): Absolute filesystem path to generated Parquet file.
  - `assets` (`list[str]`): Asset categories filtered during run.
  - `processing_mode` (`str`): Execution mode selected (`"fast"` or `"slow"`).
  - `elapsed_time` (`float`): Elapsed execution time in seconds.
- `errors` (`dict[str, str]`): Dictionary mapping failed files to failure error messages. The key is always present and may be empty.

Official B3 downloads use ZIP archives, but the API accepts both
`COTAHIST_A{YYYY}.ZIP` and the uncompressed `COTAHIST_A{YYYY}.TXT`. When both
formats exist for the same year, ZIP takes deterministic precedence.
`output_filename` must be a basename without path separators; the `.parquet`
suffix is optional and is appended only when omitted.

`EmptyDirectoryError` is raised only when the input directory is physically
empty. If the directory is not empty but contains no COTAHIST file for the
requested year, the API returns an empty result with `success=True`,
`total_files=0`, `total_records=0`, `output_file=""`, and `errors={}`. Inspect
`total_files` and `total_records` when data presence is required.

A valid input whose records are all filtered by the requested TPMERC also
returns success and publishes an empty Parquet with the B3 schema. In contrast,
an invalid selected record fails with source, member, line, and field context;
the parser never turns invalid data into zero or null.

**`extract_async()`**

```python
async def extract_async(
    self,
    path_of_docs: str,
    assets_list: list[str],
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

Returns a comprehensive list of permissible asset category string parameters supported by extraction filtering rules:

- `'ações'`: Equities (cash and fractional market)
- `'etf'`: Exchange Traded Funds
- `'opções'`: Options (call and put)
- `'termo'`: Term-market contracts
- `'exercicio_opcoes'`: Options exercise
- `'forward'`: Forward contracts (TPMERC 050 and 060)
- `'leilao'`: Auction market

The Portuguese strings above are canonical `assets_list` values and must be
passed exactly as shown. BDRs and Futures are **Planned** and are not accepted
by the current runtime contract.

**`get_available_years()`**

```python
def get_available_years(self) -> dict[str, int]:
    ...
```

Returns dictionary defining available lower temporal boundaries (`minimal_year`: 1986) and upper bound operational limits (`current_year`).

______________________________________________________________________

## Related References

For specialized technical contracts and deep internal structural references, consult:

- [CVM API Specification](../reference/cvm-api.md) - Deep architectural breakdown of CVM processing pipelines
- [B3 API Specification](../reference/b3-api.md) - Detailed technical documentation for B3 extraction contracts
- [Exception Hierarchy](../reference/exceptions.md) - Diagnostic reference covering project exception classes
