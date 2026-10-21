# Auditoria do corpus COTAHIST fornecido

Este registro preserva a auditoria independente do corpus local usado para
planejar o contrato v2. Os hashes de entrada ficam no manifesto versionado
[cotahist-v2-supplied-corpus.sha256](cotahist-v2-supplied-corpus.sha256), com
nomes reais dos 27 ZIPs e SHA-256 de cada arquivo externo. A auditoria-base
partiu da revisão `c163c92f1a770fde0d3a6f6a83c2305e59a429bd`.

## Linha de base observada

| Medida | Resultado auditado |
| --- | ---: |
| Anos e arquivos | 2000–2026, 27 ZIPs |
| Cotações type `01` nas fontes | 22.305.860 |
| Linhas do Parquet anterior | 22.303.577 |
| Cotações ausentes do mercado `021` | 2.283 |
| Códigos de negociação distintos no mercado `021` | 345 |
| Soma exata de `VOLTOT` no mercado `021` | BRL 57.359.085.637,97 |
| Campos oficiais ausentes do schema anterior | 5 |
| Colunas antigas comparadas contra as fontes | 20; nenhuma diferença |
| Primeira data de negociação no corpus | 2000-01-03 |
| Última data de negociação no corpus | 2026-09-02 |

As 2.283 cotações `021` aparecem em 2023–2026. O volume foi somado com
decimais exatos. A B3 documenta `021` para BBT e Midpoint; os tickers originais
mantêm os sufixos `Q` e `M`.

| Ano | Primeira data | Última data | Cotações `01` | Cotações `021` |
| ---: | --- | --- | ---: | ---: |
| 2000 | 2000-01-03 | 2000-12-28 | 153.682 | 0 |
| 2001 | 2001-01-02 | 2001-12-28 | 141.848 | 0 |
| 2002 | 2002-01-02 | 2002-12-30 | 129.973 | 0 |
| 2003 | 2003-01-02 | 2003-12-30 | 148.112 | 0 |
| 2004 | 2004-01-02 | 2004-12-30 | 166.937 | 0 |
| 2005 | 2005-01-03 | 2005-12-29 | 181.408 | 0 |
| 2006 | 2006-01-02 | 2006-12-28 | 198.367 | 0 |
| 2007 | 2007-01-02 | 2007-12-28 | 280.255 | 0 |
| 2008 | 2008-01-02 | 2008-12-30 | 284.235 | 0 |
| 2009 | 2009-01-02 | 2009-12-30 | 265.046 | 0 |
| 2010 | 2010-01-04 | 2010-12-30 | 287.480 | 0 |
| 2011 | 2011-01-03 | 2011-12-29 | 298.370 | 0 |
| 2012 | 2012-01-02 | 2012-12-28 | 330.633 | 0 |
| 2013 | 2013-01-02 | 2013-12-30 | 378.917 | 0 |
| 2014 | 2014-01-02 | 2014-12-30 | 392.228 | 0 |
| 2015 | 2015-01-02 | 2015-12-30 | 414.177 | 0 |
| 2016 | 2016-01-04 | 2016-12-29 | 466.734 | 0 |
| 2017 | 2017-01-02 | 2017-12-28 | 489.115 | 0 |
| 2018 | 2018-01-02 | 2018-12-28 | 580.155 | 0 |
| 2019 | 2019-01-02 | 2019-12-30 | 779.229 | 0 |
| 2020 | 2020-01-02 | 2020-12-30 | 1.251.646 | 0 |
| 2021 | 2021-01-04 | 2021-12-30 | 1.831.862 | 0 |
| 2022 | 2022-01-03 | 2022-12-29 | 2.117.440 | 0 |
| 2023 | 2023-01-02 | 2023-12-28 | 2.257.424 | 30 |
| 2024 | 2024-01-02 | 2024-12-30 | 2.635.561 | 346 |
| 2025 | 2025-01-02 | 2025-12-30 | 3.174.698 | 539 |
| 2026 | 2026-01-02 | 2026-09-02 | 2.670.328 | 1.368 |

## Controles e campos omitidos

Os trailers de 2025 e 2026 declaram apenas as cotações, enquanto os arquivos
anteriores incluem os controles `00` e `99` na contagem. O total de cada arquivo
foi confirmado pela leitura de todas as linhas `01`; a diferença dos controles
é exatamente duas linhas.

| Campo oficial ausente antes do v2 | Linhas com valor não padrão |
| --- | ---: |
| `PRAZOT` | 1.445.095 |
| `MODREF` | 22.305.860 |
| `PREEXE` | 15.196.391 |
| `INDOPC` | 10.395 |
| `PTOEXE` | 323.647 |

## Escopo desta evidência

Esses números descrevem os bytes dos arquivos congelados no manifesto, não uma
verificação contra calendário ou cadastro externo de instrumentos. O corpus
local não contém 1986–1999 nem dados posteriores a 2026-09-02. Uma campanha v2
posterior registrou a reconciliação integral dos 32 campos e da ordem das
linhas, além dos 27 checksums do manifesto; veja a
[aceitação de 2000–2026](../dev-guide/cotahist-performance.md#aceitacao-integral-de-20002026).
Esses resultados são históricos. Uma nova campanha precisa reconferir os
hashes e reconciliar os dados antes de usar estes números como critério de
aceitação.

Formato e offsets oficiais: [layout de séries históricas da B3](https://www.b3.com.br/data/files/33/67/B9/50/D84057102C784E47AC094EA8/SeriesHistoricas_Layout.pdf).
