# Performance e integridade de COTAHIST

## Contrato das otimizações

As otimizações de 06/10/2026 preservam as assinaturas públicas, o schema v2,
os nomes de saída e a seleção de mercados. Os 32 campos, os decimais exatos,
os bytes originais, a proveniência, a ordem e as ocorrências repetidas continuam
conferidos antes da publicação. CRC, identidade das fontes, replay e leitura
final completa permanecem obrigatórios.

A implementação atual valida coordenadas na releitura com reduções Arrow em
segmentos contíguos de fonte. Nulos obrigatórios são rejeitados antes das
comparações; segmentos inválidos usam diagnósticos escalares para preservar o
primeiro erro. O preflight mantém o container validado aberto durante o hash
em blocos de 64 KiB e a varredura estrita. O worker valida um novo container e
calcula o digest dos lotes Arrow convertidos contra a expectativa canônica
independente do preflight. O framing binário lê os buffers Arrow com seus
offsets; o schema v2 e o framing do digest permanecem iguais.

## Encerramento da refatoração: 20/10/2026

A refatoração foi encerrada e aceita pelo responsável pelo projeto em
20/10/2026. Por decisão explícita, a meta mínima de ganho de 20% foi retirada
dos requisitos de aceitação. Os ganhos reais demonstrados na comparação
controlada de 19/10 foram aceitos como suficientes para o encerramento, junto
às correções revisadas e às verificações de integridade dos dados e contratos.
Não há percentual mínimo de desempenho pendente para esta entrega.

Os percentuais medidos continuam vinculados ao snapshot de 19/10. A campanha
complementar da versão final confirmou a integridade dos dados, mas seu
resultado temporal permanece inconclusivo e não estabelece um novo percentual
confiável. Os aumentos de CPU e RSS continuam documentados como custos dos
ganhos observados.

Os relatórios e as amostras originais permanecem preservados, inclusive os
registros da meta não atingida quando ela ainda era exigida. Esta decisão
substitui aquele requisito para o encerramento da refatoração.

## Política atual de execução

`HistoricalQuotesB3()` usa `process` por padrão. A extração `fast` elegível usa
processos iniciados por `spawn`, com pelo menos duas fontes resolvidas e dois
workers permitidos pela política de recursos. `slow`, uma fonte ou limite de um
worker usam um worker de thread. Daemons e chamadas sem módulo principal
importável ou script legível recebem fallback antes da submissão; o logger
registra o motivo e a telemetria informa o backend efetivo. Falhas do pool e dos
workers preservam os diagnósticos e a limpeza normal. Scripts devem proteger a
extração com `if __name__ == '__main__':`. As escolhas explícitas
`GDF_B3_EXECUTOR_BACKEND=thread` e `process` continuam aceitas.

O parser produz uma tupla canônica diretamente e aplica um plano derivado do
layout, reutilizando os validadores escalares existentes. O digest usa tabelas
constantes de tags e comprimentos. A leitura final monta o mesmo framing v2
com Arrow em segmentos limitados pelas fontes. Essas tabelas não armazenam
valores financeiros. Veja o [contrato do digest](../reference/b3-schema-v2.md).

## Ajustes após revisão: 20/10/2026

O preflight valida o caminho e captura o hash externo antes de abrir o handle
usado no hash de conteúdo e no scan. A conferência final do caminho permanece.
Assim, uma substituição por renomeação nessa janela é rejeitada no próprio
preflight, sem produzir um descritor que misture dois arquivos. As regressões
cobrem TXT e ZIP, antes e depois da abertura, no validador e na fachada, incluindo
o fechamento dos handles e a ausência de publicação.

Também foram removidos a configuração antiga `_ProcessingModeConfig`, as quatro
propriedades de recursos sem consumidores de produção em `ProcessingModeEnumB3`
e o helper sem chamadas `validate_one_temp_file()`. A política efetiva continua
em `ResourcePolicyB3`; a remoção das propriedades exportadas foi autorizada.

A comparação completa de 72 observações abaixo pertence ao snapshot de 19/10,
anterior a essa correção, e não foi repetida. Seus ganhos históricos e aumentos
de RSS e CPU permanecem vinculados àquela versão. A decisão de encerramento
acima aceita essa evidência sem exigir um percentual mínimo de ganho.

Uma campanha complementar da versão final em 20/10 executou 18 extrações completas
de um ZIP com 100.000 cotações: três pares alternados para cada configuração
`slow/thread`, `fast/thread` e `fast/process`. Foram conferidos os snapshots do
produto, as dependências e os bytes de entrada; os 32 campos e os metadados do
schema coincidiram, e duas reconciliações independentes verificaram 100.000
linhas cada. O resultado temporal foi inconclusivo: execuções da mesma versão
em `fast/process` variaram de 12,44 a 18,77 s no baseline e de 10,35 a 15,13 s no
candidato. As reduções dos três pares foram 16,75%, 44,66% e 17,14%. A variação
do host impede usar as medianas nominais como nova evidência de aceitação. O
[relatório complementar](benchmark-results/cotahist-processing-final-20261020/comparison.json)
preserva todas as amostras, CPU/RSS, proveniência, audits independentes e
limitações. A última comparação controlada aceita dos padrões permanece em 15,41%.

O profiling separado localizou os maiores custos do preflight na conversão
escalar dos campos canônicos e no digest escalar independente. Um pequeno
experimento de framing não demonstrou benefício e foi descartado; essa campanha
complementar não alterou o código do produto.

## Comparação da API completa: 19/10/2026

Três pares por configuração rodaram sequencialmente em processos Python novos,
em ordem alternada, totalizando 72 observações aceitas. Ambiente: Python 3.13.9,
PyArrow 23.0.1, Linux x86_64, oito CPUs lógicas e 7,55 GiB de RAM. As versões
usaram dependências travadas, bytes de entrada, seleção completa de mercados e
quatro workers solicitados iguais. Uma fonte e `slow` usaram um worker de thread.
Os quatro TXT ultrapassam o limiar de 64 MiB do preflight; os ZIP não.

O tempo inclui construção, preflight, replay nos workers, leitura integral do
Parquet e publicação transacional. A reconciliação independente tem seu próprio
cronômetro. Os 32 campos, ocorrências, ordem e metadados completos do schema
coincidiram entre versões e modos. Oito audits independentes verificaram
2.400.000 linhas no total.

| Fontes / cotações | Entrada | Modo / backend solicitado | API inicial (s) | API candidata (s) | Redução |
| ----------------- | ------- | ------------------------- | --------------: | ----------------: | ------: |
| 1 / 100,000       | TXT     | `slow/thread`             |           9.019 |             7.812 |  13.39% |
| 1 / 100,000       | TXT     | `fast/thread`             |           9.435 |             7.981 |  15.41% |
| 1 / 100,000       | TXT     | `fast/process`            |           9.496 |             8.057 |  15.15% |
| 1 / 100,000       | ZIP     | `slow/thread`             |           9.733 |             8.099 |  16.79% |
| 1 / 100,000       | ZIP     | `fast/thread`             |           9.604 |             8.133 |  15.32% |
| 1 / 100,000       | ZIP     | `fast/process`            |           9.563 |             8.124 |  15.04% |
| 4 / 500,000       | TXT     | `slow/thread`             |          46.889 |            39.480 |  15.80% |
| 4 / 500,000       | TXT     | `fast/thread`             |          46.113 |            37.736 |  18.17% |
| 4 / 500,000       | TXT     | `fast/process`            |          25.171 |            20.518 |  18.49% |
| 4 / 500,000       | ZIP     | `slow/thread`             |          48.029 |            40.048 |  16.62% |
| 4 / 500,000       | ZIP     | `fast/thread`             |          51.285 |            42.172 |  17.77% |
| 4 / 500,000       | ZIP     | `fast/process`            |          35.419 |            29.426 |  16.92% |

A troca do padrão anterior (`fast/thread`) para o novo padrão elegível
(`fast/process`) reduziu a mediana em **55,51% no TXT** (46,113 para 20,518 s)
e **42,62% no ZIP** (51,285 para 29,426 s), com quatro fontes. A comparação de
padrões com uma fonte ZIP melhorou **15,41%**. Nenhum par de modo/backend teve
regressão de tempo nessa campanha.

A memória aumentou nos perfis fast com várias fontes: **24,31% em threads/TXT**,
**37,29% em threads/ZIP** e **24,16% em processos**, nos dois formatos. A
instrumentação separada observou até quatro digests concorrentes, lotes limitados
a 25.000 linhas e pico de alocação Arrow por worker de 64,0 para 106,5 MiB.
Após cada fonte, restavam 17.536 bytes Arrow para tabelas constantes de prefixos;
o RSS também inclui reservas do alocador. A evidência localiza os buffers
adicionais de framing e preserva os limites existentes de buffering.

A troca de backend, isolada no candidato, acrescenta **46,78% de RSS agregado no
TXT** e **47,16% no ZIP**. Somando código e backend, a mediana passa de 676,12
para 1.233,73 MiB no TXT e de 613,48 para 1.239,46 MiB no ZIP. A CPU total da API
passa de 50,06 para 72,18 s e de 53,71 para 60,09 s, respectivamente. O menor tempo
tem custo de CPU e memória. A soma de RSS pode contar páginas compartilhadas
mais de uma vez. A amostragem cobre a API e a comparação limitada posterior do
runner nativo; os audits de dados brutos permanecem separados.

O ZIP de 2023 fornecido pelo chamador passou separadamente nos dois modos:
**2.257.424 cotações por modo**, reconciliação independente dos 32 campos,
paridade exata de ordem e nenhum worker restante. Seu SHA-256 é
`ad1603788d78aaa1de806498572277f1d9443f88ae116452751b5800cb23523e`.
A campanha coincidiu com gates de qualidade e constitui evidência de integridade.

| Carga sintética | SHA-256 combinado das entradas                                     |
| --------------- | ------------------------------------------------------------------ |
| 1-100000-txt    | `253a8e7e8448b25b8293cef8d130a3821a161682ca15dc17ffe1e9e6ab0c0646` |
| 1-100000-zip    | `410e7200bbb04bb7b4af8a75164d34dd8153ed7203ccf3247f46dea37697d9e0` |
| 4-500000-txt    | `3847bb6d8f4bac24449f623c1255acbd80625b4f8b98f0a3dcd111639321ab1d` |
| 4-500000-zip    | `b618ff2947498c82d022c7fb2ffe0c0d9016f60bbaafef885f36cd80f4ddd366` |

A [comparação e métricas por fase](benchmark-results/cotahist-processing-20261019/comparison.json)
referencia cada amostra bruta. A [proveniência](benchmark-results/cotahist-processing-20261019/provenance.json)
vincula hashes de produto e suporte, dependências e entradas individuais.
A [investigação de memória](benchmark-results/cotahist-processing-20261019/memory-investigation.json),
os [audits independentes](benchmark-results/cotahist-processing-20261019/independent-audits.json),
a [reconciliação anual](benchmark-results/cotahist-processing-20261019/annual-2023.json)
e o [smoke com backend não definido](benchmark-results/cotahist-processing-20261019/default-smoke.json)
ficam separados. O [relatório de validação](benchmark-results/cotahist-processing-20261019/validation.json)
registra os gates e os critérios vigentes na data da campanha; o encerramento
acima retira o requisito percentual. A instrumentação de um ZIP passou de 4 para 2 varreduras
completas de CRC e de 7 para 5 descompressões; os contextos no hash passaram de
4 para 0 em um fixture de duas cotações, com todos os arquivos fechados.

O corpus sintético tem um pregão por ano, mercado 010 e fontes equilibradas.
Três observações por versão/configuração e caches de arquivo do SO aquecidos
limitam a precisão e a extrapolação. Os números descrevem as cargas medidas e
não garantem throughput em outra máquina ou no corpus anual completo.

```bash
uv run --locked --no-sync python scripts/benchmark_ingestion.py \
  --scenario b3_multi_4x25k --rows 500000 --source-count 4 --worker-limit 4 \
  --b3-input-format zip --backend process --processing-mode fast --repeats 3 \
  --output .benchmarks/b3-processing-zip.json
```

O CLI nativo usa TXT por padrão e seleciona ações; a comparação controlada usou
`todos` pelo ponto de extensão da operação. O coordenador arquivado preserva
essa seleção e alterna snapshots distintos. As seções de 06/10/2026 abaixo são
medições históricas de versões e campanhas anteriores.

## Parser e leitura final: comparação de versões distintas

Três pares por modo processaram os mesmos 500.000 registros em quatro fontes,
em processos Python novos e ordem alternada. Ambiente: Python 3.13.9, PyArrow
23.0.1, Linux x86_64, oito CPUs, com os outros processos da máquina em execução.
O backend solicitado foi `thread`; `slow` manteve um worker.

| Modo   | Mediana inicial | Mediana otimizada | Redução de tempo | Redução de CPU |
| ------ | --------------: | ----------------: | ---------------: | -------------: |
| `fast` |        84,148 s |          57,901 s |           31,19% |         29,57% |
| `slow` |        66,477 s |          47,089 s |           29,16% |         28,63% |

O tempo inclui preflight, workers, merge e leitura final completa. A auditoria
independente posterior fica fora desse timer. Todos os pares produziram
Parquets idênticos byte a byte. A expectativa sintética cobre os campos de
negócio; a leitura interna dos 32 campos e a igualdade física também cobrem a
proveniência. A reconciliação oficial é uma prova adicional separada.

O RSS agregado mediano de `fast` ficou praticamente estável: 640,86 para
642,42 MiB. Em `slow`, caiu de 492,79 para 407,54 MiB. Os tempos de leitura
final foram de 21,576 para 6,819 s em `fast` e de 16,486 para 5,260 s em `slow`.

O [relatório bruto](benchmark-results/cotahist-optimization-20261006/parser-arrow-500k.json)
preserva todas as amostras, carga, swap, checksums e hashes dos módulos.
Os números descrevem essa carga e essa máquina; não são uma garantia de
throughput nem uma projeção para os 27 anos oficiais.

## Versão final integrada: nova comparação

A integração final repetiu os três pares por modo, com a mesma configuração
`thread`, quatro fontes e 500.000 registros. Os outros aplicativos e a suíte
optativa de dados reais estavam ativos. As versões tiveram o mesmo número
efetivo de fontes e workers em todos os pares.

| Modo   | Mediana inicial | Mediana integrada | Redução de tempo | Redução de CPU |
| ------ | --------------: | ----------------: | ---------------: | -------------: |
| `fast` |        96,363 s |          63,489 s |           34,11% |         29,34% |
| `slow` |        76,374 s |          50,380 s |           34,04% |         33,85% |

Os seis pares melhoraram tempo e CPU, e os 12 processos produziram os mesmos
Parquets dentro de cada par. O RSS agregado mediano foi de 679,44 para
665,44 MiB em `fast` e de 453,68 para 405,96 MiB em `slow`.

O [relatório da versão integrada](benchmark-results/cotahist-optimization-20261006/final-integrated-500k.json)
preserva todas as amostras e os hashes das versões. A variação da máquina
limita a precisão do ganho observado; esta medição também não representa
uma garantia para o corpus anual completo.

## Aceitação integral de 2000–2026

A [aceitação final](benchmark-results/cotahist-optimization-20261006/final-acceptance.json)
processou as 27 fontes anuais fornecidas, de 03/01/2000 a 02/09/2026, com o
backend padrão `thread` e quatro workers solicitados. Cada modo leu, selecionou,
escreveu e verificou 22.305.860 cotações, sem exclusões ou anos ausentes.
A reconciliação independente conferiu os 32 campos e a ordem de todas as linhas.
Os Parquets físicos coincidiram entre os modos e com a aceitação histórica.

Também passaram os 27 checksums do manifesto congelado, a preservação dos
20 campos anteriores em 22.303.577 cotações e as 2.283 negociações em bloco,
com 345 códigos distintos e volume decimal total exato de 57.359.085.637,97.
A limpeza terminou sem processos ativos ou temporários residuais.

| Modo   | API na campanha anterior |  API na campanha atual | Redução observada |
| ------ | -----------------------: | ---------------------: | ----------------: |
| `fast` |   3.895,088 s (64min55s) | 2.989,776 s (49min50s) |            23,24% |
| `slow` |   3.350,505 s (55min51s) | 2.297,342 s (38min17s) |            31,43% |

Cada campanha executou uma extração completa por modo. A máquina manteve seus
outros processos em execução, mas as campanhas ocorreram em dias e cargas
diferentes. Esses percentuais são observações históricas, não uma estimativa
causal controlada ou mediana do corpus completo. A comparação repetida de
500.000 registros tem metodologia e números próprios, descritos acima.

Os tempos da API incluem preparação, extração, merge e leitura integral antes
da publicação. A campanha atual inteira levou 12.861,443 s, aproximadamente
3h34min, incluindo as auditorias externas, a paridade e a limpeza. Esse total
mede a aceitação completa e não substitui o timer de processamento da API.

O relatório explicita o vínculo com o código: a campanha integral preservou
uma cópia de 323 arquivos; uma correção posterior afeta somente a espera do
preflight por processos, e outra alteração sincroniza um teste de cancelamento.
Os outros 321 arquivos e o restante da AST desse módulo permaneceram iguais.
`thread` e `slow` não chamam a função de espera corrigida. A correção por
processos passou novamente na aceitação oficial de 2002–2003, sobre uma cópia
que coincide com todos os 112 módulos atuais de produto. Os gates locais
cobriram o código e os testes atuais nos três Python suportados.

## Preflight concorrente

Na campanha de 06/10/2026, `thread` era o padrão. Com o padrão atual `process`
ou sua escolha explícita, o modo `fast` admite preflight concorrente somente
em contexto compatível com `spawn`, quando há pelo
menos dois workers permitidos pela política de recursos e a soma dos tamanhos
armazenados dos candidatos anuais é de pelo menos 64 MiB. A soma inclui ZIP e
TXT coexistentes, pois ambos precisam de validação. `slow`, uma fonte, um
worker ou uma carga menor preservam preflight serial.

O limiar é conservador e considera bytes armazenados, não quantidade de
cotações ou tamanho descomprimido. Compressão, distribuição por fonte, CPUs e
memória afetam o resultado. Falhas de leitura do tamanho são encaminhadas à
validação serial canônica, que preserva a ordem dos diagnósticos.

Em três pares adicionais, ambos os lados usaram extração por processos com
500.000 registros e quatro fontes. O preflight concorrente reduziu a mediana
de 34,294 para 25,514 s: 25,60% menos tempo. A CPU total mediana aumentou de
67,295 para 81,940 s. Esse é um custo adicional de CPU para reduzir tempo de
parede; não representa menor trabalho computacional.

O [relatório do preflight](benchmark-results/cotahist-optimization-20261006/preflight-process-500k.json)
registra todas as amostras, RSS agregado, CPU e versões comparadas. Os três
pares produziram o mesmo Parquet. A implementação preserva a ordem das
fontes e do primeiro erro, as causas tipadas e o encerramento dos workers
antes de concluir cancelamento ou falha.
O polling recupera resultados que terminam na fronteira do tempo de espera e
preserva um `TimeoutError` produzido pelo próprio worker.

Uma [aceitação oficial adicional](benchmark-results/cotahist-optimization-20261006/official-process-2002-2003.json)
usou 2002–2003 com ZIPs idênticos aos originais e TXT equivalentes coexistentes,
totalizando 77,69 MiB de candidatos, acima do limiar. Com `process` solicitado,
os dois modos reconciliaram independentemente os 32 campos de 278.085 cotações
cada, sem exclusões nem duplicação pelas representações equivalentes. A ordem
e os Parquets físicos coincidiram entre os modos; nenhum worker ou temporário
permaneceu após a limpeza. Esse caso comprova integridade, não ganho de tempo.

```bash
mkdir -p .benchmarks
uv run --locked --no-sync python scripts/benchmark_ingestion.py \
  --scenario b3_multi_4x25k --rows 500000 --source-count 4 --worker-limit 4 \
  --backend process --processing-mode fast --repeats 3 \
  --output .benchmarks/b3-process-500k.json
```

## Como aceitar uma nova alteração

A implementação passou no pre-push local em Python 3.12.3, 3.13.9 e 3.14.0.
Cada ambiente executou 2.330 testes determinísticos e 200 testes do executor
de validação. A cobertura de produto, incluindo branches, foi de 91,22%,
91,22% e 91,12%, respectivamente; a cobertura do executor foi de 91,12% nos
três. A auditoria das 116 dependências travadas também passou. Esses resultados
são locais; a execução da CI remota e a publicação são etapas separadas.

1. Congele baseline e candidato distintos, com hashes de produto, suporte e
   entradas. Mantenha dependências, seleção e recursos iguais dentro de cada par.
2. Alterne a ordem em processos novos, registre todas as amostras e meça a
   operação completa. CPU, RSS agregado e auditoria externa têm métricas próprias.
3. Exija equivalência de todos os valores e ocorrências, além dos testes de
   corrupção, exclusões, fontes vazias após seleção e cancelamento.
4. Reconcilie o corpus oficial fornecido nos dois modos sobre a versão final;
   passe os testes, hooks e documentação antes de aceitar a alteração.

Rust pode ser avaliado como um núcleo em lotes se um gargalo relevante
persistir após essas mudanças. Essa decisão exige ganho adicional na operação
completa, equivalência exata e distribuição compatível com os Python suportados.
Um microbenchmark isolado não justifica trocar a linguagem da biblioteca.
