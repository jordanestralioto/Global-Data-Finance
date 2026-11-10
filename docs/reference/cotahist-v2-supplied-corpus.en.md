# Audit of the Supplied COTAHIST Corpus

This record preserves the independent audit of the local corpus used to plan
the v2 contract. Input hashes are stored in the versioned
[cotahist-v2-supplied-corpus.sha256](cotahist-v2-supplied-corpus.sha256)
manifest, with the actual names of all 27 ZIP files and each outer-file
SHA-256. The baseline audit used revision `c163c92f1a770fde0d3a6f6a83c2305e59a429bd`.

## Observed baseline

| Measurement | Audited result |
| --- | ---: |
| Years and files | 2000–2026, 27 ZIPs |
| Type-`01` source quotations | 22,305,860 |
| Rows in the previous Parquet | 22,303,577 |
| Omitted market `021` quotations | 2,283 |
| Distinct trading codes in market `021` | 345 |
| Exact `VOLTOT` sum for market `021` | BRL 57,359,085,637.97 |
| Official fields missing from the previous schema | 5 |
| Previous columns compared with the sources | 20; no differences |
| First trading date in the corpus | 2000-01-03 |
| Latest trading date in the corpus | 2026-09-02 |

The 2,283 market `021` quotations occur in 2023–2026. Volume was summed with
exact decimals. B3 documents `021` for BBT and Midpoint; original ticker values
retain their `Q` and `M` suffixes.

| Year | First date | Last date | Type-`01` quotations | Market `021` |
| ---: | --- | --- | ---: | ---: |
| 2000 | 2000-01-03 | 2000-12-28 | 153,682 | 0 |
| 2001 | 2001-01-02 | 2001-12-28 | 141,848 | 0 |
| 2002 | 2002-01-02 | 2002-12-30 | 129,973 | 0 |
| 2003 | 2003-01-02 | 2003-12-30 | 148,112 | 0 |
| 2004 | 2004-01-02 | 2004-12-30 | 166,937 | 0 |
| 2005 | 2005-01-03 | 2005-12-29 | 181,408 | 0 |
| 2006 | 2006-01-02 | 2006-12-28 | 198,367 | 0 |
| 2007 | 2007-01-02 | 2007-12-28 | 280,255 | 0 |
| 2008 | 2008-01-02 | 2008-12-30 | 284,235 | 0 |
| 2009 | 2009-01-02 | 2009-12-30 | 265,046 | 0 |
| 2010 | 2010-01-04 | 2010-12-30 | 287,480 | 0 |
| 2011 | 2011-01-03 | 2011-12-29 | 298,370 | 0 |
| 2012 | 2012-01-02 | 2012-12-28 | 330,633 | 0 |
| 2013 | 2013-01-02 | 2013-12-30 | 378,917 | 0 |
| 2014 | 2014-01-02 | 2014-12-30 | 392,228 | 0 |
| 2015 | 2015-01-02 | 2015-12-30 | 414,177 | 0 |
| 2016 | 2016-01-04 | 2016-12-29 | 466,734 | 0 |
| 2017 | 2017-01-02 | 2017-12-28 | 489,115 | 0 |
| 2018 | 2018-01-02 | 2018-12-28 | 580,155 | 0 |
| 2019 | 2019-01-02 | 2019-12-30 | 779,229 | 0 |
| 2020 | 2020-01-02 | 2020-12-30 | 1,251,646 | 0 |
| 2021 | 2021-01-04 | 2021-12-30 | 1,831,862 | 0 |
| 2022 | 2022-01-03 | 2022-12-29 | 2,117,440 | 0 |
| 2023 | 2023-01-02 | 2023-12-28 | 2,257,424 | 30 |
| 2024 | 2024-01-02 | 2024-12-30 | 2,635,561 | 346 |
| 2025 | 2025-01-02 | 2025-12-30 | 3,174,698 | 539 |
| 2026 | 2026-01-02 | 2026-09-02 | 2,670,328 | 1,368 |

## Controls and omitted fields

The 2025 and 2026 trailers declare quotations only, while earlier files include
the `00` and `99` controls in their totals. Each file's quotation count was
confirmed by reading every type-`01` line; the control difference is exactly
two records.

| Official field missing before v2 | Rows with nondefault values |
| --- | ---: |
| `PRAZOT` | 1,445,095 |
| `MODREF` | 22,305,860 |
| `PREEXE` | 15,196,391 |
| `INDOPC` | 10,395 |
| `PTOEXE` | 323,647 |

## Scope of this evidence

These figures describe the bytes of the frozen files in the manifest; they do
not verify an external trading calendar or instrument registry. The local
corpus does not include 1986–1999 or dates after 2026-09-02. A later v2 campaign
recorded complete reconciliation of all 32 fields and row order, along with
the 27 manifest checksums; see the
[2000–2026 acceptance](../dev-guide/cotahist-performance.md#complete-20002026-acceptance).
These results are historical. A new campaign must recheck input hashes and
reconcile the data before using these numbers as acceptance criteria.

## Supplementary 2025–2026 acceptance on 2026-11-09

A new campaign reconciles the current official 2025 and 2026 sources through
the 2026-11-06 trading session. It supplements the baseline above without
replacing its hashes or attributing later records to its September snapshot.

| Measure | Result |
| --- | ---: |
| 2025 quotations | 3,174,698 |
| 2026 quotations | 3,429,676 |
| Rows verified in each mode | 6,604,374 |
| Observed date range | 2025-01-02 to 2026-11-06 |
| `fast`/`slow` parity | Exact equality of every record and its order |
| Verification | Independent raw-to-Parquet oracle, schema v2 |
| Total time, including readback and reconciliation of both modes | 2,936.14 s |
| Active processes or temporary files after cleanup | None |

The official 2026 ZIP has SHA-256
`26f2a0c96e37f2cfdca02e467f472d764a91e1c908a38edc0002c2c8ef913021`.
Physical line 2,072,135, dated 2026-10-22 with ticker `FR0T5L`, occupies 246
UTF-8 bytes. [Rejection of the original](../dev-guide/benchmark-results/cotahist-release-20261109/official-2026-rejection.json)
is expected and preserves existing output: the contract still requires 245
bytes. The campaign used a TXT copy strictly converted from UTF-8 to Latin-1,
changing only this record while retaining the original. Its SHA-256 is
`44ee9ffb6bc33d1d205d17966d6e7d5108c4b014b55b5290cff43ee63dfe5be6`.

Executor-generated artifacts remain separate: [manifest](../dev-guide/benchmark-results/cotahist-release-20261109/manifest.json),
[complete result](../dev-guide/benchmark-results/cotahist-release-20261109/results.jsonl),
[summary](../dev-guide/benchmark-results/cotahist-release-20261109/summary.json),
and [conversion provenance](../dev-guide/benchmark-results/cotahist-release-20261109/source-normalization.json).
Reconciliation also compares the original 20 fields and all 2,671 quotations
in market `021`. The ordered logical digest is
`19f73a7a8471d38c2c592ea50d904c53dbacf2b036b4d5291dda63b1dbf7835d`.
This local Linux run does not replace final-commit acceptance in CI.

To reproduce, retain source hashes and prepare the copy following the
[encoding guide](../user-guide/b3-docs.en.md#diagnose-utf-8-text-in-records-with-an-invalid-width),
leaving only the 2025 ZIP and converted 2026 TXT in the selected directory:

```bash
uv run --locked --no-sync python scripts/real_validation.py \
  --source cotahist --cotahist-path /external/path/inputs \
  --initial-year 2025 --last-year 2026 --cotahist-mode all \
  --case cotahist-multi-parity-2025-2026 \
  --report /external/path/report --timeout 3600 --progress
```

Official format and offsets: [B3 historical series layout](https://www.b3.com.br/data/files/33/67/B9/50/D84057102C784E47AC094EA8/SeriesHistoricas_Layout.pdf).
