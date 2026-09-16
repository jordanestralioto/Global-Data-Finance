# CVM API - Technical Specification

Detailed technical specification governing the CVM corporate disclosure API.

______________________________________________________________________

## FundamentalStocksDataCVM

### Primary Class Definition

```python
class FundamentalStocksDataCVM:
    """High-level facade for CVM financial statement ingestion."""
```

### Public Methods

#### `download()`

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

**Description**: Downloads official CVM disclosure packages into a targeted filesystem directory.

**Parameters**:

| Parameter             | Type                | Required | Default | Description                                |
| --------------------- | ------------------- | -------- | ------- | ------------------------------------------ |
| `destination_path`    | `str`               | Yes      | -       | Target local filesystem output folder      |
| `list_docs`           | `list[str] \| None` | No       | `None`  | Targeted document codes (None = fetch all) |
| `initial_year`        | `int \| None`       | No       | `None`  | Starting year (None = earliest available)  |
| `last_year`           | `int \| None`       | No       | `None`  | Ending fiscal year (None = current year)   |
| `automatic_extractor` | `bool`              | No       | `False` | Convert to Parquet through PyArrow         |

With `automatic_extractor=True`, CVM CSV keeps the `QUOTE_NONE` dialect:
quotes are literal, short rows receive trailing nulls only, and excess rows
fail. A header-only CSV produces an empty Parquet with Arrow `null` fields and
no `b'pandas'` metadata. Parquets from the same ZIP use recoverable batch
publication, not instant visibility atomicity for concurrent readers.

The local filename is the URL path's final component after one
percent-encoding decode. The library rejects separators, invalid Win32
characters, controls, trailing periods or spaces, and reserved DOS devices
such as `CON`, `AUX`, `COM1`, and `LPT1` with `SecurityError`, before starting
the download or creating staging.

**Return Structure**:

Returns a `DownloadResultCVM` object containing consolidated download metrics:

- `success_count_downloads: int` — Total count of successfully completed download tasks.
- `error_count_downloads: int` — Total count of failed download tasks.
- `successful_downloads: list[str]` — List of completed document identifiers in `{DOC}_{YEAR}` format (e.g., `"DFP_2023"`).
- `failed_downloads: dict[str, str]` — Dictionary mapping failed items to specific error messages.
- `elapsed_time: float` — Total execution duration in seconds.
- `has_errors() -> bool` — Boolean indicator signaling whether failures occurred.

**Synchronous Exceptions**:

- `InvalidDocumentName`: Supplied document code string falls outside whitelist.
- `InvalidFirstYear`: Requested initial year below historic floor or above upper boundaries.
- `InvalidLastYear`: Ending year preceded initial year or surpassed active year limits.
- `InvalidDestinationPathError`: Destination filesystem directory access blocked or restricted.
- `SecurityError`: URL-derived filename or local destination is unsafe.

Transient HTTP transmission failures during asynchronous downloads are handled
by the internal retry mechanism. When retries are exhausted, each final failure
is consolidated in `DownloadResultCVM.failed_downloads` without terminating
the remaining downloads.

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
```

#### `get_available_docs()`

```python
def get_available_docs(self) -> dict[str, str]:
    ...
```

**Description**: Retrieves mapping catalog connecting short acronym codes to full Portuguese administrative descriptions.

**Return Structure**: Dictionary `{acronym_code: full_legal_title}`

**Execution Example**:

```python
docs = cvm.get_available_docs()
# Returns: {'DFP': 'Demonstração Financeira Padronizada', ...}
```

#### `get_available_years()`

```python
def get_available_years(self) -> AvailableYearsInfoCVM:
    ...
```

**Description**: Queries structural historical year boundary metrics across supported filing categories.

**Return Structure (`AvailableYearsInfoCVM`)**: `NamedTuple` container featuring:

- `general_min_year` (`int`): Earliest year for general accounting forms (`DFP`, `FRE`, `FCA`, `IPE`) — `2010`.
- `itr_min_year` (`int`): Earliest year for interim quarterly reports (`ITR`) — `2011`.
- `cgvn_vlmo_min_year` (`int`): Earliest year for governance disclosures (`CGVN`, `VLMO`) — `2018`.
- `current_year` (`int`): Real-time operational system year limit.

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
| IPE          | Informações Periódicas e Eventuais  | 2010            |

______________________________________________________________________

## Related Documentation

- [CVM User Guide](../user-guide/cvm-docs.md)
- [Exception Hierarchy](exceptions.md)
