# B3 API - Technical Specification

Detailed technical specification covering the B3 historical quote extraction API.

______________________________________________________________________

## HistoricalQuotesB3

### Primary Class Definition

```python
class HistoricalQuotesB3:
    """High-level facade for B3 market quote extraction and normalization."""
```

### Execution telemetry

The `last_phase_timings: dict[str, Any]` property exposes telemetry from the
last extraction for instrumentation and benchmarks. It starts empty and resets
when a new extraction begins. Observations include the effective backend,
worker limit, and timings of executed phases. This diagnostic is separate from
the `ExtractionResultB3` result and Parquet metadata.

### Public Methods

#### `extract()`

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

**Description**: Parses COTAHIST archives (`COTAHIST_A{YYYY}.ZIP` or `.TXT`), filters target asset transactions, and compiles a unified Parquet file. The API accepts both local formats; official B3 downloads continue to be distributed as ZIP archives.

The parser is strict: `00`/`99` controls and blank lines are not persisted,
TPMERC outside the filter is counted as filtered, and an invalid selected `01`
record raises contextual `ExtractionError`. Invalid financial values never
receive a zero or null fallback.

**Parameters**:

| Parameter          | Type                | Required | Default                | Description                                                                      |
| ------------------ | ------------------- | -------- | ---------------------- | -------------------------------------------------------------------------------- |
| `path_of_docs`     | `str`               | Yes      | -                      | Directory containing COTAHIST ZIP or TXT inputs                                 |
| `assets_list`      | `list[str] \| None` | No       | `None` (`["todos"]`)   | Asset classes; `todos` selects every valid numeric TPMERC                         |
| `initial_year`     | `int \| None`       | No       | `None` (1986)          | Initial historical fiscal year (inclusive, >= 1986)                              |
| `last_year`        | `int \| None`       | No       | `None` (current year)  | Ending historical fiscal year (inclusive)                                        |
| `destination_path` | `str \| None`       | No       | `None` (`path_of_docs`)| Output artifact destination directory                                            |
| `output_filename`  | `str`               | No       | `"cotahist_extracted"` | Required basename; optional `.parquet` suffix is appended only when absent     |
| `processing_mode`  | `str`               | No       | `"fast"`               | Execution mode: `"fast"` (parallel) or `"slow"` (minimal RAM)                    |
| `verbose`          | `bool`              | No       | `True`                 | When `True`, prints formatted execution summary to console                       |

The `Validating B3 files` and `Processing B3 files` bars appear on `stdout`
in both `fast` and `slow`, independently of `verbose`. They count annual
sources found: the first advances after a source is validated; the second
advances when a processing attempt finishes, including with an error.
The summary is emitted only when `verbose=True`. Parquet consolidation,
readback verification, and publication continue after the processing bar;
the returned result confirms complete success. Failures and cancellation
finish the bar's output line at the observed count. Selections without files
do not display empty bars.

**Return Contract (`ExtractionResultB3`)**:

Typed dictionary (`TypedDict`) containing execution results:

- `success: bool` — Success status confirmation for overall execution.
- `message: str` — Human-readable summary of the execution outcome.
- `total_files: int` — Number of annual inputs resolved for the request.
- `success_count: int` — Number of sources included in the committed output.
- `error_count: int` — Number of entries in `errors`.
- `total_records: int` — Committed output row count.
- `output_file: str` — Newly committed output path; empty on failure.
- `errors: dict[str, str]` — Dictionary mapping failed files to failure error messages (if any).
- `assets: list[str]` — Asset category tags processed during extraction.
- `processing_mode: str` — Processing mode used (`"fast"` or `"slow"`).
- `elapsed_time: float` — Total execution duration in seconds.
- `schema_version: int` — Parquet schema version (`2`).
- `integrity: B3IntegrityReport` — Coverage, selection, source, verification,
  warning, and published-output hash evidence.

When preflight fails, `integrity` retains previously validated sources, missing
years, and normalized selection. `success_count` and `total_records` remain
zero. Each validated source includes input and content hashes, uncompressed
size, market counts, original controls encoded as Base64, generation date,
trading-date range, trailer convention, blank lines, warnings, and expected
and verified digests.

**Input and empty-result semantics**:

- The API accepts `COTAHIST_A{YYYY}.ZIP` and `COTAHIST_A{YYYY}.TXT`; when both
  formats exist for the same year, both are fully validated. ZIP is selected
  only when their uncompressed contents are identical; different contents
  cause failure.
- Each ZIP read verifies the CRC of every member, including unselected ones,
  and reads the COTAHIST member from the same open, validated archive.
  Validation is renewed on every pass, preserving decompression limits and
  source identity checks.
- `output_filename` must be a basename without path separators. The optional
  `.parquet` suffix is accepted and appended exactly once when omitted.
- A missing requested year returns `success=False`, lists the year in
  `integrity.missing_years`, and does not publish a new output. An empty
  directory reports zero resolved files and every requested year as missing.
- If every requested source is valid and the filter excludes all quotations,
  extraction publishes an empty result (`success=True`).

If valid inputs contain no records after asset filtering, extraction still
succeeds and publishes an empty B3 Parquet with the explicit schema.

`assets_list=None` selects `todos`, including unknown numeric TPMERC codes;
`lote_bloco` selects `021`. All quote fields are validated before filtering,
every requested year must be present, and the full output is read back before
publication. Gaps or failures return `success=False`; `integrity` retains the
observed coverage and reason. See the [COTAHIST v2 schema reference](b3-schema-v2.en.md)
and [migration guide](../user-guide/migration-pyarrow-integrity.en.md).

For asynchronous cancellation before commit, the service aborts publication,
cleans temporary state, and re-raises `asyncio.CancelledError`; a pre-existing
final artifact remains intact.

Preparation, transaction recovery and acquisition, Parquet verification,
consolidation, source checksum rechecks, and rollback run outside the event-loop
thread. Thread and process workers receive a cancellation signal owned by their
extraction run. Cancellation is observed at bounded reads
and batch boundaries. The service joins readers and writers before removing
their temporary files, including after repeated cancellation requests. A
cancellation checkpoint runs immediately before the commit decision. Once
that decision starts atomic publication, new cancellation requests wait for
completion and the API returns the publication outcome. Commit also runs
outside the event-loop thread.

The final input checksum recheck and publication decision run in the same
worker, without returning to the event loop between them. Hash reads remain
cancellable; the worker checks cancellation once more before starting
publication. Detected source changes fail and preserve the previous output.
Callers must keep ZIP/TXT inputs unchanged during extraction: this recheck does
not lock external writers or provide absolute isolation against concurrent
modifications.

A cleanup failure after durable commit preserves `success=True`, the output
path, verified counts, and published-output checksum. Its diagnostic appears
in `integrity.warnings`: `PUBLICATION_CLEANUP_RECOVERED` means the cleanup retry
succeeded; `PUBLICATION_CLEANUP_PENDING` means recovery state was preserved.
For these warnings, `source` identifies the published Parquet basename. The
original diagnostic is also logged. Failures before commit still return a
failed outcome and preserve the previous output through rollback.

**Raised Exceptions**:

- `EmptyAssetListError`: Empty array supplied for `assets_list` parameter.
- `InvalidAssetsName`: Supplied instrument keyword unsupported by filter rules.
- `InvalidFirstYear`: Initial year parameter set below 1986 historical floor.
- `InvalidLastYear`: Ending year preceded initial year or surpassed active year limits.
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
# Returns: ['ações', 'etf', 'opções', 'termo', 'exercicio_opcoes', 'forward', 'leilao', 'lote_bloco', 'todos']
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

#### Instance Properties

- `settings: Settings`: Immutable snapshot of the client runtime configuration.

______________________________________________________________________

## Execution Configuration and Environment Variables

The variables below are resolved when `HistoricalQuotesB3()` is constructed.
They do not alter an existing instance or add parameters to the public
constructor. The process backend is experimental and requires explicit opt-in.
Measure complete operation time, CPU, and aggregate RSS on the consumer's corpus
before adopting it. Conditions and measurements are in the
[COTAHIST performance guide](../dev-guide/cotahist-performance.en.md).

- `GDF_B3_EXECUTOR_BACKEND`: Defines the parallel execution backend in `fast` mode (`"thread"` or `"process"`). Default is `"thread"`.
  - `"thread"`: Uses `ThreadPoolExecutor`. Lower startup overhead and lower global memory consumption. Recommended for most workloads.
  - `"process"`: Uses `ProcessPoolExecutor` with `spawn` context only for controlled experiments. It can reduce measured parent-process RSS by isolating per-file buffers in workers, but it also adds `spawn` cost, can increase summed worker RSS, and offers no guaranteed time improvement.
  - Automatic fallback: If `processing_mode="slow"`, exactly 1 source file is processed, or worker limit is below 2, the system safely falls back to `"thread"`.
  - Annual preflight: In `fast` with `process`, validation can use processes when the resource policy admits at least two workers and stored annual candidates total at least 64 MiB. Coexisting ZIP and TXT files both count. Smaller workloads and size-read errors use serial validation. Source order, the first error, and its typed causes are preserved; all workers are joined before cancellation or failure completes.
  - Contractual limitations:
    1. Child worker processes instantiate default readers and parsers; internally injected custom collaborators are not serialized across process boundaries in this version.
    2. Multiprocessing with `spawn` requires importable Python modules and does not support interactive execution via `<stdin>` (`python -`).
- `GDF_B3_WORKER_LIMIT`: Optional fast-mode worker cap. Use a positive integer; the effective limit remains the minimum of this value, source-file count, available CPUs, and memory budget. Slow mode remains single-worker. A non-numeric value preserves the default cap; values below one are clamped to one worker.

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
| `lote_bloco`     | Block lot            | 021 (BBT and Midpoint)                                   |
| `todos`          | Complete selection   | Every valid numeric TPMERC                               |

The Portuguese strings in this table are canonical `assets_list` values and
must be passed exactly as shown. BDRs and Futures are **Planned** and are not
accepted by the current runtime contract.

______________________________________________________________________

## Computational Execution Modes

| Processing Mode | Measured Throughput* | Measured Peak RSS* | Default Parallelism                                          | Recommended Operating Profile |
| --------------- | -------------------: | -----------------: | ------------------------------------------------------------ | ----------------------------- |
| **fast**        | 34,313.8 rows/s      | 429.88 MiB         | Up to 4 workers, bounded by CPU count, memory, and source files | Prioritize throughput         |
| **slow**        | 29,759.9 rows/s      | 331.11 MiB         | 1 worker                                                     | Reduce memory use             |

*Historical implementation v3 measurement on 27 annual files (2000–2026),
22,303,577 rows, excluding 2,283 TPMERC `021` quotations. It does not describe
schema v2 and is not directly comparable. See the [benchmark details](../dev-guide/benchmarks.en.md).*

The `fast` mode coordinates parallelism by source file. The `slow` mode uses a
single worker to reduce memory use.

______________________________________________________________________

## Related Documentation

- [B3 User Guide](../user-guide/b3-docs.md)
- [Exception Hierarchy](exceptions.md)
