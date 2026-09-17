# Historical Quotes Module (B3)

> [!NOTE]
> This module is part of the `Global-Data-Finance` suite and specializes in high-performance historical market data extraction from B3.

The `historical_quotes` module provides a robust solution for processing historical series files (COTAHIST) from B3. It abstracts the complexity of the legacy positional file layout, offering a modern and typed interface for financial data extraction. Internally, it combines focused single-responsibility modules with specialized subpackages for streaming orchestration and Parquet writing, without reproducing generic `domain`/`application`/`infra` layers.

## 🎯 Goals and Value

- **Layout Abstraction**: Eliminates the need to know the positional layout (bytes/offsets) of B3 files.
- **Performance**: Employs optimized read strategies and columnar output writing (Parquet).
- **Integrity**: Strict input parameter validation and domain-specific error handling with contextual record diagnostics.
- **Asset Class Filtering**: Ability to filter extraction by asset classes (`ações`, `etf`, `opções`, etc.).

## 🏗️ Architecture

Focused modules and specialized subpackages:

```text
brazil/b3_data/historical_quotes/
├── models.py              # DocsToExtractorB3 (data object)
├── filesystem.py          # FileSystemServiceB3 (path validation and COTAHIST files)
├── assets.py              # AvailableAssetsServiceB3 (asset classes & TPMERC mapping)
├── processing.py          # ExtractionConfigServiceB3, ProcessingModeEnumB3
├── years.py               # Year validation and logic
├── client.py              # ExtractHistoricalQuotesUseCaseB3, CreateDocsToExtractUseCaseB3, etc.
├── cotahist_parser.py     # Positional COTAHIST parser (preserved — legitimate complexity)
├── integrity.py           # B3RecordContext (bounded contextual diagnostics for records)
├── member_resolver.py     # resolve_cotahist_member (ZIP member resolution and year matching)
├── parquet_writer/        # Parquet writing subpackage (writer, schema, session, disk, constants)
├── extraction_service/    # Orchestration subpackage (service, zip_processor, resource_policy, retry, temp_parquet_merge, types)
├── catalog.py              # Strict catalog and precedence of COTAHIST inputs
├── zip_reader.py          # Streaming reader for ZIP or TXT
└── errors.py              # InvalidFirstYear, InvalidLastYear, InvalidAssetsName, EmptyAssetListError, InvalidProcessingMode, etc.
```

`ExtractHistoricalQuotesUseCaseB3` remains a class because it maintains state: `zip_reader + parser + writer + processing_mode` are reused across calls. It provides both async `execute()` and synchronous `execute_sync()`.

`catalog.py` belongs to the B3 owner and is used by opt-in validations that need to audit a caller-owned directory before processing real data. It accepts only the external names `COTAHIST_A{YEAR}.ZIP` and `COTAHIST_A{YEAR}.TXT`, validates metadata/CRC and the internal root member, rejects conflicts in the same format, and maintains ZIP precedence when both ZIP and TXT coexist for the same year.

### Key Components

| Module                | Component                          | Type                 | Responsibility                                                                                                                                                                      |
| --------------------- | ---------------------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `client.py`           | `ExtractHistoricalQuotesUseCaseB3` | Orchestrator (class) | Connects parser, reader, and writer. Maintains state across calls. Offers `execute()` and `execute_sync()`. Configurable with safety limits and allowed UNC roots.                  |
| `client.py`           | `CreateDocsToExtractUseCaseB3`     | Use case             | Validates input parameters and constructs the prepared `DocsToExtractorB3` configuration, resolving inputs to absolute paths.                                                       |
| `models.py`           | `DocsToExtractorB3`                | Data object          | Represents the prepared extraction configuration; it is a data object and does not validate direct construction.                                                                    |
| `filesystem.py`       | `FileSystemServiceB3`              | Service              | Validates paths (`SecurityError`/`PathPermissionError` before I/O) and resolves official file regex patterns.                                                                       |
| `assets.py`           | `AvailableAssetsServiceB3`         | Service              | Provides asset class aliases and validates asset class names (not individual trading codes like PETR4).                                                                             |
| `processing.py`       | `ExtractionConfigServiceB3`        | Service              | Validates processing mode (`fast`, `slow`) and sanitizes/formats `output_filename`.                                                                                                 |
| `years.py`            | `YearValidationServiceB3`          | Service              | Implements validation and time boundary logic for `range_years`.                                                                                                                    |
| `cotahist_parser.py`  | `CotahistParserB3`                 | Concrete parser      | Translates positional text lines into structured Python dictionaries.                                                                                                               |
| `integrity.py`        | `B3RecordContext`                  | Diagnostic model     | Tracks coordinates (physical line, logical record, field) for safe, non-truncating contextual diagnostics upon parsing failures.                                                    |
| `member_resolver.py`  | `resolve_cotahist_member`          | Resolver function    | Resolves supported root member from ZIP metadata (`COTAHIST_A{YEAR}.TXT`, `COTAHIST.A{YEAR}`, `COTAHIST_A{YEAR}`) and ensures year compatibility.                                   |
| `parquet_writer/`     | `ParquetWriterB3`                  | Concrete writer      | Parquet writing with explicit Arrow schema, zstd compression, statistics, and bounded persistent sessions. Subpackage (`writer`, `schema`, `session`, `disk`, `constants`).         |
| `extraction_service/` | `ExtractionServiceB3`              | Concrete service     | Bounded scheduler, synchronous workers, transient I/O retry, and ordered merge. Subpackage (`service`, `zip_processor`, `resource_policy`, `retry`, `temp_parquet_merge`, `types`). |

## 🚀 Usage Guide

### Prerequisites

Ensure you have downloaded `COTAHIST_A{YEAR}.ZIP` files, or their uncompressed `COTAHIST_A{YEAR}.TXT` counterparts, in an accessible directory. If both formats for the same year coexist, ZIP takes deterministic precedence. In ZIPs, the internal member can be the modern `COTAHIST_A{YEAR}.TXT`, the historical `COTAHIST.A{YEAR}`, or the historical extensionless `COTAHIST_A{YEAR}`; there must be exactly one member compatible with the external year. Quotation records `01` have an exact width of 245 characters, and structurally unsafe ZIPs are rejected before streaming.

### Complete Example

```python
import asyncio
from globaldatafinance.brazil.b3_data.historical_quotes import (
    CreateDocsToExtractUseCaseB3,
    ExtractHistoricalQuotesUseCaseB3,
)


async def run_extraction():
    # 1. Validate inputs and prepare configuration
    # The use case validates parameters and resolves inputs to absolute paths.
    config = CreateDocsToExtractUseCaseB3(
        path_of_docs='/raw/data/b3',  # Where ZIP/TXT inputs are located
        destination_path='/processed/data',
        assets_list=['ações', 'etf'],
        initial_year=2023,
        last_year=2023,
    ).execute()

    # 2. Execution (async or execute_sync)
    use_case = ExtractHistoricalQuotesUseCaseB3()

    try:
        result = await use_case.execute(
            docs_to_extract=config,
            processing_mode='fast',  # 'fast' (in-memory) or 'slow' (iterative)
            output_filename='b3_quotes_2023.parquet',
        )

        print(f'Success! {result["total_records"]} records processed.')
        print(f'Output Parquet file: {result["output_file"]}')

    except Exception as e:
        print(f'Error during extraction: {e}')


if __name__ == '__main__':
    asyncio.run(run_extraction())
```

## ⚙️ API Reference

### `DocsToExtractorB3` (Prepared configuration)

`DocsToExtractorB3` is a data object and does not validate direct construction. Use `CreateDocsToExtractUseCaseB3` to validate public parameters and construct the configuration, populating `documents_to_download` with resolved absolute paths found in the directory.

| Field                   | Type       | Description                                                                                                                                                                                                        |
| ----------------------- | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `path_of_docs`          | `str`      | Absolute path to the directory containing COTAHIST ZIP or TXT files.                                                                                                                                               |
| `destination_path`      | `str`      | Absolute path where the Parquet file will be saved.                                                                                                                                                                |
| `range_years`           | `range`    | Year interval for validation (e.g., `range(2020, 2024)`).                                                                                                                                                          |
| `set_assets`            | `set[str]` | Set of asset class types to filter (e.g., `{"ações", "etf", "opções"}`). Valid values: `ações`, `etf`, `opções`, `termo`, `exercicio_opcoes`, `forward`, `leilao`.                                                 |
| `documents_to_download` | `set[str]` | Absolute paths of COTAHIST ZIP/TXT files selected by `FileSystemServiceB3`; `CreateDocsToExtractUseCaseB3` populates this field with resolved absolute paths. Direct construction requires already resolved paths. |

### `ExtractHistoricalQuotesUseCaseB3` (Execution & Return Value)

Methods:

- `execute(docs_to_extract, processing_mode='fast', output_filename='cotahist_extracted.parquet')`: Asynchronous entrypoint returning the execution result dictionary.
- `execute_sync(docs_to_extract, processing_mode='fast', output_filename='cotahist_extracted.parquet')`: Synchronous wrapper around `execute()`.

Result dictionary schema:

| Key             | Type             | Description                                                      |
| --------------- | ---------------- | ---------------------------------------------------------------- |
| `total_files`   | `int`            | Total number of COTAHIST files inspected for extraction.         |
| `success_count` | `int`            | Count of files processed successfully.                           |
| `error_count`   | `int`            | Count of files that failed processing.                           |
| `total_records` | `int`            | Total number of quotation records written to the Parquet file.   |
| `errors`        | `dict[str, str]` | Map of failed file paths to their respective error descriptions. |
| `output_file`   | `str`            | Resolved absolute path to the generated output Parquet file.     |

### Error Handling

The module exposes specific exceptions in `globaldatafinance.brazil.b3_data.historical_quotes.errors` (re-exported by the source `__init__.py`):

- `InvalidFirstYear` / `InvalidLastYear`: temporal range validation errors.
- `InvalidAssetsName`: asset class alias is not recognized.
- `EmptyAssetListError`: attempted processing with an invalid or empty asset list.
- `InvalidProcessingMode`: `processing_mode` outside `{'fast', 'slow'}`.
- `InvalidOutputFilename`: attempted use of an invalid output filename (empty/whitespace-only).
- `SecurityError` / `PathPermissionError` (from `macro_exceptions`): attempted writes to sensitive paths (`/etc`, `/sys`, etc.) or insufficient permissions — defense in `FileSystemServiceB3` (`filesystem.py`).

## 🔧 Troubleshooting

> [!WARNING]
> **Error: File not found**
> Verify that each absolute path in `documents_to_download` points to an existing COTAHIST file; to obtain this configuration safely, use `CreateDocsToExtractUseCaseB3`.

> [!TIP]
> **Performance**
> For large data volumes (all assets over multiple years), prefer processing year by year or use machines with more RAM if utilizing `fast` mode.
