# COTAHIST performance and integrity

## Optimization contract

The 2026-10-06 optimizations preserve public signatures, schema v2, output
names, and market selection. All 32 fields, exact decimals, original bytes,
provenance, order, and repeated occurrences remain verified before publication.
CRC, source identity, replay, and complete final readback remain mandatory.

The parser produces a canonical tuple directly and applies a layout-derived
plan that reuses existing scalar validators. The digest uses constant tag and
length tables. Final readback builds the same v2 framing with Arrow in bounded
source segments. These tables do not store financial values. See the
[digest contract](../reference/b3-schema-v2.en.md).

## Parser and final readback: distinct-version comparison

Three pairs per mode processed the same 500,000 records across four sources,
in alternating fresh Python processes. Environment: Python 3.13.9, PyArrow
23.0.1, Linux x86_64, eight CPUs, with other host processes running. The
requested backend was `thread`; `slow` retained one worker.

| Mode | Starting median | Optimized median | Time reduction | CPU reduction |
| --- | ---: | ---: | ---: | ---: |
| `fast` | 84.148 s | 57.901 s | 31.19% | 29.57% |
| `slow` | 66.477 s | 47.089 s | 29.16% | 28.63% |

Time includes preflight, workers, merge, and complete final readback. The
subsequent independent audit is outside this timer. Every pair produced
byte-identical Parquets. The synthetic expectation covers business fields;
internal 32-field readback and physical equality also cover provenance.
Official reconciliation is a separate additional proof.

Median aggregate RSS for `fast` remained approximately stable: 640.86 to
642.42 MiB. For `slow`, it decreased from 492.79 to 407.54 MiB. Final readback
times went from 21.576 to 6.819 s for `fast` and from 16.486 to 5.260 s for `slow`.

The [raw report](benchmark-results/cotahist-optimization-20261006/parser-arrow-500k.json)
retains every sample, load, swap, input checksum, and module hash. These numbers
describe this workload and host; they are neither guaranteed throughput nor
a projection for the 27 official years.

## Final integrated version: repeated comparison

The final integration repeated three pairs per mode using the same `thread`
configuration, four sources, and 500,000 records. Other applications and the
real-data opt-in suite were active. Both versions had the same effective source
and worker counts within every pair.

| Mode | Starting median | Integrated median | Time reduction | CPU reduction |
| --- | ---: | ---: | ---: | ---: |
| `fast` | 96.363 s | 63.489 s | 34.11% | 29.34% |
| `slow` | 76.374 s | 50.380 s | 34.04% | 33.85% |

All six pairs improved wall time and CPU, and all 12 processes produced identical
Parquets within their pairs. Median aggregate RSS went from 679.44 to 665.44 MiB
in `fast` and from 453.68 to 405.96 MiB in `slow`.

The [integrated version report](benchmark-results/cotahist-optimization-20261006/final-integrated-500k.json)
preserves every sample and the compared source hashes. Host variation limits
the precision of the observed improvement; this measurement does not establish
a throughput guarantee for the complete annual corpus.

## Complete 2000–2026 acceptance

The [final acceptance](benchmark-results/cotahist-optimization-20261006/final-acceptance.json)
processed all 27 supplied annual sources, spanning 2000-01-03 through
2026-09-02, with the default `thread` backend and four requested workers.
Each mode read, selected, wrote, and verified 22,305,860 quotations, without
exclusions or missing years. Independent reconciliation checked all 32 fields
and every row's order. Physical Parquets matched between modes and the
historical acceptance.

The 27 frozen-manifest checksums also passed, as did preservation of the
previous 20 fields in 22,303,577 quotations and all 2,283 block-lot trades,
covering 345 distinct codes and an exact decimal volume total of
57,359,085,637.97. Cleanup left no active processes or temporary artifacts.

| Mode | API in earlier campaign | API in current campaign | Observed reduction |
| --- | ---: | ---: | ---: |
| `fast` | 3,895.088 s (64m55s) | 2,989.776 s (49m50s) | 23.24% |
| `slow` | 3,350.505 s (55m51s) | 2,297.342 s (38m17s) | 31.43% |

Each campaign ran one complete extraction per mode. Other machine processes
remained active, but the campaigns ran on different days and machine loads.
These percentages are historical observations, not a controlled causal
estimate or full-corpus median. The repeated 500,000-row comparison has its
own methodology and results, described above.

API times include preparation, extraction, merge, and full readback before
publication. The entire current campaign took 12,861.443 s, approximately
3h34m, including external audits, parity, and cleanup. This total measures
complete acceptance and does not replace the API processing timer.

The report states its code binding: the full campaign retained a 323-file
snapshot; a later correction affects only the process-preflight waiter, and
another change synchronizes a cancellation test. The other 321 files and the
rest of that module's AST remained identical. `thread` and `slow` do not call
the corrected waiter. The process correction passed official 2002–2003
acceptance again on a snapshot matching all 112 current product modules.
Local gates covered the current code and tests on all three supported Python
versions.

## Optional concurrent preflight

The default remains `GDF_B3_EXECUTOR_BACKEND=thread`. With explicit `process`
opt-in, `fast` admits concurrent preflight only with at least two workers
allowed by resource policy and at least 64 MiB of total stored annual
candidate sizes. This includes coexisting ZIP and TXT inputs, because both
require validation. `slow`, one source, one worker, or a smaller workload
retain serial preflight.

The threshold is conservative and measures stored bytes, not quotation count
or uncompressed size. Compression, source balance, CPUs, and memory affect
results. Size-read failures are deferred to canonical serial validation,
which preserves diagnostic order.

In three additional pairs, both sides used process extraction with 500,000
records across four sources. Concurrent preflight reduced the median from
34.294 to 25.514 s: 25.60% less time. Median total CPU increased from 67.295
to 81.940 s. This trades additional CPU for lower wall time; it does not
represent less computational work.

The [preflight report](benchmark-results/cotahist-optimization-20261006/preflight-process-500k.json)
records every sample, aggregate RSS, CPU, and compared version. All three pairs
produced the same Parquet. The implementation preserves source and first-error
order, typed causes, and worker shutdown before completing cancellation or failure.
Polling retrieves results completed at the wait boundary and preserves a
`TimeoutError` produced by the worker itself.

An [additional official acceptance](benchmark-results/cotahist-optimization-20261006/official-process-2002-2003.json)
used 2002-2003 ZIPs identical to the originals and coexisting equivalent TXT
files, totaling 77.69 MiB of candidates above the threshold. With `process`
requested, both modes independently reconciled all 32 fields of 278,085
quotations each, without exclusions or duplication from equivalent
representations. Ordered rows and physical Parquets matched between modes;
no workers or temporary artifacts remained after cleanup. This case proves
integrity, not a performance improvement.

```bash
mkdir -p .benchmarks
uv run --locked --no-sync python scripts/benchmark_ingestion.py \
  --scenario b3_multi_4x25k --rows 500000 --source-count 4 --worker-limit 4 \
  --backend process --processing-mode fast --repeats 3 \
  --output .benchmarks/b3-process-500k.json
```

## Accepting another change

The implementation passed local pre-push on Python 3.12.3, 3.13.9, and 3.14.0.
Each environment ran 2,330 deterministic tests and 200 validation-executor
tests. Product coverage, including branches, was 91.22%, 91.22%, and 91.12%,
respectively; executor coverage was 91.12% on all three. The audit of 116 locked
dependencies also passed. These are local results; remote CI execution and
publication are separate steps.

1. Freeze distinct baseline and candidate versions with product, support, and
   input hashes. Keep dependencies, selection, and resources identical within pairs.
2. Alternate fresh-process order, retain every sample, and measure the complete
   operation. CPU, aggregate RSS, and external audits have separate metrics.
3. Require equality of every value and occurrence, plus corruption, exclusion,
   zero-selected-source, and cancellation tests.
4. Reconcile the supplied official corpus in both modes on the final version;
   pass tests, hooks, and documentation checks before accepting the change.

Rust can be evaluated as a batch kernel if a material bottleneck remains after
these changes. That decision requires additional complete-operation benefit,
exact equivalence, and distribution compatible with supported Python versions.
An isolated microbenchmark does not justify changing the library's language.
