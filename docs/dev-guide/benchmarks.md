# Benchmarks de Performance

Este documento registra as linhas de base de extração e processamento para os
módulos da B3 e da CVM. Os números são evidência de um cenário de referência e
servem como métrica para regressão de performance, não uma promessa de tempo
fixo para qualquer hardware.

## 1. Linha de Base em Escala Real — B3

### 1.1. Linha de Base v2 — 25 Anos Completos (2026-09-02, Revisão `703d9ab`)

**Ambiente:** Python 3.13.7 · Linux x86_64 (kernel 6.8) · 8 CPUs · 7,55 GB de
memória total. Sem chamadas de rede; apenas extração local dos ZIPs oficiais.

- **Dataset:** 25 arquivos ZIP oficiais (2000–2024), 503,77 MB comprimido.
- **Escopo de ativos:** todas as categorias atualmente suportadas (`ações`, `etf`, `opções`, `termo`, `exercicio_opcoes`, `forward`, `leilao`).
- **Erros:** 0 (todos os 25 arquivos processados com sucesso).
- **Saída Parquet consolidada:** 344,71 MB por modo.

| Modo   | Linhas gravadas | Tempo decorrido (API) | Tempo decorrido (ponta a ponta) |    Pico RSS |   Throughput |
| ------ | --------------: | --------------------: | ------------------------------: | ----------: | -----------: |
| `fast` |      16.460.458 |   1.557,73 s |          1.557,28 s | 4.433,19 MB | 10.566,9 reg/s |
| `slow` |      16.460.458 |   2.143,77 s |          2.143,93 s | 1.545,97 MB |  7.678,3 reg/s |

> **Observação:** O modo `slow` utilizou apenas 1.545,97 MB (~1,51 GiB) de pico
> RSS (uma redução de ~65% de memória em relação ao modo `fast`), mantendo 100%
> de paridade de esquema e dados em todos os 16.460.458 registros dos 25 anos.

### 1.2. Linha de Base Histórica v1 — 17 Anos (2026-08-06, Revisão `7ee1843`)

**Ambiente:** Python 3.13.7 · Linux x86_64 (kernel 6.8) · 8 CPUs · 7,55 GB de
memória total. Sem chamadas de rede; apenas extração local dos ZIPs oficiais.

- **Dataset:** 17 arquivos ZIP oficiais (2008–2024), 445,85 MB comprimido.
- **Escopo de ativos:** todas as categorias atualmente suportadas (`ações`, `etf`, `opções`, `termo`, `exercicio_opcoes`, `forward`, `leilao`).
- **Erros:** 0 (todos os 17 arquivos processados com sucesso).
- **Saída Parquet consolidada:** 311,55 MB por modo.

| Modo   | Linhas gravadas | Tempo decorrido (API) | Tempo decorrido (ponta a ponta) |    Pico RSS |   Throughput |
| ------ | --------------: | --------------------: | ------------------------------: | ----------: | -----------: |
| `fast` |      15.059.876 |   1.222,61 s |          1.224,64 s | 4.259,35 MB | 12.317 reg/s |
| `slow` |      15.059.876 |   1.759,90 s |          1.761,91 s | 1.570,54 MB |  8.557 reg/s |

> **Gargalo identificado:** Parser e merge Parquet da B3; o modo `fast` consome
> ~4,2 GiB de pico RSS. O modo `slow` usa menos de 1,6 GiB com throughput ~28%
> menor.

______________________________________________________________________

## 2. Linha de Base Sintética Reproduzível — B3

Para CI/CD e regressões rápidas, mantemos um dataset sintético menor. Medição
realizada em **2026-08-06**, revisão `7ee1843`, com três execuções independentes
por modo:

| Modo   | Registros | Entrada ZIP | Saída Parquet | Tempo da API (mediana) | Tempo ponta a ponta (mediana) |    Pico RSS | Registros/s (mediana) |
| ------ | --------: | ----------: | ------------: | ---------------------: | ----------------------------: | ----------: | --------------------: |
| `fast` |   250.000 |     8,46 MB |       4,05 MB |                11,15 s |                       12,27 s | 1.111,72 MB |                22.427 |
| `slow` |   250.000 |     8,46 MB |       4,05 MB |                18,05 s |                       19,04 s | 1.103,01 MB |                13.847 |

O cenário processou um arquivo sintético COTAHIST de 61,5 MB descompactado, com
250.000 registros filtrados para `ações`. Todas as execuções terminaram sem
erros. O pico RSS inclui interpretador, dependências, parser e escritor Parquet.

> **Observação:** Em datasets sintéticos pequenos, `fast` e `slow` apresentam
> picos RSS próximos (~1,1 GB). A diferença significativa de memória (~4,2 GB
> vs ~1,6 GB) só fica evidente em escala real, conforme métricas da Seção 1.

### 2.1. Candidato Arrow v3 — 250 Mil Registros (2026-09-12 UTC, Revisão `703d9ab`)

Esta medição usa o runner de ingestão Arrow introduzido neste cutover. Ela não
substitui a linha de base histórica v1: o gerador de corpus, o schema explícito
e a separação entre tempo operacional e validação são parte de um protocolo mais
rigoroso. Serve como evidência reproduzível do candidato e como ponto de partida
para comparações futuras feitas sob o mesmo protocolo.

**Ambiente:** Python 3.13.7 · Linux x86_64 (kernel 6.8) · 8 CPUs. Três processos
Python novos processaram o corpus sintético determinístico, sem chamadas de
rede.

| Cenário | Repetições | Linhas | Tempo operacional (mediana) | Pico RSS (mediana) | Saída Parquet | Equivalência lógica |
| ------- | ---------: | -----: | --------------------------: | -----------------: | -------------: | ------------------: |
| B3 250k |          3 | 250.000 |                     5,832 s |         215,898 MiB |    5.822.005 B |                 3/3 |

- O SHA-256 da entrada é
  `329f30c6d160401071ab321ebe796e8d91be5a2e0bf502fc68b1cc1c66c30d39`.
- Cada repetição validou contagem, ordem, schema, nulos, valores tipados e
  precisão decimal; todas produziram o mesmo digest lógico.
- A validação pós-escrita é registrada separadamente do tempo operacional; ela
  não é misturada à métrica de throughput da tabela.
- O JSON bruto local está em
  `.benchmarks/pyarrow-ingestion-integrity-cutover-b3-250k-20260912.json`.
  Esse diretório é ignorado intencionalmente pelo Git porque contém evidência
  dependente de máquina.

### Como reproduzir

```bash
# Micro-benchmarks de hot paths no repositório (CVM URL gen e B3 parser)
uv run --locked --no-sync pytest tests/perf -m perf

# Salvar baseline de performance
uv run --locked --no-sync pytest tests/perf -m perf --benchmark-save=baseline_v1

# Comparar com baseline anterior
uv run --locked --no-sync pytest tests/perf -m perf --benchmark-compare=baseline_v1
```

Os benchmarks disponíveis no repositório são executados pelo pytest-benchmark:

```bash
# Listar os dois benchmarks sem executá-los
uv run --locked --no-sync pytest tests/perf -m perf -o addopts='' --collect-only -q

# Executar os benchmarks de hot paths
uv run --locked --no-sync pytest tests/perf -m perf -o addopts=''

# Salvar resultados para uma comparação posterior
uv run --locked --no-sync pytest tests/perf -m perf -o addopts='' \
  --benchmark-save=baseline_v1

# Comparar com o baseline salvo
uv run --locked --no-sync pytest tests/perf -m perf -o addopts='' \
  --benchmark-compare=baseline_v1
```

O arquivo sintético da linha de base tem SHA-256
`4ba04707468088975125a536b07f5a9cd361676e8ac68866554241ceb58b7e86`.

______________________________________________________________________

## 3. Linha de Base CVM — Download + Extração

### 3.1. Linha de Base v2 — 17 Anos (2010–2026, Revisão `703d9ab`)

Medição do fluxo completo de `FundamentalStocksDataCVM` com
`automatic_extractor=True`: download dos ZIPs brutos da CVM, extração CSV com
tratamento robusto de aspas em texto livre (`QUOTE_NONE`) e geração dos Parquets
primários com commit atômico. Executado na mesma máquina dos benchmarks B3.

- **Docs:** DFP, ITR, FRE, FCA, CGVN, VLMO, IPE (todos os 7 tipos disponíveis)
- **Período:** 2010–2026 (17 anos)

| ZIPs baixados | Parquets gerados | Linhas extraídas | Saída total | Tempo decorrido |  Pico RSS | Erros |
| ------------: | ---------------: | ---------------: | ----------: | ---------------: | --------: | ----: |
|           102 |            1.569 |       70.821.466 |   382,27 MB |    906,85 s | 333,91 MB |     0 |

- Inclui: conexão com servidores CVM, download de todos os 102 ZIPs disponíveis,
  validação, extração CSV e conversão para Parquet.
- O pico de memória RSS reduziu para 333,91 MB (~27% menor que a v1), mesmo com
  o processamento de 70,82 milhões de linhas e 1.569 arquivos Parquet.

### 3.2. Linha de Base Histórica v1 — 15 Anos (2010–2024, Revisão `7ee1843`)

Medição do fluxo completo de `FundamentalStocksDataCVM` com
`automatic_extractor=True`: download dos ZIPs brutos da CVM, extração CSV e
geração dos Parquets primários. Executado na mesma máquina dos benchmarks B3.

- **Docs:** DFP, ITR, FRE, FCA, CGVN, VLMO, IPE (todos os tipos disponíveis)
- **Período:** 2010–2024

| ZIPs baixados | Parquets gerados | Linhas extraídas | Saída total | Tempo decorrido |  Pico RSS | Erros |
| ------------: | ---------------: | ---------------: | ----------: | ---------------: | --------: | ----: |
|            88 |            1.392 |       63.300.208 |   337,93 MB |    505,04 s | 459,18 MB |     0 |

- Inclui: conexão com servidores CVM, download de todos os ZIPs, validação,
  extração CSV e conversão para Parquet.
- O tempo de rede varia com condições externas; o tempo de extração
  CSV→Parquet é a parcela estável e reprodutível da medida.

______________________________________________________________________

## 4. Limitações e Contratos

- O fixture sintético B3 valida o caminho completo de parsing, filtragem e
  escrita Parquet, mas não representa a cardinalidade, compressão ou distribuição
  de ativos de um ano real da B3.
- Ao atualizar os números reprodutíveis, preserve: dataset, checksum, hardware,
  versão do Python, revisão do código, número de repetições e definição de cada
  métrica.

______________________________________________________________________

## 5. Runner de ingestão em processo novo

`scripts/benchmark_ingestion.py` mede import raiz, CVM, texto CVM, B3 de 100k e
250k registros, footprint de runtime e, quando disponível, o corpus anual B3.
Ele gera corpus determinístico em diretório temporário, repete cada cenário três
vezes por padrão, executa a operação em processo Python novo e amostra RSS a
cada 10 ms no processo filho. Antes de registrar uma medição, valida contagem,
ordem, schema, valores-limite e o artefato Parquet lógico.

```bash
# Medição pequena para verificar o protocolo JSON
uv run --locked --no-sync python scripts/benchmark_ingestion.py \
  --scenario import_root --scenario cvm --rows 10 --repeats 1

# Corpora sintéticos completos, três repetições e relatório persistido
uv run --locked --no-sync python scripts/benchmark_ingestion.py \
  --scenario cvm --scenario cvm_text --scenario b3_100k \
  --scenario b3_250k --repeats 3 --output benchmark.json

# O corpus anual só executa com os 17 ZIPs; caso contrário, fica skipped
uv run --locked --no-sync python scripts/benchmark_ingestion.py \
  --scenario b3_annual --cotahist-path /caminho/COTAHIST --output annual.json
```

Cada resultado JSON contém versão do schema, revisão, ambiente, checksum de
entrada, contagem, fingerprint de schema, equivalência lógica, digest lógico,
tempo da operação, fases de operação/validação, RSS inicial/pico/final, bytes
de saída e `status`. A equivalência compara todas as linhas tipadas (incluindo
nulos, ordem e tuplas decimais), não apenas valores de borda. O filho confere o
checksum antes da medição; uma fonte modificada falha em vez de produzir uma
comparação inválida. O status anual sem os 17 ZIPs requeridos é `skipped` com a
razão `external corpus unavailable`; não deve ser convertido em sucesso em
relatórios de release.

Os gates de referência desta mudança são avaliados apenas em comparação
baseline/candidato na mesma máquina: import raiz ≤50 MiB e ≤0,50 s; CVM 269.181
linhas ≤60% do tempo e ≤70% do RSS de baseline; B3 250k ≤50% do tempo e ≤25%
do RSS; e footprint runtime fechado sem Polars ≤260 MiB. Estes são objetivos de
release, não limites universais de CI.
