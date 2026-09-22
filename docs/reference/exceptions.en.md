# Exception Reference

Complete catalog of exceptions and error handling contracts in Global-Data-Finance.

______________________________________________________________________

## Overview

Global-Data-Finance adheres to a strict error handling policy:

- **Fail-Fast Parameter Validation**: Invalid input parameters, unknown document codes, unsupported asset classes, or unsafe destination directories synchronously raise typed domain exceptions before any network or file I/O operations commence.
- **Network Resilience**: In asynchronous CVM downloads, transient connection disruptions trigger automatic retries with exponential backoff. Persistent network failures are compiled into the `failed_downloads` attribute of the returned `DownloadResultCVM` without aborting other concurrent tasks.
- **Explicit Hierarchy**: No artificial catch-all exception exists (such as `GlobalDataFinanceError`). Every source domain and infrastructure boundary provides clear, predictable, and typed exception classes.

______________________________________________________________________

## Infrastructure Exceptions (`macro_exceptions`)

Infrastructure exceptions represent cross-cutting errors originating from filesystem interactions, low-level network transports, path security validation, and archive integrity.

### Filesystem & Permissions

#### `InvalidDestinationPathError`

```python
class InvalidDestinationPathError(ValueError):
    """Target destination path is invalid, malformed, or violates security constraints."""
```

- **Inheritance**: `ValueError`
- **When Raised**: Destination path points to a protected system directory, a file rather than a directory, or contains path traversal sequences.

#### `PathIsNotDirectoryError`

```python
class PathIsNotDirectoryError(ValueError):
    """Supplied path is not a valid directory."""
```

- **Inheritance**: `ValueError`

#### `PathPermissionError`

```python
class PathPermissionError(OSError):
    """Insufficient filesystem permissions to create or access directory."""
```

- **Inheritance**: `OSError`

#### `PathCreationError`

```python
class PathCreationError(OSError):
    """Failed to create directory structure on filesystem."""
```

- **Inheritance**: `OSError`

#### `FileWriteError` & `ParquetWriteError`

```python
class FileWriteError(OSError):
    """Failed to write file to disk storage."""


class ParquetWriteError(OSError):
    """Failed to serialize or write Apache Parquet artifact."""
```

- **Inheritance**: `OSError`

During staged CVM Parquet writes, filesystem failures other than `ENOSPC` are
reported as `ParquetWriteError` with the original cause preserved; `ENOSPC`
remains `DiskFullError`. Download aggregation records `ParquetWrite: ...` and
keeps the ZIP for diagnosis.

#### `DiskFullError`

```python
class DiskFullError(OSError):
    """Insufficient storage capacity on destination filesystem."""
```

- **Inheritance**: `OSError`

### Extraction & Archive Operations

#### `EmptyDirectoryError`

```python
class EmptyDirectoryError(Exception):
    """Input directory is physically empty."""
```

- **When Raised**: Only when the input directory is physically empty. A
  directory that is not empty but contains no COTAHIST file for the requested
  year returns an empty result (`success=True`, `total_files=0`,
  `total_records=0`, `output_file=""`, and `errors={}`).

#### `ExtractionError` & `CorruptedZipError`

```python
class ExtractionError(Exception):
    """Error encountered during archive decompression or data extraction."""


class CorruptedZipError(ExtractionError):
    """ZIP archive is corrupted or unreadable."""
```

- **Inheritance**: `CorruptedZipError` inherits from `ExtractionError`.

#### `SecurityError`

```python
class SecurityError(Exception):
    """Security policy violation detected during path or file operations."""
```

### Low-Level Network & HTTP
#### `NetworkError` & `DownloadTimeoutError`

```python
class NetworkError(Exception):
    """Network transport disruption translated during CVM downloads."""


class DownloadTimeoutError(Exception):
    """Socket read or connection timeout translated during CVM downloads."""
```

- **Origin and Pipeline Translation**:
  1. The low-level HTTP adapter (`RequestsAdapter.async_download_file`) executes streaming transfers via `httpx` and may propagate transport failures (`httpx.RequestError`, `httpx.HTTPStatusError`, `httpx.TimeoutException`, `ConnectionError`) or filesystem write faults.
  2. The CVM download adapter (`AsyncDownloadAdapterCVM._download_with_retry`) intercepts these low-level transport errors and translates them into domain exceptions `NetworkError` and `DownloadTimeoutError`.
  3. `RetryStrategy` applies automated retries with exponential backoff up to configured retry limits.
  4. Persistent failures after retry exhaustion are consolidated into the `result.failed_downloads` dictionary of `DownloadResultCVM` without aborting concurrent transfers of other years or document types.

______________________________________________________________________

## CVM Domain Exceptions (`fundamental_stocks_data.errors`)

All CVM-specific exceptions inherit from `CvmError`.

```python
class CvmError(Exception):
    """Base exception class for all CVM domain failures."""
```

### `InvalidDocumentName` & `InvalidDocumentType`

```python
class InvalidDocumentName(CvmError):
    """Supplied CVM document identifier is unrecognized."""


class InvalidDocumentType(CvmError):
    """Invalid parameter type supplied for document list."""
```

- **When Raised**: Document code does not belong to the official catalog (`"DFP"`, `"ITR"`, `"FCA"`, `"FRE"`, `"CGVN"`, `"VLMO"`, `"IPE"`), or parameter is not a valid list/string.

### `InvalidFirstYear` & `InvalidLastYear`

```python
class InvalidFirstYear(CvmError):
    """Starting fiscal year falls below minimum historical boundary."""


class InvalidLastYear(CvmError):
    """Ending fiscal year is invalid or precedes starting year."""
```

- **When Raised**: Year is below the historical floor for that document type or exceeds current system year.

### `EmptyDocumentListError` & `MissingDownloadUrlError`

```python
class EmptyDocumentListError(CvmError):
    """No document download targets remained after internal resolution."""


class MissingDownloadUrlError(CvmError):
    """Download URL prefix not registered for requested document."""
```

- **Semantic Note**: On the public facade `FundamentalStocksDataCVM.download()`, supplying `list_docs=None` or `list_docs=[]` downloads **all available document types**. `EmptyDocumentListError` is an internal domain exception used when URL resolution produces an empty set.

______________________________________________________________________

## B3 Domain Exceptions (`historical_quotes.errors`)

Exceptions governing historical market exchange quote processing. Every concrete
class inherits from `B3Error`, the source-specific catch boundary.

### `InvalidAssetsName` & `EmptyAssetListError`

```python
class B3Error(Exception):
    """Base class for B3 domain exceptions."""


class InvalidAssetsName(B3Error):
    """Asset class keyword is unrecognized by B3 extractor."""


class EmptyAssetListError(B3Error):
    """Required asset class list parameter was supplied empty."""
```

- **When Raised**: `assets_list` is empty or contains identifiers outside the supported whitelist (`'ações'`, `'etf'`, `'opções'`, `'termo'`, `'exercicio_opcoes'`, `'forward'`, `'leilao'`).

### `InvalidProcessingMode`

```python
class InvalidProcessingMode(B3Error):
    """Invalid execution profile (must be 'fast' or 'slow')."""
```

### `InvalidOutputFilename`

```python
class InvalidOutputFilename(B3Error):
    """Output filename is invalid (must be a basename without path segments)."""
```

- **When Raised**: `output_filename` contains directory separators (`/` or `\`) or traversal segments (`..`). The `.parquet` suffix is optional and is appended automatically when omitted.

### `InvalidFirstYear` & `InvalidLastYear` (B3)

```python
class InvalidFirstYear(B3Error):
    """Starting year precedes historical floor (1986) or exceeds current year."""


class InvalidLastYear(B3Error):
    """Ending year precedes initial year or exceeds current system year."""
```

______________________________________________________________________

## Exception Class Hierarchy

```
Exception
├── macro_exceptions
│   ├── EmptyDirectoryError
│   ├── NetworkError
│   ├── DownloadTimeoutError
│   ├── ExtractionError
│   │   └── CorruptedZipError
│   └── SecurityError
├── CvmError
│   ├── InvalidDocumentName
│   ├── InvalidDocumentType
│   ├── InvalidFirstYear
│   ├── InvalidLastYear
│   ├── EmptyDocumentListError
│   └── MissingDownloadUrlError
└── B3Error
    ├── InvalidAssetsName
    ├── EmptyAssetListError
    ├── InvalidProcessingMode
    ├── InvalidOutputFilename
    ├── InvalidFirstYear
    └── InvalidLastYear

ValueError
├── InvalidDestinationPathError
└── PathIsNotDirectoryError

OSError
├── PathPermissionError
├── PathCreationError
├── FileWriteError
├── ParquetWriteError
└── DiskFullError
```

______________________________________________________________________

## Exception Handling Examples

### Example 1: Handling CVM Operations

```python
from globaldatafinance import FundamentalStocksDataCVM
from globaldatafinance.brazil.cvm.fundamental_stocks_data.errors import (
    CvmError,
    InvalidDocumentName,
    InvalidFirstYear,
    InvalidLastYear,
)
from globaldatafinance.macro_exceptions import (
    InvalidDestinationPathError,
    PathPermissionError,
)

cvm = FundamentalStocksDataCVM()

try:
    # 1. Synchronous parameter and directory validation
    result = cvm.download(
        destination_path="/data/cvm",
        list_docs=["DFP"],
        initial_year=2022,
        last_year=2023,
    )

    # 2. Result evaluation (network failures are retried and compiled into failed_downloads)
    if result.has_errors():
        print(
            f"Encountered {result.error_count_downloads} persistent failure(s):"
        )
        for doc_key, message in result.failed_downloads.items():
            print(f"  • {doc_key}: {message}")
    else:
        print(
            f"Success: {result.success_count_downloads} files downloaded cleanly."
        )

except InvalidDocumentName as exc:
    print(f"Invalid document parameter: {exc}")
except (InvalidFirstYear, InvalidLastYear) as exc:
    print(f"Temporal parameter boundary violation: {exc}")
except InvalidDestinationPathError as exc:
    print(f"Unsafe or invalid destination path: {exc}")
except PathPermissionError as exc:
    print(f"Insufficient filesystem permission: {exc}")
except CvmError as exc:
    print(f"General CVM domain failure: {exc}")
```

### Example 2: Handling B3 Operations

```python
from globaldatafinance import HistoricalQuotesB3
from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    EmptyAssetListError,
    InvalidAssetsName,
    InvalidFirstYear,
    InvalidLastYear,
    InvalidOutputFilename,
    InvalidProcessingMode,
)
from globaldatafinance.macro_exceptions import (
    EmptyDirectoryError,
    InvalidDestinationPathError,
)

b3 = HistoricalQuotesB3()

try:
    result = b3.extract(
        path_of_docs="/data/cotahist",
        assets_list=["ações", "etf"],
        initial_year=2023,
        output_filename="quotes_2023",
        processing_mode="fast",
    )
    print(
        f"Extracted {result['total_records']:,} rows into {result['output_file']}"
    )

except EmptyAssetListError:
    print("Asset classes filter list cannot be empty.")
except InvalidAssetsName as exc:
    print(f"Unrecognized asset class keyword: {exc}")
except (InvalidFirstYear, InvalidLastYear) as exc:
    print(f"Invalid historical year range: {exc}")
except InvalidOutputFilename as exc:
    print(f"Invalid output filename basename: {exc}")
except InvalidProcessingMode as exc:
    print(f"Processing mode must be 'fast' or 'slow': {exc}")
except EmptyDirectoryError as exc:
    print(f"Source directory contains no COTAHIST archives: {exc}")
except InvalidDestinationPathError as exc:
    print(f"Invalid destination directory: {exc}")
```

______________________________________________________________________

See also:

- [CVM API Reference](cvm-api.md)
- [B3 API Reference](b3-api.md)
- [FAQ](../user-guide/faq.md)
