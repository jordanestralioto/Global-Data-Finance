# Fundamental Data Module (CVM)

> [!NOTE] This module is part of the `Global-Data-Finance` suite and provides a
> robust interface for automating downloads of regulatory documents from the
> Brazilian Securities and Exchange Commission (CVM - Comissão de Valores
> Mobiliários).

The `fundamental_stocks_data` module is designed to simplify the acquisition of
public data from Brazilian publicly traded companies. It manages the complexity
of dynamic URLs, directory structures, and network resilience, all encapsulated
within a clean and extensible architecture.

## 🎯 Goals and Value

- **Reliable Automation**: Eliminates manual work to fetch files from the CVM
  portal.
- **Failure Management**: Robust retry system and detailed error reporting.
- **Automatic Organization**: Structures downloaded files by document type and
  year, facilitating downstream consumption.
- **Extensibility**: Concrete HTTP adapter (`AsyncDownloadAdapterCVM`)
  constructed directly. When a second implementation emerges (e.g.,
  `WgetDownloadAdapter`), extracting a `Protocol` is straightforward.

## 🏗️ Architecture

Focused module and subpackage layout:

```text
brazil/cvm/fundamental_stocks_data/
├── core.py                   # AvailableDocsCVM, AvailableYearsCVM, DictZipsToDownloadCVM, DownloadResultCVM, UrlDocsCVM
├── client.py                 # Public queries, orchestration, and path validation
├── http.py                   # AsyncDownloadAdapterCVM (httpx async + retry/back-off + integrity check)
├── extract.py                # ParquetExtractorAdapterCVM (extraction boundary)
├── transaction.py            # Staging, backup, and recoverable batch commit
├── csv_pipeline/             # PyArrow chunked CSV parsing and Parquet conversion subpackage
├── errors.py                 # InvalidDocumentName, InvalidFirstYear, InvalidLastYear, MissingDownloadUrlError, etc.
├── download_paths.py         # Validation of URL-derived basenames
├── download_validation.py    # Validation of generated ZIPs and Parquets (structural and data integrity)
└── download_extraction.py    # Extraction delegation and artifact tracking for rollback
```

`DownloadDocumentsUseCaseCVM` orchestrates URL generation, path validation
(`VerifyPathsUseCasesCVM` — raising `SecurityError` for sensitive destinations),
and downloading via the injected `AsyncDownloadAdapterCVM`.

### Key Components

| Module                   | Component                     | Type                  | Responsibility                                                                                                 |
| ------------------------ | ----------------------------- | --------------------- | -------------------------------------------------------------------------------------------------------------- |
| `client.py`              | `DownloadDocumentsUseCaseCVM` | Orchestrator (class)  | Coordinates URL generation, path validation, and download execution (`execute` and `execute_async`). Stateful. |
| `client.py`              | `generate_urls`               | Application function  | Constructs download URLs from `DictZipsToDownloadCVM`.                                                         |
| `client.py`              | `VerifyPathsUseCasesCVM`      | Use case              | Creates destination directory structure. Raises `SecurityError` on sensitive paths.                            |
| `core.py`                | `DownloadResultCVM`           | Result object         | Aggregated result containing successes, failures, and counters (including `elapsed_time`).                     |
| `core.py`                | `DictZipsToDownloadCVM`       | Value object          | Document to URLs per year mapping.                                                                             |
| `http.py`                | `AsyncDownloadAdapterCVM`     | Concrete adapter      | Asynchronous downloads with retry/back-off and extraction delegation.                                          |
| `extract.py`             | `ParquetExtractorAdapterCVM`  | Concrete adapter      | Opens ZIP files and delegates recoverable conversion commit.                                                   |
| `transaction.py`         | `CvmFailureAtomicBatchCommit` | Extraction detail     | Performs staging, validation, backup, and deterministic restoration per batch.                                 |
| `csv_pipeline/`          | `CsvToParquetPipelineCVM`     | Conversion subpackage | PyArrow streaming CSV ingestion and typed Parquet writing in bounded memory chunks (`chunk_size`).             |
| `download_extraction.py` | `extract_downloaded_file`     | Helper / Use case     | Tracks published artifacts and validates download outcome.                                                     |
| `download_validation.py` | `validate_downloaded_file`    | Helper                | Validates integrity and completeness of ZIPs and extracted Parquet files.                                      |

## 🚀 Usage Guide

### Complete Example

```python
from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    AsyncDownloadAdapterCVM,
    DownloadDocumentsUseCaseCVM,
    ParquetExtractorAdapterCVM,
)


def download_cvm_data():
    # 1. Concrete HTTP adapter (httpx async + retry + integrity check)
    repository = AsyncDownloadAdapterCVM(
        file_extractor_repository=ParquetExtractorAdapterCVM()
    )

    # 2. Orchestrator
    downloader = DownloadDocumentsUseCaseCVM(repository=repository)

    print('Starting downloads...')

    # 3. Execution (sync or async via execute_async)
    try:
        resultado = downloader.execute(
            destination_path='./cvm_data',  # Root directory for storage
            list_docs=['DFP', 'ITR', 'FRE'],  # Document types
            initial_year=2022,  # Start year
            last_year=2023,  # End year
            automatic_extractor=True,  # Automatically extract CSVs to Parquet
        )

        # 4. Result Analysis
        print('\nOperation Summary:')
        print(f'⏱️ Elapsed Time: {resultado.elapsed_time:.2f}s')
        print(f'✅ Successes: {resultado.success_count_downloads}')
        print(f'❌ Failures: {resultado.error_count_downloads}')

        if resultado.failed_downloads:
            print('\nFailure details:')
            for doc, erro in resultado.failed_downloads.items():
                print(f' - {doc}: {erro}')

    except Exception as e:
        print(f'Critical error during execution: {e}')


if __name__ == '__main__':
    download_cvm_data()
```

## ⚙️ API Reference

### `DownloadDocumentsUseCaseCVM.execute`

Also available as `execute_async(...)` when running inside an existing event
loop.

| Parameter             | Type        | Required | Description                                                                                                        |
| --------------------- | ----------- | -------- | ------------------------------------------------------------------------------------------------------------------ |
| `destination_path`    | `str`       | Yes      | Base path where per-document directories will be created.                                                          |
| `list_docs`           | `list[str]` | No       | List of document codes to download. Valid values: `DFP`, `ITR`, `FRE`, `FCA`, `CGVN`, `IPE`, `VLMO`. Default: all. |
| `initial_year`        | `int`       | No       | Start year for data collection.                                                                                    |
| `last_year`           | `int`       | No       | End year for data collection.                                                                                      |
| `automatic_extractor` | `bool`      | No       | Whether to extract and convert CSVs into Parquet files automatically via batch commit. Default: `False`.           |

#### Available Document Types

| Code   | Name                              | Description                           |
| ------ | --------------------------------- | ------------------------------------- |
| `DFP`  | Standardized Financial Statements | Balance sheet, DRE, DFC, DVA (annual) |
| `ITR`  | Quarterly Information             | Quarterly financial statements        |
| `FRE`  | Reference Form                    | Corporate governance and filings      |
| `FCA`  | Registration Form                 | Registration details                  |
| `CGVN` | Governance Code                   | Corporate governance                  |
| `IPE`  | Sporadic Information              | Minutes, material facts               |
| `VLMO` | Securities                        | Traded securities                     |

### `DownloadResultCVM` (Return Value)

Object returned by the `execute` and `execute_async` methods, containing:

- `successful_downloads` (`list[str]`): List of completed logical identifiers in
  `{DOC}_{YEAR}` format (e.g., `DFP_2023`), not file paths.
- `failed_downloads` (`dict[str, str]`): Dictionary mapping `{DOC}_{YEAR}`
  identifiers to error messages.
- `elapsed_time` (`float`): Total execution time of the download run in seconds.
- `success_count_downloads` (`int` property): Total count of successful
  downloads.
- `error_count_downloads` (`int` property): Total count of errors.
- `has_errors()` (`bool` method): Returns `True` if any download failed
  (`error_count_downloads > 0`).

### Error Handling

Exceptions defined in
`globaldatafinance.brazil.cvm.fundamental_stocks_data.errors` (re-exported by
the source `__init__.py`):

- `MissingDownloadUrlError`: could not generate a URL for the requested
  document/year.
- `InvalidDocumentName`: unrecognized document type.
- `InvalidFirstYear` / `InvalidLastYear`: invalid year or year outside supported
  range.
- `SecurityError` (from `macro_exceptions`): attempt to write to a sensitive
  path or URL-derived filename that is not portable — defense in
  `VerifyPathsUseCasesCVM` and `download_paths.py`.

> Note: Adapter typing integrity is checked statically via tools such as `mypy`
> and method contract verification (duck typing), promoting clean and direct
> adoption of the concrete adapter (`AsyncDownloadAdapterCVM`).

## 🔧 Troubleshooting

> [!CAUTION] **IP Throttling / Blocking** The CVM website may block IPs that
> issue high volumes of requests in short periods. The infrastructure adapter
> implements backoff pauses between requests.

> [!TIP] **Directory Structure** The system automatically creates subfolders for
> each document type inside `destination_path`. It is not necessary to create
> them manually.

## 🔎 How CVM File Extraction Works

Extraction is orchestrated by **`download_extraction.py`**, initiated by
**`ParquetExtractorAdapterCVM`** in `extract.py`, powered by the
**`csv_pipeline/`** subpackage, and realized through `transaction.py` when
`automatic_extractor=True`. The complete flow is:

1. **Validation of ZIP and CSV members** before any write: resource limits,
   integrity, names, and basename collisions are rejected.
2. **Staging conversion on the same filesystem**: each CSV becomes Parquet in a
   hidden directory; no final destination changes during this phase.
3. **Validation of staged Parquets**: all must have valid content and footers
   before commit.
4. **Deterministic backup and replacement**: existing targets are preserved, and
   staged Parquets are published in stable order.
5. **Recoverable rollback upon failure**: already-modified targets are restored
   in reverse order. If rollback also encounters issues, the recovery directory
   is preserved and reported for manual recovery.
6. **Post-extraction tracking and validation** in `download_extraction.py`: only
   successfully published artifacts are recorded in the download result.

### Why this approach?

- **Batch recoverable commit**: protects existing targets against partial
  failures; does not claim instant atomic visibility for all concurrent readers.
- **Scalability**: chunked processing (`chunk_size`) allows processing large CSV
  files without exhausting system memory.
- **Resilience**: backoff and retries are implemented in the download adapter;
  in extraction, failures are captured and rolled back in a controlled manner.

> **Note**: To disable automatic extraction (e.g., to only download ZIP files),
> configure `automatic_extractor=False` on `downloader.execute(...)` or on the
> public `FundamentalStocksDataCVM` facade.
