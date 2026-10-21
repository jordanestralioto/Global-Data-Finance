# B3 API Reference

Inputs, results, and execution contracts for `HistoricalQuotesB3`.
For local input preparation, see the [B3 guide](../user-guide/b3-docs.md).

______________________________________________________________________

## HistoricalQuotesB3

### Import

```python
from globaldatafinance import HistoricalQuotesB3
```

### Execution telemetry

The `last_phase_timings: dict[str, Any]` property exposes telemetry from the
last extraction for instrumentation and benchmarks. It starts empty and resets
when a new extraction begins. Observations include the effective backend,
worker limit, and timings of executed phases. This diagnostic is separate from
the `ExtractionResultB3` result and Parquet metadata.

### Construction and configuration

```python
def __init__(self, *, settings: Settings | None = None) -> None:
    ...
```

Import `Settings` from `globaldatafinance.core.config`. The optional argument
injects an immutable snapshot; with `None`, the client creates a snapshot from
the current environment. The `settings` property returns the configuration
used. See [configuration](../dev-guide/advanced-usage.md).

### `extract()`

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
and TPMERC outside the filter is counted as filtered. Every `01` record is
validated before filtering. When a source contains invalid records, the facade
returns `success=False`, `output_file=""`, and contextual details in `errors`;
callers must check the result. Direct parser calls may raise `ExtractionError`.
Invalid financial values never receive a zero or null fallback.

Within the validated destination, an output-file symbolic link is rejected
with a failure result without changing its target. Publication also prevents
the output path from replacing a COTAHIST source.

**Parameters**:

| Parameter          | Type                | Required | Default                 | Description                                                                |
| ------------------ | ------------------- | -------- | ----------------------- | -------------------------------------------------------------------------- |
| `path_of_docs`     | `str`               | Yes      | -                       | Directory containing COTAHIST ZIP or TXT inputs                            |
| `assets_list`      | `list[str] \| None` | No       | `None` (`["todos"]`)    | Asset classes; `todos` selects every valid numeric TPMERC                  |
| `initial_year`     | `int \| None`       | No       | `None` (1986)           | First annual COTAHIST year, inclusive (>= 1986)                            |
| `last_year`        | `int \| None`       | No       | `None` (current year)   | Last annual COTAHIST year, inclusive                                       |
| `destination_path` | `str \| None`       | No       | `None` (`path_of_docs`) | Output artifact destination directory                                      |
| `output_filename`  | `str`               | No       | `"cotahist_extracted"`  | Required basename; optional `.parquet` suffix is appended only when absent |
| `processing_mode`  | `str`               | No       | `"fast"`                | `"fast"` permits concurrent sources; `"slow"` uses one source worker      |
| `verbose`          | `bool`              | No       | `True`                  | When `True`, prints formatted execution summary to console                 |

The `Validating B3 files` and `Processing B3 files` bars appear on `stdout`
in both `fast` and `slow`, independently of `verbose`. They count annual
sources found: the first advances after a source is validated; the second
advances when a processing attempt finishes, including with an error.
The summary is emitted only when `verbose=True`. Parquet consolidation,
readback verification, and publication continue after the processing bar;
the returned result confirms complete success. Failures and cancellation
finish the bar's output line at the observed count. Selections without files
do not display empty bars.

**Returns (`ExtractionResultB3`)**:

Typed dictionary (`TypedDict`) containing execution results:

- `success: bool` — Whether extraction completed successfully.
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
- `InvalidAssetsName`: Non-string filter item or unsupported alias.
- `InvalidFirstYear`: Invalid initial year; supported range is 1986 through the current year.
- `InvalidLastYear`: Invalid final year, above the current year, or before the initial year.
- `InvalidOutputFilename`: Output filename contains path separators or traversal segments.
- `InvalidProcessingMode`: Mode other than `"fast"` or `"slow"`.
- `InvalidDestinationPathError`: Empty or whitespace-only path.
- `PathIsNotDirectoryError`: Missing input path or an input path that is not a directory.
- `SecurityError`: Path rejected by the security policy.

Content and processing failures are collected in `errors` with `success=False`.
See the [exception reference](exceptions.md) for types used by lower-level
calls.

**Example**:

```python
from globaldatafinance import HistoricalQuotesB3

def main() -> None:
    b3 = HistoricalQuotesB3()
    result = b3.extract(
        path_of_docs="/data/cotahist",
        assets_list=["ações", "opções"],
        initial_year=2022,
        last_year=2023,
        processing_mode="fast",
    )
    if not result["success"]:
        raise RuntimeError(result["errors"] or result["message"])
    print(f"Extracted {result['total_records']:,} records")


if __name__ == "__main__":
    main()
```

### `extract_async()`

Async counterpart of `extract()`, with identical arguments, defaults, and
result. In notebooks or applications with an active event loop, use
`await client.extract_async(...)` instead of the synchronous wrapper. The full
signature is also in the [API overview](../dev-guide/api-reference.md).

### `get_available_assets()`

```python
def get_available_assets(self) -> list[str]:
    ...
```

**Description**: Returns the supported asset filter aliases.

**Returns**: List of alias strings.

**Execution Example**:

```python
assets = b3.get_available_assets()
# Returns: ['ações', 'etf', 'opções', 'termo', 'exercicio_opcoes', 'forward', 'leilao', 'lote_bloco', 'todos']
```

### `get_available_years()`

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

### Instance properties

- `settings: Settings`: Immutable snapshot of the client runtime configuration.

______________________________________________________________________

## Integrity report

`result["integrity"]` is a `B3IntegrityReport`. Every key below is present,
including on failure; nullable values use `None`. Dates are ISO `YYYY-MM-DD`
strings. Counts and flags describe the supplied sources, without reconciliation
against an external trading calendar or instrument registry.

| Key | Type | Meaning |
| --- | --- | --- |
| `status` | `Literal["passed", "failed", "not_run"]` | Verification status |
| `schema_version` | `int` | Schema version, `2` |
| `verification_method` | `str` | Verification method or `"not completed"` |
| `requested_years` | `list[int]` | Requested years |
| `selected_years` | `list[int]` | Years of selected, validated sources |
| `missing_years` | `list[int]` | Requested years without an input source |
| `complete_market_selection` | `bool` | `todos` selection, including unknown numeric codes |
| `market_codes` | `list[str]` | Selected codes; empty for complete market selection |
| `asset_classes` | `list[str]` | Normalized, deduplicated aliases |
| `raw_quotes` | `int` | Total `01` records in validated sources |
| `selected_quotes` | `int` | Records selected by the filter |
| `intentional_exclusions` | `int` | Records excluded by the filter |
| `excluded_records` | `int` | Same value as `intentional_exclusions` |
| `written_rows` | `int` | Rows written |
| `verified_rows` | `int` | Rows checked during readback |
| `selection_complete` | `bool` | Verification passed and selected = written = verified |
| `source_complete` | `bool` | Complete row selection, no exclusions, and raw = written = verified |
| `source_first_trading_date` | `str \| None` | First date in validated sources |
| `source_last_trading_date` | `str \| None` | Last date in validated sources |
| `output_first_trading_date` | `str \| None` | First date in verified output |
| `output_last_trading_date` | `str \| None` | Last date in verified output |
| `unknown_market_counts` | `dict[str, int]` | Counts by unknown TPMERC code |
| `warnings` | `list[B3IntegrityWarning]` | Warnings associated with an input or published output |
| `sources` | `list[B3SourceIntegrityReport]` | Per-source evidence, detailed below |
| `ignored_duplicate_sources` | `list[str]` | Equivalent TXT inputs skipped in favor of ZIP |
| `output_sha256` | `str \| None` | SHA-256 of published output; `None` without confirmed output |

Each item in `sources` contains these required keys:

| Key | Type | Meaning |
| --- | --- | --- |
| `source` | `str` | Input filename |
| `year` | `int` | Source year |
| `member` | `str` | ZIP member; empty for TXT |
| `outer_sha256` | `str` | SHA-256 of the input file |
| `content_sha256` | `str` | SHA-256 of uncompressed COTAHIST bytes |
| `uncompressed_bytes` | `int` | Uncompressed content size |
| `market_counts` | `dict[str, int]` | Counts by TPMERC code |
| `unknown_market_counts` | `dict[str, int]` | Counts by unknown TPMERC code |
| `header_records` | `int` | Number of `00` controls |
| `trailer_records` | `int` | Number of `99` controls |
| `generation_date` | `str` | Declared generation date |
| `blank_lines` | `int` | Observed blank lines |
| `warnings` | `list[B3SourceWarningReport]` | Source warnings |
| `raw_quotes` | `int` | Total `01` records |
| `selected_quotes` | `int` | Selected records |
| `intentional_exclusions` | `int` | Records excluded by the filter |
| `excluded_records` | `int` | Same value as `intentional_exclusions` |
| `written_rows` | `int` | Rows written for this source |
| `verified_rows` | `int` | Rows verified for this source |
| `declared_records` | `int` | Count declared in the trailer |
| `trailer_convention` | `str` | Trailer count convention |
| `first_trading_date` | `str` | First source trading date |
| `last_trading_date` | `str` | Last source trading date |
| `header_base64` | `str` | Original `00` control in Base64 |
| `trailer_base64` | `str` | Original `99` control in Base64 |
| `expected_rows_sha256` | `str` | Ordered preflight digest of selected rows |
| `verified_rows_sha256` | `str \| None` | Verified output digest; `None` before verification |

`B3SourceWarningReport` contains `code: str`, `count: int`, and `explanation: str`.
`B3IntegrityWarning` adds `source: str`, the input or published Parquet basename.
Post-commit cleanup warning codes are described under `extract()`.
The [B3 v2 schema](b3-schema-v2.md) defines the row-digest framing.

## Execution Configuration and Environment Variables

`GDF_B3_EXECUTOR_BACKEND` is resolved when `HistoricalQuotesB3()` is constructed
and does not alter an existing instance. Resource policy reads
`GDF_B3_WORKER_LIMIT` when calculating worker admission. These options add no
public constructor parameters. The default `process` applies in `fast` with two sources, two workers,
and a compatible spawn context. Conditions and measurements are in the
[COTAHIST performance guide](../dev-guide/cotahist-performance.en.md).

- `GDF_B3_EXECUTOR_BACKEND`: Accepts `"thread"` or `"process"`; the default is `"process"`.
  - `"thread"`: Uses `ThreadPoolExecutor`, with lower startup cost and buffers in the parent process.
  - `"process"`: Uses `ProcessPoolExecutor` with `spawn` in eligible contexts. It isolates source buffers and can increase aggregate RSS. Measure complete operation time, CPU, and memory on the consumer's corpus.
  - Fallback: `slow`, one source, or a one-worker limit use one thread worker. Daemons and sessions without an importable main module or readable script use threads. The logger records the incompatibility and `last_phase_timings['effective_backend']` reports the actual backend. Failures after submission retain their diagnostics and normal cleanup.
  - Annual preflight: In `fast` with `process`, admits processes when policy allows at least two workers, the context is compatible, and stored annual candidates total at least 64 MiB. Coexisting ZIP and TXT files both count. Smaller workloads and size-read errors use serial validation. Order, first error, typed causes, and joining workers before cleanup are preserved.
  - Child workers instantiate default readers and parsers; internally injected custom collaborators are not serialized. Use threads for these collaborators.
  - Scripts must guard the call with `if __name__ == '__main__':`. Set `GDF_B3_EXECUTOR_BACKEND=thread` to explicitly select threads. Invalid values raise `ValueError` at construction.
- `GDF_B3_WORKER_LIMIT`: Optional fast-mode worker cap. Use a positive integer; the effective limit remains the minimum of this value, source-file count, available CPUs, and memory budget. Slow mode remains single-worker. A non-numeric value preserves the default cap; values below one are clamped to one worker.

______________________________________________________________________

## Asset Classification Codes

| Code Identifier    | Description           | Included B3 TPMERC Codes                             |
| ------------------ | --------------------- | ---------------------------------------------------- |
| `ações`            | Equities / Stocks     | 010 (Spot Cash Market), 020 (Fractional Market)      |
| `etf`              | ETFs                  | 010 (Spot Cash Market), 020 (Fractional Market)      |
| `opções`           | Options               | 070 (Call Options), 080 (Put Options)                |
| `termo`            | Term-market contracts | 030 (Term Market)                                    |
| `exercicio_opcoes` | Option Exercises      | 012 (Call Exercise), 013 (Put Exercise)              |
| `forward`          | Forward Contracts     | 050 (Forward with Gain), 060 (Forward with Movement) |
| `leilao`           | Auction Market        | 017 (Auction Market)                                 |
| `lote_bloco`       | Block lot             | 021 (BBT and Midpoint)                               |
| `todos`            | Complete selection    | Every valid numeric TPMERC                           |

The Portuguese strings in this table are the accepted `assets_list` aliases.
Validation lowercases the input; spelling and accents still matter. `ações`
and `etf` select the same markets, `010` and `020`, without distinguishing
stocks from ETFs or classifying issuers. The aliases `bdr` and `futuro` are not
in the catalog. Use `get_available_assets()` to query the installed version.

______________________________________________________________________

## Processing modes

| Mode | Execution | Use |
| --- | --- | --- |
| `fast` | Concurrent sources within CPU, memory, and file-count limits; default cap of 4 workers | Allow source-level parallelism |
| `slow` | One source worker and smaller batches | Limit concurrency and memory use |

Both modes use bounded batches and the same schema and validation.
`slow` does not reduce the requested data or the space needed for temporary
files and output. [COTAHIST measurements](../dev-guide/cotahist-performance.md)
record the environment, corpus, and results. Previous-schema measurements
remain in the [historical benchmarks](../dev-guide/benchmarks.md).

For consumers importing `ProcessingModeEnumB3` through the source namespace,
the `FAST` and `SLOW` values remain. The 2026-10-20 revision removes
`desired_concurrent_files`, `desired_workers`, `use_parallel_parsing` and
`memory_threshold_mb`, which did not control extraction. `ResourcePolicyB3`
continues to calculate actual limits, while telemetry exposes the effective
backend and worker count.

______________________________________________________________________

## Related Documentation

- [B3 User Guide](../user-guide/b3-docs.md)
- [Exception Hierarchy](exceptions.md)
