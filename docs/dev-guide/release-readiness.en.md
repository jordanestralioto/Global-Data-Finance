# Release Acceptance

Acceptance gathers evidence for the same candidate commit before publication.
The canonical [testing](testing.md), [transactional publication](../reference/transactional-publication.md),
[HTTP and retry](retry-strategy.md), and [logging](logging-system.md) contracts
remain in their owner documents.

## Required validation

| Environment | Execution |
| --- | --- |
| Linux, Python 3.12/3.13/3.14 | Complete deterministic suite, gates, product coverage, and real-validation executor coverage. |
| Windows/macOS, Python 3.12/3.13/3.14 | Native lock, recovery, ZIP, HTTP, retry, logging, CVM, and B3 regressions. |
| Linux, Python 3.13 | Complete process-crash and storage-failure campaign across eight shards. |
| Distributions | Wheel/sdist inspection and local CVM/B3 flows from independent installations. |

Both aggregate coverage floors remain 85%, including branches. The native
suite is focused; required cases must execute and pass. Windows error 1314
when creating symlinks may skip only that alias case. It cannot waive
publication or recovery executions.

The `tests.support.release_evidence` plugin records actual pytest outcomes
and rejects empty, entirely skipped, unfinished, or missing critical behavior.
Artifacts include JUnit, environment versions, and the candidate commit.

## Fault campaign

The campaign uses temporary directories, caller files, and small valid Parquet
payloads. It covers fresh/existing destinations and hard-link/copy backups.
Every operation is interrupted before and after execution; resulting states
receive further crashes during recovery. Three recovery attempts must retain
one complete old or new batch, according to the journal, without changing
caller files or leaving residues with established ownership.

It also injects ENOSPC/EIO, partial writes, persistent rollback failures, and
interrupted child cleanup. Each recovery phase receives storage failures.
The empty Windows guard file is persistent by contract and is not residue.

Run the complete local campaign:

```bash
GDF_PUBLICATION_REPORT_DIR=.cache/publication-campaign/reports \
uv run --locked --no-sync pytest \
  tests/macro_infra/test_publication_fault_campaign.py \
  -m "integration and slow" --no-cov
```

To partition it, set `GDF_PUBLICATION_SHARDS=8` and execute each
`GDF_PUBLICATION_SHARD` index from `0` through `7`, retaining reports together.
These variables configure test tooling rather than library runtime settings.
The complete campaign uses Linux processes; native suites use portable
checkpoints. Normal pytest collection does not start the slow campaign.

The verifier requires all four scenarios and every shard, derives expected
cases from operation traces, and rejects missing executions:

```bash
uv run --locked --no-sync python scripts/check_release_evidence.py \
  .cache/publication-campaign/reports --shards 8
```

Use `--shards 1` when verifying an unpartitioned campaign. Processes execute
real operations and terminate through `os._exit`; storage faults are injected
at the I/O boundary without filling the host disk.

## Packages and publication

After `uv build`, inspect metadata, safety modules, and both distribution
digests:

```bash
uv run --locked --no-sync python -m scripts.check_distributions dist
```

The release workflow requires the stable tag version through
`--expected-version`. Untagged local builds may have development versions.
Each distribution receives its own installation, and smoke checks run with
Python `-I` outside the checkout. They verify the loaded installation, public
exports, local CVM extraction, and ZIP/TXT B3 extraction in fast/slow modes.

The `release-acceptance` job requires quality, security, package checks,
every native environment, the complete campaign, coverage, and matching
downloaded artifact digests. A failed prerequisite produces a pending report
and blocks publication. Dry-run performs these checks without uploading to PyPI.

## Evidence and limitations

Acceptance and test artifacts remain available in the CI run for at least
30 days. Reports identify SHA, version, hashes, and execution URL, separating
`passed`, `failed`, `skipped`, and `external_failure`.
Acceptance uses evidence produced by CI, without depending on versioned
planning documents or review records in the repository.
Unavailable native environments or required executions keep acceptance pending.

Process-crash recovery does not establish universal power-loss durability or
simultaneous batch visibility during commit. The HTTP budget does not measure
total process memory. Ownership and the outer CVM lock contracts remain active.
