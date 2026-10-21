# Exceptions and failure results

This reference distinguishes input errors, failures collected in results, and
lower-level exceptions. See also the [CVM](cvm-api.md) and [B3](b3-api.md)
contracts.

## Handling a public call

| Situation | Behavior |
| --- | --- |
| Invalid parameter or path | Validation may raise an exception before the main operation |
| A CVM download fails | The result records its identifier and cause in `failed_downloads`; other downloads continue |
| A B3 input is missing, corrupt, or invalid | The facade returns `success=False`, details in `errors`, and no new `output_file` |
| An empty B3 directory | Returns zero `total_files` and requested years in `integrity.missing_years` |
| Valid B3 sources with no quotations after filtering | Returns success and publishes an empty Parquet with the B3 schema |
| B3 async cancellation before the commit decision | Waits for workers, cleans temporary files, and propagates `asyncio.CancelledError` |

Check `result.has_errors()` for CVM and `result["success"]` for B3 before
consuming artifacts. [Transactional publication](transactional-publication.md)
describes recovery, cancellation, and visibility limits.

## Shared exceptions

Import these types from `globaldatafinance.macro_exceptions`.

| Exception | Base | Condition |
| --- | --- | --- |
| `InvalidDestinationPathError` | `ValueError` | Empty or whitespace-only path |
| `PathIsNotDirectoryError` | `ValueError` | A required directory is missing or is a file |
| `PathPermissionError` | `OSError` | No permission to create or write to the destination |
| `PathCreationError` | `OSError` | Destination creation fails for another I/O reason |
| `FileWriteError` | `OSError` | File write failure |
| `ParquetWriteError` | `OSError` | Filesystem failure while writing or reopening Parquet |
| `DiskFullError` | `OSError` | Insufficient destination storage |
| `ExtractionError` | `Exception` | Extraction or content-validation failure |
| `CorruptedZipError` | `ExtractionError` | Corrupt or unreadable ZIP |
| `SecurityError` | `Exception` | Violation of path, file, or extraction policy |
| `NetworkError` | `Exception` | Transport failure translated by the CVM adapter |
| `DownloadTimeoutError` | `Exception` | CVM download timeout |
| `EmptyDirectoryError` | `Exception` | Shared type representing the absence of input files |

A sensitive destination raises `SecurityError`. Type errors may raise the
built-in `TypeError`. The B3 facade reports an empty directory through its
result as described above; catching `EmptyDirectoryError` does not replace
that check.

During staged CVM Parquet writes, filesystem failures other than `ENOSPC`
become `ParquetWriteError` with the original cause preserved; `ENOSPC` becomes
`DiskFullError`. Download aggregation records `ParquetWrite: ...` when
applicable and retains the ZIP for diagnosis. CSV, schema, count, and integrity
failures continue to follow the extraction contract.

The CVM adapter translates transport failures, applies the
[retry policy](../dev-guide/retry-strategy.md), and collects persistent failures
in `failed_downloads`. Catching `NetworkError` synchronously around the facade
is not how callers identify these failed downloads.

## CVM exceptions

These types are defined in
`globaldatafinance.brazil.cvm.fundamental_stocks_data.errors`.
`CvmError` inherits from `Exception`; every other type in this table inherits
from `CvmError`.

| Exception | Condition |
| --- | --- |
| `InvalidDocumentName` | Unsupported CVM document code |
| `InvalidDocumentType` | An item in `list_docs` is not a string |
| `InvalidFirstYear` | Initial year is not an integer, is below 2003, or exceeds the current year |
| `InvalidLastYear` | Final year is not an integer, exceeds the current year, or precedes the initial year |
| `EmptyDocumentListError` | Internal resolution type for an empty selection |
| `MissingDownloadUrlError` | Internal resolution type for a document without a configured URL |

An outer `list_docs` value other than a list or `None` raises `TypeError`.
`None` and `[]` select all document types. The catalog accepts `DFP`, `ITR`,
`FCA`, `FRE`, `CGVN`, `VLMO`, and `IPE`.

The global year-validation floor is 2003. Per-document first years filter the
URLs: a valid interval before DFP begins, for example, generates no DFP URLs
for those years. See the first years in the
[CVM reference](cvm-api.md#supported-document-classifications).

## B3 exceptions

These types are defined in
`globaldatafinance.brazil.b3_data.historical_quotes.errors`.
`B3Error(Exception)` is the base for the validation exceptions in this table:

| Exception | Condition |
| --- | --- |
| `EmptyAssetListError` | `assets_list` is empty or not a list; `None` selects `todos` |
| `InvalidAssetsName` | Non-string item or unknown alias |
| `InvalidFirstYear` | Initial year outside 1986 through the current year, or an invalid type |
| `InvalidLastYear` | Invalid final year, above the current year, or before the initial year |
| `InvalidProcessingMode` | Mode other than `fast` or `slow` |
| `InvalidOutputFilename` | Invalid output name or a name that is not a basename |

Accepted aliases: `ações`, `etf`, `opções`, `termo`, `exercicio_opcoes`,
`forward`, `leilao`, `lote_bloco`, and `todos`. Validation normalizes letter
case. The output name accepts an optional `.parquet` suffix, appended when
absent. Path separators and traversal are rejected.

The module also defines `CotahistCatalogError(ValueError)` and
`CotahistPreflightError(ExtractionError)` for internal resolution and preflight.
Neither inherits from `B3Error`. The facade converts these input-source
failures into unsuccessful results. Catching `B3Error` handles input validation;
processing failures require checking `result["success"]` and `errors`.

The CVM and B3 `InvalidFirstYear` and `InvalidLastYear` types are distinct
classes. Source-specific exceptions are imported from their source modules;
the `globaldatafinance` root exports the facades and `ExtractionResultB3`.

## Handling examples

### CVM

This example requires access to CVM and a writable destination.

```python
from globaldatafinance import FundamentalStocksDataCVM
from globaldatafinance.brazil.cvm.fundamental_stocks_data.errors import CvmError
from globaldatafinance.macro_exceptions import SecurityError

try:
    result = FundamentalStocksDataCVM().download(
        destination_path="./data_cvm",
        list_docs=["DFP"],
        initial_year=2023,
        last_year=2023,
    )
except (CvmError, TypeError, ValueError, OSError, SecurityError) as error:
    raise SystemExit(f"CVM request failed: {error}") from error

if result.has_errors():
    raise RuntimeError(result.failed_downloads)
print(f"Downloaded: {result.success_count_downloads}")
```

### B3

Place `COTAHIST_A2023.ZIP` or `.TXT` in the input directory before running.

```python
from globaldatafinance import HistoricalQuotesB3
from globaldatafinance.brazil.b3_data.historical_quotes.errors import B3Error
from globaldatafinance.macro_exceptions import SecurityError


def main() -> None:
    try:
        result = HistoricalQuotesB3().extract(
            path_of_docs="./cotahist_b3",
            assets_list=["ações", "opções"],
            initial_year=2023,
            last_year=2023,
            output_filename="quotes_2023",
        )
    except (B3Error, TypeError, ValueError, OSError, SecurityError) as error:
        raise SystemExit(f"B3 request failed: {error}") from error

    if not result["success"]:
        raise RuntimeError(result["errors"] or result["message"])
    print(f"Rows: {result['total_records']}; output: {result['output_file']}")


if __name__ == "__main__":
    main()
```
