# B3 API - Technical Specification

Detailed technical specification covering the B3 historical quote extraction API.

______________________________________________________________________

## HistoricalQuotesB3

### Primary Class Definition

```python
class HistoricalQuotesB3:
    """High-level facade for B3 market quote extraction and normalization."""
```

### Public Methods

#### `extract()`

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

**Description**: Parses COTAHIST archives (`COTAHIST_A{YYYY}.ZIP` or `.TXT`), filters target asset transactions, and compiles a unified Parquet file. The API accepts both local formats; official B3 downloads continue to be distributed as ZIP archives.

The parser is strict: `00`/`99` controls and blank lines are not persisted,
TPMERC outside the filter is counted as filtered, and an invalid selected `01`
record raises contextual `ExtractionError`. Invalid financial values never
receive a zero or null fallback.

**Parameters**:

| Parameter          | Type                | Required | Default                | Description                                                                      |
| ------------------ | ------------------- | -------- | ---------------------- | -------------------------------------------------------------------------------- |
| `path_of_docs`     | `str`               | Yes      | -                      | Directory containing COTAHIST ZIP or TXT inputs                                 |
| `assets_list`      | `list[str]`         | Yes      | -                      | Targeted asset categories (e.g., `["ações", "etf"]`)                             |
| `initial_year`     | `int \| None`       | No       | `None` (1986)          | Initial historical fiscal year (inclusive, >= 1986)                              |
| `last_year`        | `int \| None`       | No       | `None` (current year)  | Ending historical fiscal year (inclusive)                                        |
| `destination_path` | `str \| None`       | No       | `None` (`path_of_docs`)| Output artifact destination directory                                            |
| `output_filename`  | `str`               | No       | `"cotahist_extracted"` | Required basename; optional `.parquet` suffix is appended only when absent     |
| `processing_mode`  | `str`               | No       | `"fast"`               | Execution mode: `"fast"` (parallel) or `"slow"` (minimal RAM)                    |
| `verbose`          | `bool`              | No       | `True`                 | When `True`, prints formatted execution summary to console                       |

**Return Contract (`ExtractionResultB3`)**:

Typed dictionary (`TypedDict`) containing execution results:

- `success: bool` — Success status confirmation for overall execution.
- `message: str` — Human-readable summary of the execution outcome.
- `total_files: int` — Total number of input files processed (ZIP or TXT).
- `success_count: int` — Count of successfully parsed input files.
- `error_count: int` — Count of input files that failed during processing.
- `total_records: int` — Aggregate count of financial transactions consolidated.
- `output_file: str` — Absolute filesystem path of produced Parquet file.
- `errors: dict[str, str]` — Dictionary mapping failed files to failure error messages (if any).
- `assets: list[str]` — Asset category tags processed during extraction.
- `processing_mode: str` — Processing mode used (`"fast"` or `"slow"`).
- `elapsed_time: float` — Total execution duration in seconds.

**Input and empty-result semantics**:

- The API accepts `COTAHIST_A{YYYY}.ZIP` and `COTAHIST_A{YYYY}.TXT`; when both
  formats exist for the same year, ZIP takes deterministic precedence.
- `output_filename` must be a basename without path separators. The optional
  `.parquet` suffix is accepted and appended exactly once when omitted.
- `EmptyDirectoryError` is raised only when the input directory is physically
  empty. If the directory is not empty but has no COTAHIST file for a requested
  year, the API returns an empty result with `success=True`, `total_files=0`,
`total_records=0`, `output_file=""`, and `errors={}`. Inspect these counters
when data presence is required.

If valid inputs contain no records after asset filtering, extraction still
succeeds and publishes an empty B3 Parquet with the explicit schema.

For asynchronous cancellation before commit, the service aborts publication,
cleans temporary state, and re-raises `asyncio.CancelledError`; a pre-existing
final artifact remains intact.

**Raised Exceptions**:

- `EmptyAssetListError`: Empty array supplied for `assets_list` parameter.
- `InvalidAssetsName`: Supplied instrument keyword unsupported by filter rules.
- `InvalidFirstYear`: Initial year parameter set below 1986 historical floor.
- `InvalidLastYear`: Ending year preceded initial year or surpassed active year limits.
- `EmptyDirectoryError`: Target source directory was physically empty.
- `InvalidOutputFilename`: Output filename contains path separators or traversal segments.
- `ExtractionError`: Corruption or positional alignment errors encountered during parsing.

**Execution Example**:

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações", "etf"],
    initial_year=2022,
    last_year=2023,
    processing_mode="fast",
)
print(f"Extracted {result['total_records']:,} records")
```

#### `get_available_assets()`

```python
def get_available_assets(self) -> list[str]:
    ...
```

**Description**: Returns an exhaustive whitelist of permissible asset filter strings.

**Return Structure**: List of instrument string identifiers.

**Execution Example**:

```python
assets = b3.get_available_assets()
# Returns: ['ações', 'etf', 'opções', 'termo', 'exercicio_opcoes', 'forward', 'leilao']
```

#### `get_available_years()`

```python
def get_available_years(self) -> dict[str, int]:
    ...
```

**Description**: Queries bounding boundaries representing permissible historical time horizons.

**Return Structure**: Dictionary featuring:

- `"minimal_year"`: Floor starting year (1986)
- `"current_year"`: Real-time operational system year

**Execution Example**:

```python
years = b3.get_available_years()
# `current_year` is the current execution year returned by the API.
```

______________________________________________________________________

## Asset Classification Codes

| Code Identifier  | Description          | Included B3 TPMERC Codes                                 |
| ---------------- | -------------------- | -------------------------------------------------------- |
| `ações`          | Equities / Stocks    | 010 (Spot Cash Market), 020 (Fractional Market)          |
| `etf`            | ETFs                 | 010 (Spot Cash Market), 020 (Fractional Market)          |
| `opções`         | Options              | 070 (Call Options), 080 (Put Options)                    |
| `termo`          | Term-market contracts | 030 (Term Market)                                        |
| `exercicio_opcoes`| Option Exercises    | 012 (Call Exercise), 013 (Put Exercise)                  |
| `forward`        | Forward Contracts    | 050 (Forward with Gain), 060 (Forward with Movement)     |
| `leilao`         | Auction Market       | 017 (Auction Market)                                     |

The Portuguese strings in this table are canonical `assets_list` values and
must be passed exactly as shown. BDRs and Futures are **Planned** and are not
accepted by the current runtime contract.

______________________________________________________________________

## Computational Execution Modes

| Processing Mode | Measured Throughput | CPU Utilization | RAM Consumption Window | Recommended Operating Profile          |
| --------------- | ------------------- | --------------- | ---------------------- | -------------------------------------- |
| **fast**        | ~12,300 rec/s       | Intensive       | ~2 GB – 4.2 GB (peak)  | Default profile for multi-core systems |
| **slow**        | ~8,500 rec/s        | Low             | ~500 MB – 1.5 GB (peak)| Constrained RAM server environments    |

______________________________________________________________________

## Related Documentation

- [B3 User Guide](../user-guide/b3-docs.md)
- [Exception Hierarchy](exceptions.md)
