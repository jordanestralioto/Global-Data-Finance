# Global-Data-Finance

Python library for obtaining CVM regulatory filings and converting B3 historical
quotes to Parquet. Requires Python `>=3.12,<4.0`.

| Source | Input | Result |
| --- | --- | --- |
| CVM | Download of selected filings | Original ZIP and optional Parquet conversion |
| B3 | Annual files supplied by the user | Consolidated Parquet and integrity report |

The B3 extractor accepts local ZIP or TXT files: `COTAHIST_A{YYYY}.ZIP` and
`COTAHIST_A{YYYY}.TXT`. The files must exist before extraction.

## Use the library

```bash
python -m pip install globaldatafinance
```

Start with the [quickstart](user-guide/quickstart.md): one CVM download and one
B3 extraction, including result checks.

| I need to… | Page |
| --- | --- |
| Set up an environment | [Installation](user-guide/installation.md) |
| Choose documents and years | [CVM guide](user-guide/cvm-docs.md) |
| Prepare COTAHIST and filter markets | [B3 guide](user-guide/b3-docs.md) |
| Run examples or resolve a question | [Examples](user-guide/examples.md) · [FAQ](user-guide/faq.md) |

## Develop the project

Follow [contributing](dev-guide/contributing.md) to set up the environment and
validate a change. The [architecture](dev-guide/architecture.md) shows where
responsibilities belong; the [testing guide](dev-guide/testing.md) explains
commands and test classification.

## Look up details

Use the [API reference](dev-guide/api-reference.md) for signatures, results,
schemas, and exceptions. Configuration, operation, and migrations are grouped
under the reference; benchmarks, external campaigns, and decisions are in the
maintenance section of the developer guide.
