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

Official format and offsets: [B3 historical series layout](https://www.b3.com.br/data/files/33/67/B9/50/D84057102C784E47AC094EA8/SeriesHistoricas_Layout.pdf).
