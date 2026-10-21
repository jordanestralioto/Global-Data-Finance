# CVM API Reference

Inputs, results, and persistence contracts for `FundamentalStocksDataCVM`.
For a first run, see the [CVM guide](../user-guide/cvm-docs.md).

______________________________________________________________________

## FundamentalStocksDataCVM

### Import

```python
from globaldatafinance import FundamentalStocksDataCVM
```

### Construction and configuration

```python
def __init__(self, *, settings: Settings | None = None) -> None:
    ...
```

Import `Settings` from `globaldatafinance.core.config`. The optional argument
injects an immutable snapshot; with `None`, the client creates a snapshot from
the current environment. The `settings` property returns the configuration
used. See [configuration](../dev-guide/advanced-usage.md).

### `download()`

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

**Description**: Downloads CVM document archives into a local directory.

**Parameters**:

| Parameter             | Type                | Required | Default | Description                                |
| --------------------- | ------------------- | -------- | ------- | ------------------------------------------ |
| `destination_path`    | `str`               | Yes      | -       | Target local filesystem output folder      |
| `list_docs`           | `list[str] \| None` | No       | `None`  | Targeted document codes (None = fetch all) |
| `initial_year`        | `int \| None`       | No       | `None`  | Starting year (None = earliest available)  |
| `last_year`           | `int \| None`       | No       | `None`  | Last year, inclusive (None = current year) |
| `automatic_extractor` | `bool`              | No       | `False` | Convert to Parquet through PyArrow         |

With `automatic_extractor=True`, every CVM column is Arrow `string`
under the `exact-text-v1` contract. Each field keeps its original text:
decimals, leading zeroes, signs, case, and literals such as `N/A`, `NULL`, or
`None`; empty fields are `""`. Header-only CSVs produce zero rows with string
columns. `QUOTE_NONE` retains literal quotes. Short rows receive trailing
empty fields; excess fields, empty or duplicate headers, more than 4,096
columns, and physical records exceeding 8 MiB UTF-8 fail explicitly.

The SHA-256 of all decoded records is compared with reopened Parquet content
before publication. Files include page checksums, ZIP and CSV member identity
in metadata, and `fsync` synchronization. Confirmation requires all expected
Parquets and their association with the ZIP. Row groups use an estimated
16 MiB budget, up to 50,000 rows.
Reads stay on the same opened ZIP and the source is checked again before
publication. Removed or renamed CSVs require regeneration into a clean
destination when obsolete Parquets from that archive remain.

The original ZIP is retained after success and failure, including non-CSV
members. Concurrent calls to one destination fail before ZIP promotion.
After abrupt termination, `.cvm-write-lock` requires explicit inspection
before recovery. Multi-Parquet publication is recoverable as a batch; its
visibility to concurrent readers is not instantaneously atomic. Undeclared
encoding can be ambiguous, and accounting consistency is not inferred.

This schema change requires [consumer migration](../user-guide/migration-cvm-exact-text.en.md).

The local filename is the URL path's final component after one
percent-encoding decode. The library rejects separators, invalid Win32
characters, controls, trailing periods or spaces, and reserved DOS devices
such as `CON`, `AUX`, `COM1`, and `LPT1` with `SecurityError`, before starting
the download or creating staging.

**Returns**:

Returns a `DownloadResultCVM` object:

- `success_count_downloads: int` — Total count of successfully completed download tasks.
- `error_count_downloads: int` — Total count of failed download tasks.
- `successful_downloads: list[str]` — List of completed document identifiers in `{DOC}_{YEAR}` format (e.g., `"DFP_2023"`).
- `failed_downloads: dict[str, str]` — Dictionary mapping failed items to specific error messages.
- `elapsed_time: float` — Total execution duration in seconds.
- `has_errors() -> bool` — Boolean indicator signaling whether failures occurred.

**Synchronous Exceptions**:

- `InvalidDocumentName`: Unsupported document code.
- `InvalidDocumentType`: An item in `list_docs` is not a string.
- `InvalidFirstYear`: Invalid initial year.
- `InvalidLastYear`: Invalid final year.
- `TypeError`: Invalid type for `list_docs`, `automatic_extractor`, or a path.
- `InvalidDestinationPathError`: Empty or whitespace-only path.
- `PathIsNotDirectoryError`: A document or year directory already exists as a file.
- `PathPermissionError`: No permission to create or write to the destination.
- `PathCreationError`: Destination creation failed, including when a parent is a file.
- `SecurityError`: URL-derived filename or local destination is unsafe.

Transient HTTP transmission failures during asynchronous downloads are handled
by the internal retry mechanism. When retries are exhausted, each final failure
is consolidated in `DownloadResultCVM.failed_downloads` without terminating
the remaining downloads.

If the output directory disappears, becomes a file, or encounters an I/O error
while creating the lock after the download, finalization records the failure
in `failed_downloads` and continues other destinations. Replacement by another
directory or a symbolic link raises `SecurityError`.

On systems supporting directory-descriptor-relative operations and child access
through descriptor-backed paths, the lock,
ZIP promotion, and cleanup remain bound to the opened directory. Automatic
extraction reuses that ownership to read the ZIP, write staging, and publish
Parquet. Readers and writers use descriptor-backed paths through `/proc/self/fd`
or `/dev/fd`; if both are unavailable, extraction raises `SecurityError` before
writing data through a mutable pathname. Manifests retain the original relative
names. Cleanup preserves staging and logs a diagnostic when it cannot confirm
the originally validated directory identity.

On systems without this complete support, the library verifies directory identity
before path-based operations. Child traversal is checked before comparing the
virtual path's identity or creating the lock; systems such as macOS, whose
`/dev/fd` does not support this access, use this fallback. Concurrent changes by
processes that do not follow the ownership protocol do not have the same atomic
guarantee on those systems.

URL selection respects each document's first year: IPE in 2003; DFP, FCA, and
FRE in 2010; ITR in 2011; CGVN and VLMO in 2018. A mixed interval does not
generate URLs for years before the document starts.

**Execution Example**:

```python
cvm = FundamentalStocksDataCVM()
result = cvm.download(
    destination_path="/data/cvm",
    list_docs=["DFP", "ITR"],
    initial_year=2022,
    last_year=2023,
    automatic_extractor=True
)
if result.has_errors():
    raise RuntimeError(result.failed_downloads)
```

### `async_download()`

Async counterpart of `download()`, with identical arguments, defaults, and
result. In notebooks or applications with an active event loop, use
`await client.async_download(...)` instead of the synchronous wrapper. The full
signature is also in the [API overview](../dev-guide/api-reference.md).

### `get_available_docs()`

```python
def get_available_docs(self) -> dict[str, str]:
    ...
```

**Description**: Returns document codes and their descriptions.

**Returns**: Dictionary `{code: description}`. Descriptions are the English
text returned by the library; the table below provides Portuguese document names.

**Execution Example**:

```python
docs = cvm.get_available_docs()
# Returns: {'DFP': '(Standardized Financial Statements) ...', ...}
```

### `get_available_years()`

```python
def get_available_years(self) -> AvailableYearsInfoCVM:
    ...
```

**Description**: Returns supported first years and the current system year.

**Returns (`AvailableYearsInfoCVM`)**: A `NamedTuple` with these attributes:

- `general_min_year` (`int`): Earliest year for general accounting forms (`DFP`, `FRE`, `FCA`) — `2010`.
- `itr_min_year` (`int`): Earliest year for interim quarterly reports (`ITR`) — `2011`.
- `cgvn_vlmo_min_year` (`int`): Earliest year for governance disclosures (`CGVN`, `VLMO`) — `2018`.
- `current_year` (`int`): Current system year.
- `ipe_min_year` (`int`, property): Earliest IPE year — `2003`; accessed as a tuple property.

**Execution Example**:

```python
years = cvm.get_available_years()
print(f"General docs floor: {years.general_min_year}")
print(f"ITR docs floor: {years.itr_min_year}")
print(f"Current year: {years.current_year}")
```

______________________________________________________________________

## Supported Document Classifications

| Acronym Code | Complete Legal Title                | Available Since |
| ------------ | ----------------------------------- | --------------- |
| DFP          | Demonstração Financeira Padronizada | 2010            |
| ITR          | Informação Trimestral               | 2011            |
| FRE          | Formulário de Referência            | 2010            |
| FCA          | Formulário Cadastral                | 2010            |
| CGVN         | Código de Governança                | 2018            |
| VLMO         | Valores Mobiliários                 | 2018            |
| IPE          | Informações Periódicas e Eventuais  | 2003            |

______________________________________________________________________

## Related Documentation

- [CVM User Guide](../user-guide/cvm-docs.md)
- [Exception Hierarchy](exceptions.md)
