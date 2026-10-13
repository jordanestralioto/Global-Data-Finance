# CVM exact text preservation migration

The `exact-text-v1` contract writes every CVM column as Arrow `string`.
This changes persisted schemas: consumers depending on inferred `int64`,
`uint64`, `float64`, booleans, or nulls must migrate explicitly.
The original ZIP remains available after successful extraction.

| CSV input | Previous Parquet | `exact-text-v1` Parquet |
| --- | --- | --- |
| `000012345` | Integer without leading zeroes | `"000012345"` |
| `1.234567890123456789` | Rounded `float64` decimal | `"1.234567890123456789"` |
| `1e-400` | `0.0` | `"1e-400"` |
| `N/A`, `NULL`, `None` | Inferred null | Original text |
| Empty field | Inferred null | `""` |
| `TrUe` | Boolean | `"TrUe"` |
| Header-only CSV | Arrow `null` columns | Arrow `string` columns, zero rows |

## Regeneration and consumer cutover

1. Keep original ZIPs and previous output during migration.
2. Regenerate Parquets in a new directory using `automatic_extractor=True`.
   The download-only default, `automatic_extractor=False`, remains available.
3. Check `has_errors()` and completed `{DOC}_{YEAR}` identities.
4. Check regenerated files for `cvm.contract=exact-text-v1` metadata.
5. Convert only required columns according to your data dictionary and test
   those consumers before switching the directory read by the application.

A previous Parquet that already rounded values or removed zeroes cannot
recover original text. Regeneration requires the corresponding ZIP or a new
official download. Combining previous and new schemas in one dataset can
cause incompatibility or coercion; migrate into a new destination.

```python
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq

path = Path("cvm-exact/DFP/2024/dfp_cia_aberta_DRE_con_2024.parquet")
table = pq.read_table(path)
assert table.schema.metadata[b"cvm.contract"] == b"exact-text-v1"

raw_value = table.column("VL_CONTA")[0].as_py()
amount = Decimal(raw_value) if raw_value else None
```

Financial conversion also requires interpreting currency, scale, reporting
period, version, and statement type according to the CVM dataset. The pipeline
preserves supplied fields; accounting consistency of the declared filing
remains a consumer business validation.

## Integrity and operation

Before publication, the pipeline compares a SHA-256 of all decoded records
with the reopened Parquet content. Metadata includes `cvm.contract`,
`cvm.content-sha256`, `cvm.source-archive`, `cvm.source-archive-sha256`,
`cvm.source-member`, and
`cvm.source-encoding`. Extraction confirmation requires every expected Parquet
and its association with the consumed ZIP. Page checksums, complete reads,
and `fsync` protect persisted publication.

Every pass reads the same opened ZIP; source changes abort extraction before
publication. If a ZIP revision removes or renames a CSV, obsolete Parquets
owned by that archive block reprocessing into the same destination. Keep
previous outputs and regenerate the revision into a clean directory;
the library does not automatically delete old files.

Quotes remain literal under the `QUOTE_NONE` dialect. Short rows receive
trailing empty fields; the retained ZIP preserves the distinction between
absent and empty fields. Excess fields, empty or duplicate headers, more than
4,096 columns, and physical records exceeding 8 MiB in UTF-8 fail explicitly.
Row groups contain up to 50,000 rows, reduced to respect an estimated 16 MiB
data and offset budget; this budget is not an absolute process RSS limit.

UTF-8 and UTF-8 BOM are validated completely. For non-UTF-8 sources, the
documented policy distinguishes CP1252 and Latin-1 from observed bytes.
An input without an encoding declaration can be ambiguous; original ZIP
bytes remain available for independent inspection.

Concurrent calls to one destination fail before ZIP replacement.
`.cvm-write-lock/owner.json` identifies the owning process. After abrupt
termination, the library retains that lock and requires explicit inspection
before recovery: confirm no active writer exists, preserve evidence, and
recover derived transaction state. The library never automatically takes
an unverifiable lock. Failures remain in the result; a Parquet's existence
alone does not establish success.

IPE now includes 2003 onward. `get_available_years().ipe_min_year` exposes that
minimum as a property; the four tuple fields continue to describe general
documents, ITR, CGVN/VLMO, and the current year.

See the [CVM reference](../reference/cvm-api.en.md) and
[testing guide](../dev-guide/testing.en.md) for the official campaign with
independent comparison of every file and record.
