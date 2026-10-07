# Benchmarks de Performance

Este documento registra as linhas de base de extração e processamento para os
módulos da B3 e da CVM. Os números são evidência de um cenário de referência e
servem como métrica para regressão de performance, não uma promessa de tempo
fixo para qualquer hardware.

As otimizações COTAHIST de 06/10/2026, suas comparações e condições de uso estão
no [guia de performance e integridade](cotahist-performance.md).

## 1. Linha de Base em Escala Real — B3

### 1.1. Medição Histórica da Implementação v3 — 27 Anos (2026-09-16, Revisão `f1a2f47`)

**Ambiente:** Python 3.13.7 · Linux x86_64 (kernel 6.8) · 8 CPUs · 7,55 GB de
memória total. Sem chamadas de rede; apenas extração local dos ZIPs oficiais.

- **Dataset:** 27 arquivos ZIP oficiais (2000–2026), 666,00 MB comprimido.
- **Escopo de ativos:** categorias públicas suportadas na revisão v3; a seleção não incluía TPMERC `021`.
- **Erros:** 0 (todos os 27 arquivos processados com sucesso).
- **Saída Parquet consolidada:** 481,86 MB por modo (505.265.249 bytes).

| Modo   | Linhas gravadas | Tempo decorrido (API) | Tempo decorrido (ponta a ponta) |    Pico RSS |      Throughput |
| ------ | --------------: | --------------------: | ------------------------------: | ----------: | --------------: |
| `fast` |      22.303.577 |              649,99 s |                        650,50 s |  429,88 MiB | 34.313,8 reg/s  |
| `slow` |      22.303.577 |              749,45 s |                        750,10 s |  331,11 MiB | 29.759,9 reg/s  |

> **Observação:** O modo `slow` utilizou apenas 331,11 MiB (~0,32 GiB) de pico
> RSS (uma redução de ~23% de memória em relação ao modo `fast`), mantendo 100%
> de paridade de esquema e dados em todos os 22.303.577 registros dos 27 anos.
> A diferença de memória de apenas ~98 MiB entre `fast` e `slow` deve-se ao
> limite delimitado por worker (`python_record_limit` de 25.000 vs 10.000 linhas)
> e descarte em chunks (`ROW_GROUP_LIMIT = 200.000`), mantendo complexidade de
> memória $O(1)$ em relação ao período temporal. O ganho de tempo moderado do
> `fast` (~15%) reflete a hipótese plausível de contenção do GIL do CPython em
> `ThreadPoolExecutor` no loop intensivo em CPU de parsing posicional de strings
> Python e montagem de lotes, além da etapa sequencial de merge em disco
> (embora rotinas de descompressão zlib e escrita C++ do PyArrow liberem o GIL,
> a validação posicional e construção de linhas em Python retêm o lock). Em
> relação à linha de base histórica v2 (~4,4 GB), a arquitetura com streaming
> colunar PyArrow reduziu o pico de memória em mais de 90%.

> **Escopo da medição:** esses números são uma referência histórica anterior
> ao contrato COTAHIST schema v2. O corpus continha 22.305.860 cotações e a
> medição excluiu 2.283 registros TPMERC `021`; portanto, ela não mede o volume,
> schema ou custo do contrato atual e não deve ser comparada diretamente.

### 1.2. Linha de Base Histórica v2 — 25 Anos Completos (2026-09-02, Revisão `703d9ab`)

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

### 1.3. Linha de Base Histórica v1 — 17 Anos (2026-08-06, Revisão `7ee1843`)

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
uv run --locked --no-sync pytest tests/perf -m perf -k benchmark_

# Salvar baseline de performance
uv run --locked --no-sync pytest tests/perf -m perf -k benchmark_ --benchmark-save=baseline_v1

# Comparar com baseline anterior
uv run --locked --no-sync pytest tests/perf -m perf -k benchmark_ --benchmark-compare=baseline_v1
```

Os dois microbenchmarks de hot path usam pytest-benchmark. A pasta também tem
um teste de medição de memória, marcado como `perf` e `slow`; os comandos abaixo
selecionam somente os dois microbenchmarks:

```bash
# Listar os dois benchmarks sem executá-los
uv run --locked --no-sync pytest tests/perf -m perf -o addopts='' --collect-only -q -k benchmark_

# Executar os benchmarks de hot paths
uv run --locked --no-sync pytest tests/perf -m perf -o addopts='' -k benchmark_

# Salvar resultados para uma comparação posterior
uv run --locked --no-sync pytest tests/perf -m perf -o addopts='' \
  -k benchmark_ --benchmark-save=baseline_v1

# Comparar com o baseline salvo
uv run --locked --no-sync pytest tests/perf -m perf -o addopts='' \
  -k benchmark_ --benchmark-compare=baseline_v1
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
- Para atribuir um ganho à refatoração, congele duas versões distintas e registre
  os hashes dos módulos de produto e validação. Execuções com os mesmos módulos
  medem a variação da máquina. Compare versões com os mesmos dados, dependências,
  mercados, backend e limites efetivos de recursos, alternando a ordem em processos
  novos e preservando todas as amostras.
- O tempo da operação inclui preflight, workers, merge e leitura final completa;
  a auditoria independente posterior tem seu próprio tempo. Registre carga e
  atividade de swap, além do RSS agregado. Quando medir CPU, some pai e workers
  encerrados e informe essa métrica separadamente do tempo de parede.
- Tempos instrumentados por profiler localizam gargalos, mas não comprovam ganho
  de throughput. Um ganho de microbenchmark precisa de confirmação na operação
  completa; resultados de uma carga sintética não podem ser extrapolados para
  todos os anos oficiais.

______________________________________________________________________

## 5. Runner de ingestão em processo novo

`scripts/benchmark_ingestion.py` mede import raiz, CVM, texto CVM, B3 de 100k e
250k registros, o cenário multi-arquivo `b3_multi_4x25k` (por padrão, 4 arquivos
de 25k linhas), footprint de runtime e, quando disponível, o corpus anual B3.
Ele gera corpus determinístico em diretório temporário, repete cada cenário três
vezes por padrão, executa a operação em processo Python novo e amostra RSS a
cada 10 ms no processo filho. Suporta avaliação comparativa via
`--backend thread|process` e `--processing-mode fast|slow`. Antes de registrar uma
medição, valida contagem, ordem, schema, valores-limite e o artefato Parquet lógico.
No corpus anual, o digest de referência e a extração incluem todas as classes
de ativos suportadas pela API, usando os 27 ZIPs oficiais; cada repetição é
comparada com esse digest tipado. `--processing-mode` executa somente o modo
selecionado, sem iniciar automaticamente o outro. `--source-count` é exclusivo
do corpus sintético `b3_multi_4x25k` e reparte as linhas solicitadas pela
quantidade exata de fontes; o corpus anual usa sempre suas 27 fontes.
`--worker-limit` aplica um teto no processo novo da medição por
`GDF_B3_WORKER_LIMIT`; o JSON registra tanto o valor solicitado quanto o valor
efetivo depois da política de recursos e do fallback de backend.

A referência anual usa o decoder independente de COTAHIST e inclui os 32 campos,
com o hash textual do conteúdo descomprimido, ano da fonte, linha física e bytes
originais. O marcador `todos` também preserva cotações de mercados sem uma classe
mapeada. A preparação desse digest fica fora do tempo da extração.

```bash
# Medição pequena para verificar o protocolo JSON
uv run --locked --no-sync python scripts/benchmark_ingestion.py \
  --scenario import_root --scenario cvm --rows 10 --repeats 1

# Corpora sintéticos completos, três repetições e relatório persistido
uv run --locked --no-sync python scripts/benchmark_ingestion.py \
  --scenario cvm --scenario cvm_text --scenario b3_100k \
  --scenario b3_250k --scenario b3_multi_4x25k --repeats 3 --output benchmark.json

# Comparação explícita de backend e modo de processamento
uv run --locked --no-sync python scripts/benchmark_ingestion.py \
  --scenario b3_multi_4x25k --backend process --processing-mode fast --repeats 3

# Prova do fallback: duas fontes, mas somente um worker efetivo
uv run --locked --no-sync python scripts/benchmark_ingestion.py \
  --scenario b3_multi_4x25k --rows 100 --source-count 2 --worker-limit 1 \
  --backend process --processing-mode fast

# Executa apenas slow em todos os mercados; o corpus precisa dos 27 ZIPs
mkdir -p .benchmarks
uv run --locked --no-sync python scripts/benchmark_ingestion.py \
  --scenario b3_annual --cotahist-path /caminho/COTAHIST \
  --processing-mode slow --repeats 1 \
  --output .benchmarks/b3-annual-slow.json
```

Cada resultado JSON contém versão do schema, revisão, ambiente, checksum de
entrada, contagem, fingerprint de schema, equivalência lógica, digest lógico,
SHA-256 do artefato gerado (`artifact_sha256`), tempo da operação, fases de
operação/validação, modo de processamento, backend, contagens e limites de
fontes/workers solicitados e efetivos, RSS inicial/pico/final do processo pai
(`rss_peak_mib`, preservando
a comparação com a linha de base histórica v1),
pico de RSS agregado da árvore (`aggregate_rss_peak_mib`), contagem de processos
filhos observados, bytes de saída, `status` e `worktree_sha256`. RSS é memória
residente por processo, não heap. `aggregate_rss_peak_mib` é a soma de RSS do pai e
dos descendentes na mesma amostra; páginas compartilhadas podem ser contadas mais de
uma vez, portanto essa métrica não equivale à memória física única, à memória global
do host ou ao uso de memória de um cgroup. A equivalência compara todas as linhas
tipadas (incluindo nulos, ordem e tuplas decimais), não apenas valores de borda. O
filho confere o checksum antes da medição; uma fonte modificada falha em vez de
produzir uma comparação inválida. O status anual sem os 27 ZIPs requeridos é `skipped`
com a razão `external corpus unavailable`; não deve ser convertido em sucesso em
relatórios de release.

Quando `git_sha` termina em `-dirty`, `worktree_sha256` identifica o diff rastreado
e o conteúdo de arquivos não rastreados e não ignorados existentes no início da
medição. Os resultados em `.benchmarks/` são deliberadamente locais e ignorados;
para uma alegação revisável, guarde o JSON emitido em um artefato rastreado da revisão
e cite ambos os campos de proveniência.

Os gates de referência desta mudança são avaliados apenas em comparação
baseline/candidato na mesma máquina: import raiz ≤50 MiB e ≤0,50 s; CVM 269.181
linhas ≤60% do tempo e ≤70% do RSS de baseline; B3 250k ≤50% do tempo e ≤25%
do RSS; e footprint runtime fechado sem Polars ≤260 MiB. Estes são objetivos de
release, não limites universais de CI.

______________________________________________________________________

## 6. Otimizações CVM — Encoding, Inferência e HTTP

### 6.1. Varredura de encoding e inferência terminal

Em **2026-09-23**, os cenários `cvm` e `cvm_text` foram executados em três
processos novos por etapa, com o mesmo corpus determinístico. Ambiente: Python
3.13.9, Linux x86_64, kernel 6.8, 8 CPUs. A etapa `scan` troca a classificação
byte a byte por uma tradução C por bloco; `scan + inferência` também interrompe
a observação de colunas já promovidas definitivamente a string.

| Cenário | Etapa | Repetições | Tempo mediano | Pico RSS mediano |
| ------- | ----- | ---------: | ------------: | ---------------: |
| `cvm` | baseline | 3 | 4,092 s | 166,30 MiB |
| `cvm` | scan | 3 | 1,798 s | 165,99 MiB |
| `cvm` | scan + inferência | 3 | 1,593 s | 162,10 MiB |
| `cvm_text` | baseline | 3 | 2,705 s | 227,28 MiB |
| `cvm_text` | scan | 3 | 0,822 s | 227,13 MiB |
| `cvm_text` | scan + inferência | 3 | 0,762 s | 227,33 MiB |

A varredura reduziu o tempo mediano em 56,1% para `cvm` e 69,6% para
`cvm_text`. A inferência terminal reduziu mais 11,4% e 7,3%, respectivamente,
comparada à etapa `scan`. O pico de RSS final ficou 2,5% abaixo do baseline em
`cvm` e 0,02% acima em `cvm_text`.

As três etapas produziram as mesmas contagens, fingerprints de schema, digests
lógicos e SHA-256 físicos dos Parquets em todas as nove repetições de cada
cenário. Os hashes lógicos foram `1ef1f6d9cd9ade4fba4551796916241ff0966620846a219b1f87be78f0e186c9`
para `cvm` (269.181 linhas) e
`2f3649d866f98263ce2156bdb688733da3ae31b0fbc7c963c720675c6ae49d0b` para
`cvm_text` (8.000 linhas).

Os relatórios completos, incluindo checksums de entrada, cada repetição e
proveniência `git_sha` / `worktree_sha256`, estão nos arquivos [baseline](benchmark-results/cvm-optimizations-20260923/cvm-opt-baseline-20260923.json), [scan](benchmark-results/cvm-optimizations-20260923/cvm-opt-scan-20260923.json) e [scan + inferência](benchmark-results/cvm-optimizations-20260923/cvm-opt-inference-20260923.json).
Reproduza os três cenários com:

```bash
mkdir -p .benchmarks
uv run --locked --no-sync python scripts/benchmark_ingestion.py \
  --scenario cvm --scenario cvm_text --repeats 3 \
  --output .benchmarks/cvm-optimizations.json
```

### 6.2. Medição por fase de downloads CVM

`scripts/benchmark_cvm_http.py` mede separadamente tempo e bytes de GET, HEAD,
validação do ZIP e extração Parquet. O modo local serve o mesmo ZIP determinístico
em HTTP/1.1, executa lotes de três downloads por padrão e compara chunks de 8,
64 e 256 KiB. Os bytes de GET são os transferidos; HEAD transfere zero bytes e
registra o `Content-Length`; validação registra o tamanho do ZIP lido; extração
registra os bytes CSV descompactados. O relatório também conta as construções
de `httpx.AsyncClient` e mede o custo síncrono dessas construções.

```bash
mkdir -p .benchmarks
uv run --locked --no-sync python scripts/benchmark_cvm_http.py \
  --source local --repeats 3 --batch-size 3 --payload-mib 4 \
  --output .benchmarks/cvm-http-local.json
```

Para poucas fontes oficiais equivalentes, use URLs explícitas:

```bash
mkdir -p .benchmarks
uv run --locked --no-sync python scripts/benchmark_cvm_http.py \
  --source official \
  --official-url https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_2022.zip \
  --official-url https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_2023.zip \
  --official-url https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_2024.zip \
  --repeats 3 --output .benchmarks/cvm-http-official.json
```

Em **2026-09-23**, a execução local terminou com `passed`: nove lotes, três
repetições por chunk e três downloads por lote. As medianas abaixo usam o tempo
total do lote; os tempos de fase somam as operações concorrentes do lote.

| Chunk | Lote total | HEAD | GET | Validação | Extração | Inicialização de clientes HTTPX |
| ----: | ---------: | ---: | --: | --------: | -------: | ------------------------------: |
| 8 KiB | 0,246 s | 0,049 s | 0,201 s | 0,013 s | 0,136 s | 6 clientes; 0,0369 s |
| 64 KiB | 0,241 s | 0,046 s | 0,151 s | 0,014 s | 0,133 s | 6 clientes; 0,0371 s |
| 256 KiB | 0,236 s | 0,047 s | 0,157 s | 0,013 s | 0,128 s | 6 clientes; 0,0371 s |

Cada lote transferiu 12.590.178 bytes em três GETs. HEAD anunciou o mesmo
tamanho; a validação leu os mesmos bytes; a extração processou 6.612 bytes CSV.
As nove execuções produziram três Parquets e 768 linhas, com fingerprints de
schema e SHA-256 dos artefatos idênticos. O melhor tempo mediano total ficou
4,2% abaixo do chunk de 8 KiB, com variação entre repetições e diferença pequena
entre chunks de 64 e 256 KiB. Os seis construtores `httpx.AsyncClient` somaram
cerca de 37 ms por lote, 18% do tempo acumulado de GET e HEAD. Como o benchmark
local sintético não compara clientes compartilhados e a diferença de tempo total
é pequena, mantenho o chunk atual de 8 KiB e o ciclo atual dos clientes HTTPX.

O relatório completo, com cada repetição, checksum da fixture e proveniência
`git_sha` / `worktree_sha256`, está em
[cvm-http-local-20260923.json](benchmark-results/cvm-http-local-20260923.json).
O primeiro intento local dentro do sandbox falhou ao abrir o servidor de fixture
em `127.0.0.1` (`PermissionError: Operation not permitted`); a execução local
posterior passou. A medição oficial foi `skipped`: a consulta DNS por
`dados.cvm.gov.br` continua sem resolução neste ambiente.

### 6.3. Benchmark completo com fonte CVM real

`scripts/benchmark_cvm_full.py` executa manualmente downloads e extração CVM
de 2010 a 2026, mede tempo e pico RSS do processo e resume os Parquets gerados.
Ele acessa a CVM e produz arquivos grandes; não faz parte dos testes
determinísticos nem da CI. Forneça um diretório existente e vazio:

```bash
mkdir -p .benchmarks/cvm-full
uv run --locked --no-sync python -m scripts.benchmark_cvm_full \
  --output-dir .benchmarks/cvm-full
```
