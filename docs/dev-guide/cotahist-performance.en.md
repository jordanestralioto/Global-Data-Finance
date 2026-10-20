# COTAHIST performance and integrity

## Optimization contract

The 2026-10-06 optimizations preserve public signatures, schema v2, output
names, and market selection. All 32 fields, exact decimals, original bytes,
provenance, order, and repeated occurrences remain verified before publication.
CRC, source identity, replay, and complete final readback remain mandatory.

The current implementation validates readback coordinates with Arrow reductions
within contiguous source segments. Required nulls are rejected first; a failing
segment uses scalar diagnostics to preserve the first invalid row. Preflight
keeps a validated container open through the 64 KiB content hash and strict scan.
The worker validates a fresh container and hashes actual converted Arrow batches
against the independent canonical preflight digest. Fixed binary framing reads
Arrow buffers with their slice offsets; schema v2 and digest framing are unchanged.

## Refactor closure: 2026-10-20

The project owner accepted and closed the refactor on 2026-10-20. By explicit
decision, the minimum 20% improvement target was removed from the acceptance
requirements. The real gains demonstrated in the controlled 2026-10-19
comparison were accepted as sufficient for closure, together with the reviewed
corrections and data-integrity and contract checks. No minimum performance
percentage remains pending for this delivery.

Measured percentages remain bound to the 2026-10-19 snapshot. The supplemental
final-version campaign confirmed data integrity, but its timing result remains
inconclusive and establishes no new reliable percentage. Increased CPU and RSS
remain documented as costs of the observed gains.

Original reports and samples remain preserved, including records of the unmet
target while it was still required. This decision supersedes that requirement
for closing the refactor.

## Current executor policy

`HistoricalQuotesB3()` defaults to `process`. Eligible `fast` extraction uses
spawned workers with at least two resolved sources and two workers allowed by
resource policy. `slow`, one source, or a one-worker limit use one thread worker.
Daemons and callers without an importable main module or readable script fall
back before submission; the logger records the reason and execution telemetry
reports the actual backend. Pool and worker failures retain normal diagnostics
and cleanup. Scripts must guard extraction with `if __name__ == '__main__':`.
Explicit `GDF_B3_EXECUTOR_BACKEND=thread` and `process` remain supported.

The parser produces a canonical tuple directly and applies a layout-derived
plan that reuses existing scalar validators. The digest uses constant tag and
length tables. Final readback builds the same v2 framing with Arrow in bounded
source segments. These tables do not store financial values. See the
[digest contract](../reference/b3-schema-v2.en.md).

## Review follow-up: 2026-10-20

Preflight validates the path and captures the outer hash before opening the
handle used for the content hash and scan. The final pathname check remains.
A rename replacement in this window is therefore rejected during preflight,
without producing a descriptor that mixes two files. Regressions cover TXT and
ZIP, before and after opening, through the validator and facade, including
handle cleanup and absence of publication.

The old `_ProcessingModeConfig`, the four resource properties on
`ProcessingModeEnumB3` without production consumers, and the uncalled
`validate_one_temp_file()` helper were also removed. `ResourcePolicyB3` continues
to own the effective policy; removal of the exported properties was authorized.

The complete 72-observation comparison below belongs to the 2026-10-19 snapshot
before this correction and was not repeated. Its historical gains and increased
RSS and CPU remain bound to that version. The closure decision above accepts
this evidence without requiring a minimum improvement percentage.

A supplemental final-version campaign on 2026-10-20 ran 18 complete extractions
for one ZIP with 100,000 quotations: three alternating pairs for each of
`slow/thread`, `fast/thread` and `fast/process`. Product snapshots, dependencies
and input bytes were checked; all 32 fields and schema metadata matched, and
two independent reconciliations checked 100,000 rows each. Timing was
inconclusive: identical-version `fast/process` runs ranged from 12.44 to 18.77 s
for the baseline and from 10.35 to 15.13 s for the candidate. The three paired
reductions were 16.75%, 44.66% and 17.14%. Host variation prevents treating the
nominal medians as new acceptance evidence. The
[supplemental report](benchmark-results/cotahist-processing-final-20261020/comparison.json)
retains every sample, CPU/RSS measurements, provenance, independent audits and
limitations. The last accepted controlled default comparison remains 15.41%.

Separate profiling located the largest preflight costs in canonical scalar
field conversion and the independent scalar digest. A small framing experiment
showed no measurable benefit and was discarded; product code is unchanged by
this supplemental campaign.

## Complete API comparison: 2026-10-19

Three pairs per configuration ran sequentially in fresh Python processes, in
alternating order, for 72 accepted observations. Environment: Python 3.13.9,
PyArrow 23.0.1, Linux x86_64, eight logical CPUs and 7.55 GiB RAM. Both versions
used the same locked dependencies, input bytes, all-market selection and four
requested workers. One source and `slow` used one thread worker. Stored TXT
inputs for four sources exceed the 64 MiB preflight threshold; ZIP inputs do not.

The timer includes construction, preflight, worker replay, full Parquet readback
and transactional publication. Independent reconciliation has its own timer.
All 32 fields, occurrences, order and complete schema metadata matched across
versions and modes. Eight independent raw audits verified 2,400,000 rows in total.

| Sources / quotations | Input | Mode / requested backend | Baseline API (s) | Candidate API (s) | Reduction |
| -------------------- | ----- | ------------------------ | ---------------: | ----------------: | --------: |
| 1 / 100,000          | TXT   | `slow/thread`            |            9.019 |             7.812 |    13.39% |
| 1 / 100,000          | TXT   | `fast/thread`            |            9.435 |             7.981 |    15.41% |
| 1 / 100,000          | TXT   | `fast/process`           |            9.496 |             8.057 |    15.15% |
| 1 / 100,000          | ZIP   | `slow/thread`            |            9.733 |             8.099 |    16.79% |
| 1 / 100,000          | ZIP   | `fast/thread`            |            9.604 |             8.133 |    15.32% |
| 1 / 100,000          | ZIP   | `fast/process`           |            9.563 |             8.124 |    15.04% |
| 4 / 500,000          | TXT   | `slow/thread`            |           46.889 |            39.480 |    15.80% |
| 4 / 500,000          | TXT   | `fast/thread`            |           46.113 |            37.736 |    18.17% |
| 4 / 500,000          | TXT   | `fast/process`           |           25.171 |            20.518 |    18.49% |
| 4 / 500,000          | ZIP   | `slow/thread`            |           48.029 |            40.048 |    16.62% |
| 4 / 500,000          | ZIP   | `fast/thread`            |           51.285 |            42.172 |    17.77% |
| 4 / 500,000          | ZIP   | `fast/process`           |           35.419 |            29.426 |    16.92% |

Changing from the previous default (`fast/thread`) to the new eligible default
(`fast/process`) reduced the median by **55.51% for TXT** (46.113 to 20.518 s)
and **42.62% for ZIP** (51.285 to 29.426 s) with four sources. The one-source ZIP
default comparison improved **15.41%**. No matched mode/backend showed a time
regression in that campaign.

Memory increased in the multi-source fast profiles: **24.31% for threads/TXT**,
**37.29% for threads/ZIP**, and **24.16% for processes** in both formats.
Separate instrumentation observed up to four concurrent digest updates, batches
bounded to 25,000 rows, and worker Arrow high-water allocation rising from 64.0
to 106.5 MiB. After each source, only 17,536 Arrow bytes remained for constant
prefix tables; RSS also includes allocator reservations. These observations
locate the additional framing buffers and preserve the existing buffering limits.

The backend switch itself adds **46.78% aggregate RSS for TXT** and **47.16% for
ZIP**, comparing candidate threads with candidate processes. Including both code
and backend changes, median RSS moves from 676.12 to 1,233.73 MiB for TXT and
613.48 to 1,239.46 MiB for ZIP. Total API CPU moves from 50.06 to 72.18 s and
53.71 to 60.09 s, respectively. Lower elapsed time therefore has a CPU and memory
cost. Aggregate RSS can count shared pages more than once. RSS sampling covers
the native runner's API and bounded post-API comparison; raw audits are separate.

The caller-provided 2023 ZIP separately passed both modes: **2,257,424 quotations
per mode**, all 32 fields independently reconciled, exact ordered parity and no
remaining workers. Its SHA-256 is
`ad1603788d78aaa1de806498572277f1d9443f88ae116452751b5800cb23523e`.
This campaign overlapped quality gates and provides integrity evidence.

| Synthetic workload | Combined input SHA-256                                             |
| ------------------ | ------------------------------------------------------------------ |
| 1-100000-txt       | `253a8e7e8448b25b8293cef8d130a3821a161682ca15dc17ffe1e9e6ab0c0646` |
| 1-100000-zip       | `410e7200bbb04bb7b4af8a75164d34dd8153ed7203ccf3247f46dea37697d9e0` |
| 4-500000-txt       | `3847bb6d8f4bac24449f623c1255acbd80625b4f8b98f0a3dcd111639321ab1d` |
| 4-500000-zip       | `b618ff2947498c82d022c7fb2ffe0c0d9016f60bbaafef885f36cd80f4ddd366` |

The [comparison and phase metrics](benchmark-results/cotahist-processing-20261019/comparison.json)
link every raw sample. [Provenance](benchmark-results/cotahist-processing-20261019/provenance.json)
binds product/support hashes, dependencies and individual inputs.
[Memory investigation](benchmark-results/cotahist-processing-20261019/memory-investigation.json),
[independent audits](benchmark-results/cotahist-processing-20261019/independent-audits.json),
[annual reconciliation](benchmark-results/cotahist-processing-20261019/annual-2023.json)
and the [env-unset default smoke](benchmark-results/cotahist-processing-20261019/default-smoke.json)
are retained separately. The [validation report](benchmark-results/cotahist-processing-20261019/validation.json)
records gate results and the criteria in force at the time of the campaign;
the closure above removes the percentage requirement. Instrumented single-ZIP counts changed from 4 to 2
complete CRC scans and 7 to 5 decompressions; hash-pass record contexts changed
from 4 to 0 on a two-quotation fixture, with every archive closed.

The synthetic corpus has one trading day per year, market 010 and balanced
sources. Three observations per version/configuration and warm OS file caches
limit precision and extrapolation. These are measured workloads, not a
throughput guarantee for another machine or the complete annual corpus.

```bash
uv run --locked --no-sync python scripts/benchmark_ingestion.py \
  --scenario b3_multi_4x25k --rows 500000 --source-count 4 --worker-limit 4 \
  --b3-input-format zip --backend process --processing-mode fast --repeats 3 \
  --output .benchmarks/b3-processing-zip.json
```

The native CLI defaults to TXT and selects stocks; the controlled comparison
used `todos` through its operation seam. The archived coordinator preserves that
selection and alternates distinct snapshots. The 2026-10-06 sections below are
historical measurements of earlier versions and campaigns.

## Parser and final readback: distinct-version comparison

Three pairs per mode processed the same 500,000 records across four sources,
in alternating fresh Python processes. Environment: Python 3.13.9, PyArrow
23.0.1, Linux x86_64, eight CPUs, with other host processes running. The
requested backend was `thread`; `slow` retained one worker.

| Mode   | Starting median | Optimized median | Time reduction | CPU reduction |
| ------ | --------------: | ---------------: | -------------: | ------------: |
| `fast` |        84.148 s |         57.901 s |         31.19% |        29.57% |
| `slow` |        66.477 s |         47.089 s |         29.16% |        28.63% |

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

| Mode   | Starting median | Integrated median | Time reduction | CPU reduction |
| ------ | --------------: | ----------------: | -------------: | ------------: |
| `fast` |        96.363 s |          63.489 s |         34.11% |        29.34% |
| `slow` |        76.374 s |          50.380 s |         34.04% |        33.85% |

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

| Mode   | API in earlier campaign | API in current campaign | Observed reduction |
| ------ | ----------------------: | ----------------------: | -----------------: |
| `fast` |    3,895.088 s (64m55s) |    2,989.776 s (49m50s) |             23.24% |
| `slow` |    3,350.505 s (55m51s) |    2,297.342 s (38m17s) |             31.43% |

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

## Concurrent preflight

The 2026-10-06 campaign used the then-default `thread` backend. Under the current
`process` default or explicit process selection, `fast` admits concurrent preflight
only in a compatible spawn context with at least two workers
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
