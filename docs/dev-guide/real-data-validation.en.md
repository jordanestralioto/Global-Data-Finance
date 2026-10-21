# Validation with external data

## Run

To audit the complete matrix without relying on implicit environment
configuration, run the opt-in executor with every path supplied explicitly.
Keep the report and temporary artifacts outside the repository:

```bash
uv run --locked --no-sync python scripts/real_validation.py \
  --source all \
  --cotahist-path /external/path/COTAHIST \
  --cvm-output /tmp/globaldatafinance-cvm-output \
  --report /tmp/globaldatafinance-real-validation/first-run \
  --timeout 3600
```

## Scope and validation

`all` creates COTAHIST cases for every local catalog year in the requested
range (or every available year when the range is omitted) and valid
combinations in the seven CVM document windows, including IPE since 2003.
A missing year in the requested range fails the campaign before processing. With
`--cotahist-mode all`, every year gets a `fast` proof and a complete
`fast`/`slow` parity; the campaign also includes complete multi-year parity
over the full range. Preparation checks names, containers, years, and hashes
and applies ZIP precedence. Coexisting ZIP/TXT representations of one year
still require identical complete contents. Every quotation is validated by
the API before publication and by independent reconciliation; preparing the
manifest does not repeat that complete parsing pass. Invalid containers
prevent campaign creation; invalid quotation fields produce a `failed` case
without API publication. COTAHIST is never downloaded by the executor. The CVM
matrix contacts only the official URLs defined explicitly in code and
classifies HTTP 404/410 as `not_published`,
network unavailability as `external_failure`, and invalid content or processing
failures as `failed`.

For CVM, `--verify-cvm-catalog` writes `cvm-catalog.json` with all published
years and selection omissions. If a published year of the selected documents
is outside the matrix, the campaign stops with exit code 1; omit this option
for intentionally partial campaigns. Every CSV is reconciled field by field by an
independent parser, including headers, ordering, empty fields, and counts.
Results record hashes for every ZIP member, attachments, and compared fields.
For complete CVM history, use `--initial-year 2003 --document all`; ZIPs the
facade retains in the isolated workspace are removed by the executor only
after evidence is persisted, along with other campaign artifacts.

## Historical baseline and monitoring

By default, COTAHIST campaigns reconcile caller-provided inputs against the
checksums frozen in that run's own manifest. Selecting 2000–2026 does not
implicitly require the historical corpus used in the initial audit. To require
that specific corpus, its 27 checksums, and historical metrics, explicitly
select multi-year parity with `--cotahist-frozen-baseline`:

```bash
uv run --locked --no-sync python scripts/real_validation.py \
  --source cotahist --cotahist-path /external/path/COTAHIST \
  --initial-year 2000 --last-year 2026 --cotahist-mode all \
  --cotahist-frozen-baseline --case cotahist-multi-parity-2000-2026 \
  --report /external/path/cotahist-historical-acceptance --timeout 43200 --progress
```

`--progress` writes preparation, case start/results, and updates every 30
seconds while the worker is active to stderr. Stdout retains the final JSON
summary. Extraction, Parquet validation, and reconciliation stages appear in
the individual case log. Activity updates are not row progress and do not
prove the current stage is free of blocking. Full campaigns read every
quotation in both modes and can take hours; do not launch a second campaign
to replace one that is still active.

`--cotahist-frozen-baseline` requires the complete range and selection of
the multi-year case.
The case persists this intent as `frozenBaseline`, preserved by `--resume`;
resume cannot switch a generic campaign to historical acceptance. Use a new
report directory to change this selection. Without `--resume`, the CLI rejects
directories with previous campaign evidence and preserves their files.
Output paths are resolved consistently,
including a symlink in directory ancestry; destination containment and the
exactly-one-Parquet requirement remain mandatory.

In the COTAHIST campaign, extraction-reported `DiskFullError` and
`PathPermissionError` are `external_failure`; original diagnostics remain in
the report. Invalid content and integrity mismatches remain `failed`.

## Reports and resuming

Each case runs in an isolated process. The directory supplied to `--report`
contains `manifest.json`, one current result per case in `results.jsonl`,
`summary.json`, individual logs, and artifact evidence. Use `--resume
--report <same-directory>` to rerun only `external_failure` cases or cases
that have not been classified; functional results and `not_published` cases
are preserved. Persisted results are caller-owned evidence, not a signed
attestation: use `--resume` only with a trusted report directory when a
pass/fail conclusion must serve as evidence. Before resuming, every COTAHIST
input is compared with the
manifest `inputSizeBytes` and `inputSha256`. A shared path is hashed once;
any drift raises `ReportFormatError`, does not rerun or overwrite old results,
and requires a new campaign. The COTAHIST `caseId`, year, mode, and input must
also agree with the current catalog. CVM resume first validates the persisted
`campaign.cvmOutput` with the external-destination policy, then rebuilds cases
from the official document/year matrix: persisted fields, including
`inputPath`, `url`, and `outputRoot`, must match both the rebuilt case and the
campaign destination before a worker starts. A tampered `outputRoot` fails
before `mkdir`, `mkdtemp`, a worker, or an HTTP client. The CVM probe uses only
the canonical HTTPS endpoint, does not follow redirects, and never persists a
preflight body. The compressed-archive byte limit is enforced from
both `Content-Length` and the public-facade stream; the recorded hash is taken
from the ZIP immediately before that facade extracts it. `--report` and
`--cvm-output` pass through the sensitive-destination policy before any
directory is created; system roots, protected directories, relative Windows
drives, and untrusted UNC paths are rejected, while `/tmp` and an explicitly
allowed UNC root can be used under the shared policy. Exit code `0` is reserved
for a fully executed matrix with no functional failures, external failures,
unexecuted combinations, or orphan processes; `1` indicates a functional
failure, and `2` indicates an external dependency, timeout, incomplete
execution, or orphan process. I/O, report-format, security, or campaign
configuration failures handled as `invalid_campaign` return `3`. Argument
syntax errors return `2` through `argparse`.

## Related contracts

- [Auditable campaign decision](../decisions/real-validation-campaign.md)
- [Audited COTAHIST corpus](../reference/cotahist-v2-supplied-corpus.md)
- [Release acceptance](release-readiness.md)
