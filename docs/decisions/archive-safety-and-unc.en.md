# ZIP limits and allowlisted UNC destinations

**Status:** Accepted
**Date:** 2026-08-31
**Scope:** shared archive security and caller-provided destinations

## Context

CVM and B3 consume ZIP archives obtained from external sources. Streaming
avoids `extractall()`, but does not itself bound the CPU, disk, or memory cost
of an archive with many members, deceptive metadata, or excessive expansion.
Both sources also receive caller-provided destinations. Blocking only selected
POSIX directories does not protect Windows drive roots or UNC paths.

## Decision

`core/archive_safety.py` owns the reusable ZIP policy. Before CRC, parsing, or
writes, CVM and B3 validate compressed size, member count, individual and
total uncompressed sizes, compression ratio, encryption, absolute or `..`
names, links/special types, output-name duplicates after case-insensitive
normalization, and collisions where a file is an ancestor of another member.
Each component is also checked against Win32 semantics: ambiguous separators,
ADS, invalid characters, trailing dot/space, and reserved DOS device names are
rejected. Each decompressed stream is also counted while reading, so false
metadata cannot authorize more bytes than the policy permits.

The limits are typed global configuration:

| Variable | Default |
| --- | ---: |
| `DATAFINANCE_ARCHIVE_MAX_ARCHIVE_BYTES` | 2 GiB |
| `DATAFINANCE_ARCHIVE_MAX_MEMBERS` | 10,000 |
| `DATAFINANCE_ARCHIVE_MAX_MEMBER_UNCOMPRESSED_BYTES` | 2 GiB |
| `DATAFINANCE_ARCHIVE_MAX_TOTAL_UNCOMPRESSED_BYTES` | 8 GiB |
| `DATAFINANCE_ARCHIVE_MAX_COMPRESSION_RATIO` | 200.0 |

Values are positive, have defensive upper bounds, and are validated while
creating `Settings`; the allowed total cannot be lower than the per-member
limit.

`assert_path_not_sensitive()` remains the single shared destination policy. It
blocks `/`, roots of every Windows drive, `Windows`, `Program Files`, and
`Program Files (x86)` on every drive, as well as sensitive POSIX directories.
UNC is denied by default. The only exception is a path equal to or below a
root in the JSON list `DATAFINANCE_PATH_SAFETY_ALLOWED_UNC_ROOTS`;
administrative shares ending in `$` remain forbidden even in that list.

## Consequences

- Sources retain source-owned naming rules: CSV belongs to CVM and
  `COTAHIST` belongs to B3; only generic limits and security are shared.
- Rejected input fails before material decompression or any write.
- Limits reduce denial-of-service exposure, but an archive within a permitted
  ceiling may still consume resources up to that ceiling.
- This is a defense for caller-provided destinations. It does not claim to
  constrain a caller that already has the process's privileges.
- The library never loads `.env` implicitly. The caller must export variables
  or explicitly use `uv run --env-file ...` when running a local process.
