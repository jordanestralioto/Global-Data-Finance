# Performance Benchmarks

This document records reproducible baselines for extraction and processing
across the B3 and CVM modules. The numbers are evidence from a reference
scenario and serve as a regression metric, not a fixed-time promise for every
machine or dataset.

## 1. Real-Scale Baseline — B3

### 1.1. Baseline v3 — Full 27 Years (2026-09-16, Revision `f1a2f47`)

**Environment:** Python 3.13.7 · Linux x86_64 (kernel 6.8) · 8 CPUs · 7.55 GB
total memory. No network calls; local extraction of official ZIPs only.

- **Dataset:** 27 official ZIP files (2000–2026), 666.00 MB compressed.
- **Asset scope:** all currently supported asset categories (`ações`, `etf`, `opções`, `termo`, `exercicio_opcoes`, `forward`, `leilao`).
- **Errors:** 0 (all 27 files processed successfully).
- **Consolidated Parquet output:** 481.86 MB per mode (505,265,249 bytes).

| Mode   | Written rows | Elapsed time (API) | Elapsed time (end-to-end) |    Peak RSS |      Throughput |
| ------ | -----------: | -----------------: | ------------------------: | ----------: | --------------: |
| `fast` |   22,303,577 |           649.99 s |                  650.50 s |  429.88 MiB | 34,313.8 rows/s |
| `slow` |   22,303,577 |           749.45 s |                  750.10 s |  331.11 MiB | 29,759.9 rows/s |

> **Note:** The `slow` mode peaked at only 331.11 MiB (~0.32 GiB) RSS (a ~23%
> memory reduction compared to `fast` mode), preserving 100% schema and data
> parity across all 22,303,577 records of the 27-year series. The modest ~98 MiB
> memory difference between `fast` and `slow` stems from bounded per-worker
> limits (`python_record_limit` of 25,000 vs 10,000 rows) and chunked flushes
> (`ROW_GROUP_LIMIT = 200,000`), keeping memory complexity $O(1)$ relative to
> the time span. The moderate ~15% speed advantage of `fast` mode reflects the
> plausible hypothesis of CPython GIL contention in `ThreadPoolExecutor` during
> the CPU-intensive positional string parsing loop and batch building in Python,
> alongside the sequential disk merge stage (while zlib decompression and C++
> PyArrow writes release the GIL, Python positional slicing and row validation
> retain the lock). Compared to historical baseline v2 (~4.4 GB), the columnar
> streaming architecture reduced peak memory by over 90%.

### 1.2. Historical Baseline v2 — Full 25 Years (2026-09-02, Revision `703d9ab`)

**Environment:** Python 3.13.7 · Linux x86_64 (kernel 6.8) · 8 CPUs · 7.55 GB
total memory. No network calls; local extraction of official ZIPs only.

- **Dataset:** 25 official ZIP files (2000–2024), 503.77 MB compressed.
- **Asset scope:** all currently supported asset categories (`ações`, `etf`, `opções`, `termo`, `exercicio_opcoes`, `forward`, `leilao`).
- **Errors:** 0 (all 25 files processed successfully).
- **Consolidated Parquet output:** 344.71 MB per mode.

| Mode   | Written rows | Elapsed time (API) | Elapsed time (end-to-end) |    Peak RSS |    Throughput |
| ------ | -----------: | -----------------: | ------------------------: | ----------: | ------------: |
| `fast` |   16,460,458 | 1,557.73 s | 1,557.28 s | 4,433.19 MB | 10,566.9 rows/s |
| `slow` |   16,460,458 | 2,143.77 s | 2,143.93 s | 1,545.97 MB |  7,678.3 rows/s |

> **Note:** The `slow` mode peaked at only 1,545.97 MB (~1.51 GiB) RSS (a ~65%
> memory reduction compared to `fast` mode), preserving 100% schema and data
> parity across all 16,460,458 records of the 25-year series.

### 1.3. Historical Baseline v1 — 17 Years (2026-08-06, Revision `7ee1843`)

**Environment:** Python 3.13.7 · Linux x86_64 (kernel 6.8) · 8 CPUs · 7.55 GB
total memory. No network calls; local extraction of official ZIPs only.

- **Dataset:** 17 official ZIP files (2008–2024), 445.85 MB compressed.
- **Asset scope:** all currently supported asset categories (`ações`, `etf`, `opções`, `termo`, `exercicio_opcoes`, `forward`, `leilao`).
- **Errors:** 0 (all 17 files processed successfully).
- **Consolidated Parquet output:** 311.55 MB per mode.

| Mode   | Written rows | Elapsed time (API) | Elapsed time (end-to-end) |    Peak RSS |    Throughput |
| ------ | -----------: | -----------------: | ------------------------: | ----------: | ------------: |
| `fast` |   15,059,876 | 1,222.61 s | 1,224.64 s | 4,259.35 MB | 12,317 rows/s |
| `slow` |   15,059,876 | 1,759.90 s | 1,761.91 s | 1,570.54 MB |  8,557 rows/s |

> **Bottleneck identified:** B3 Parquet parser and merge; `fast` mode peaks at
> ~4.2 GiB RSS. `slow` uses under 1.6 GiB with ~28% lower throughput.

______________________________________________________________________

## 2. Reproducible Synthetic Baseline — B3

For CI/CD and fast regressions, a smaller synthetic dataset is maintained.
Measured on **2026-08-06**, revision `7ee1843`, with three independent runs per
mode:

| Mode   | Records | ZIP input | Parquet output | API time (median) | End-to-end time (median) |    Peak RSS | Records/s (median) |
| ------ | ------: | --------: | -------------: | ----------------: | -----------------------: | ----------: | -----------------: |
| `fast` | 250,000 |   8.46 MB |        4.05 MB |           11.15 s |                  12.27 s | 1,111.72 MB |             22,427 |
| `slow` | 250,000 |   8.46 MB |        4.05 MB |           18.05 s |                  19.04 s | 1,103.01 MB |             13,847 |

The scenario processed a synthetic 61.5 MB uncompressed COTAHIST file with
250,000 records filtered to `ações`. All runs completed without errors. Peak RSS
includes the interpreter, dependencies, parser, and Parquet writer.

> **Note:** At synthetic scale, `fast` and `slow` show similar peak RSS (~1.1 GB).
> The significant memory difference (~4.2 GB vs ~1.6 GB) only becomes apparent at
> real scale, as shown in Section 1.

### 2.1. Arrow v3 Candidate — 250 Thousand Records (2026-09-12 UTC, Revision `703d9ab`)

This measurement uses the Arrow ingestion runner introduced by this cutover. It
does not replace the historical v1 baseline: the corpus generator, explicit
schema, and separation between operation and validation time are part of a
stricter protocol. It is reproducible candidate evidence and a starting point
for future comparisons made under the same protocol.

**Environment:** Python 3.13.7 · Linux x86_64 (kernel 6.8) · 8 CPUs. Three fresh
Python processes handled the deterministic synthetic corpus without network
calls.

| Scenario | Repeats | Rows | Operation time (median) | Peak RSS (median) | Parquet output | Logical equivalence |
| -------- | ------: | ---: | ----------------------: | ----------------: | -------------: | -----------------: |
| B3 250k |       3 | 250,000 |                 5.832 s |       215.898 MiB |    5,822,005 B |                3/3 |

- The input SHA-256 is
  `329f30c6d160401071ab321ebe796e8d91be5a2e0bf502fc68b1cc1c66c30d39`.
- Each repeat validated row count, order, schema, nulls, typed values, and
  decimal precision; all produced the same logical digest.
- Post-write validation is recorded separately from operation time; it is not
  mixed into the throughput metric in the table.
- The local raw JSON is stored at
  `.benchmarks/pyarrow-ingestion-integrity-cutover-b3-250k-20260912.json`.
  That directory is deliberately Git-ignored because it contains
  machine-dependent evidence.

### Reproduction

```bash
# In-repository hot path micro-benchmarks (CVM URL generation and B3 line parsing)
uv run --locked --no-sync pytest tests/perf -m perf

# Save a performance baseline
uv run --locked --no-sync pytest tests/perf -m perf --benchmark-save=baseline_v1

# Compare against saved baseline
uv run --locked --no-sync pytest tests/perf -m perf --benchmark-compare=baseline_v1
```

The repository's available benchmarks are executed through pytest-benchmark:

```bash
# List the two benchmarks without running them
uv run --locked --no-sync pytest tests/perf -m perf -o addopts='' --collect-only -q

# Run the hot-path benchmarks
uv run --locked --no-sync pytest tests/perf -m perf -o addopts=''

# Save results for a later comparison
uv run --locked --no-sync pytest tests/perf -m perf -o addopts='' \
  --benchmark-save=baseline_v1

# Compare against the saved baseline
uv run --locked --no-sync pytest tests/perf -m perf -o addopts='' \
  --benchmark-compare=baseline_v1
```

The synthetic archive used for the baseline has SHA-256
`4ba04707468088975125a536b07f5a9cd361676e8ac68866554241ceb58b7e86`.

______________________________________________________________________

## 3. CVM Baseline — Download + Extraction

### 3.1. Baseline v2 — 17 Years (2010–2026, Revision `703d9ab`)

Full-pipeline measurement of `FundamentalStocksDataCVM` with
`automatic_extractor=True`: raw ZIP downloads from CVM, CSV extraction with
robust unquoted free-text handling (`QUOTE_NONE`), and primary Parquet
generation with failure-atomic batch commit. Run on the same machine as the B3
benchmarks.

- **Docs:** DFP, ITR, FRE, FCA, CGVN, VLMO, IPE (all 7 available types)
- **Period:** 2010–2026 (17 years)

| ZIPs downloaded | Parquets generated | Extracted rows | Total output | Elapsed time |  Peak RSS | Errors |
| --------------: | -----------------: | -------------: | -----------: | ------------: | --------: | -----: |
|             102 |              1,569 |     70,821,466 |    382.27 MB |   906.85 s | 333.91 MB |      0 |

- Includes: CVM server connection, downloading all 102 available ZIPs,
  validation, CSV extraction, and Parquet conversion.
- Peak RSS memory dropped to 333.91 MB (~27% lower than v1), even while
  processing 70.82 million rows and generating 1,569 Parquet files.

### 3.2. Historical Baseline v1 — 15 Years (2010–2024, Revision `7ee1843`)

Full-pipeline measurement of `FundamentalStocksDataCVM` with
`automatic_extractor=True`: raw ZIP downloads from CVM, CSV extraction, and
primary Parquet generation. Run on the same machine as the B3 benchmarks.

- **Docs:** DFP, ITR, FRE, FCA, CGVN, VLMO, IPE (all available types)
- **Period:** 2010–2024

| ZIPs downloaded | Parquets generated | Extracted rows | Total output | Elapsed time |  Peak RSS | Errors |
| --------------: | -----------------: | -------------: | -----------: | ------------: | --------: | -----: |
|              88 |              1,392 |     63,300,208 |    337.93 MB |   505.04 s | 459.18 MB |      0 |

- Includes: CVM server connection, downloading all ZIPs, validation, CSV
  extraction, and Parquet conversion.
- Network time varies with external conditions; the CSV→Parquet extraction
  step is the stable and reproducible portion of the measurement.

______________________________________________________________________

## 4. Limitations and Contracts

- The synthetic B3 fixture validates the complete parsing, filtering, and
  Parquet-writing path, but does not represent the cardinality, compression, or
  asset mix of a real B3 year.
- When updating reproducible numbers, preserve: dataset, checksum, hardware,
  Python version, code revision, repetition count, and metric definitions.

______________________________________________________________________

## 5. Fresh-process ingestion runner

`scripts/benchmark_ingestion.py` measures root import, CVM, CVM text, B3
at 100k and 250k records, the multi-file scenario `b3_multi_4x25k` (four
25k-row files by default), runtime footprint, and, when available, the annual
B3 corpus. It generates
deterministic corpus data in a temporary directory, repeats each scenario three
times by default, runs the operation in a fresh Python process, and samples child
RSS every 10 ms. It supports comparative evaluation via `--backend thread|process`
and `--processing-mode fast|slow`. Before recording a result it validates row count,
order, schema, boundary values, and the logical Parquet artifact.
For the annual corpus, the runner derives a typed digest of every selected row from
the 27 official ZIPs before measurement and compares every repeat with that digest.
`--source-count` is exclusive to the synthetic `b3_multi_4x25k` corpus and
partitions the requested rows across the exact number of sources; the annual
corpus always uses its 27 sources. `--worker-limit` applies a cap in the fresh
measurement process through `GDF_B3_WORKER_LIMIT`; JSON records both requested
and effective values after resource policy and backend fallback.

```bash
# Small measurement to verify the JSON protocol
uv run --locked --no-sync python scripts/benchmark_ingestion.py \
  --scenario import_root --scenario cvm --rows 10 --repeats 1

# Full synthetic corpora, three repetitions, and a persisted report
uv run --locked --no-sync python scripts/benchmark_ingestion.py \
  --scenario cvm --scenario cvm_text --scenario b3_100k \
  --scenario b3_250k --scenario b3_multi_4x25k --repeats 3 --output benchmark.json

# Explicit comparison of execution backend and processing mode
uv run --locked --no-sync python scripts/benchmark_ingestion.py \
  --scenario b3_multi_4x25k --backend process --processing-mode fast --repeats 3

# Fallback proof: two sources, but only one effective worker
uv run --locked --no-sync python scripts/benchmark_ingestion.py \
  --scenario b3_multi_4x25k --rows 100 --source-count 2 --worker-limit 1 \
  --backend process --processing-mode fast

# The annual corpus runs only with all 27 ZIPs (2000–2026); otherwise it is skipped
uv run --locked --no-sync python scripts/benchmark_ingestion.py \
  --scenario b3_annual --cotahist-path /path/to/COTAHIST --output annual.json
```

Each JSON result contains schema version, revision, environment, input checksum,
row count, schema fingerprint, logical equivalence, a typed logical digest,
physical artifact SHA-256 (`artifact_sha256`), operation time,
operation/validation phases, processing mode, execution backend, requested and
effective source/worker counts, initial/peak/final parent RSS (`rss_peak_mib`, preserving
comparison with historical baseline v1), aggregate tree peak RSS
(`aggregate_rss_peak_mib`), observed child process count, output bytes, `status`, and
`worktree_sha256`. RSS is resident memory per process, not heap. `aggregate_rss_peak_mib`
is the sum of parent and descendant RSS in the same sample; shared pages can be
counted more than once, so it is not unique physical memory, host-wide memory, or
cgroup memory use. Equivalence compares every typed row (including nulls, ordering,
and decimal tuples), not only boundary values. The child verifies the checksum before
measuring, so a changed source fails instead of producing an invalid comparison. An
annual run without all 27 required ZIPs reports `skipped` with `external corpus unavailable`;
release reports must not turn that into success.

When `git_sha` ends in `-dirty`, `worktree_sha256` identifies the tracked diff and
the contents of non-ignored untracked files present when measurement began. Results
under `.benchmarks/` are deliberately local and ignored; for a reviewable claim,
preserve the emitted JSON in a tracked review artifact and cite both provenance fields.

Reference gates for this change are compared only on the same baseline/candidate
machine: root import ≤50 MiB and ≤0.50 s; CVM 269,181 rows ≤60% of baseline
time and ≤70% of baseline RSS; B3 250k ≤50% of baseline time and ≤25% of
baseline RSS; and a closed runtime footprint without Polars ≤260 MiB. These are
release objectives, not universal CI limits.
