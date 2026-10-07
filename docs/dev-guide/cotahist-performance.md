# Performance e integridade de COTAHIST

## Contrato das otimizações

As otimizações de 06/10/2026 preservam as assinaturas públicas, o schema v2,
os nomes de saída e a seleção de mercados. Os 32 campos, os decimais exatos,
os bytes originais, a proveniência, a ordem e as ocorrências repetidas continuam
conferidos antes da publicação. CRC, identidade das fontes, replay e leitura
final completa permanecem obrigatórios.

O parser produz uma tupla canônica diretamente e aplica um plano derivado do
layout, reutilizando os validadores escalares existentes. O digest usa tabelas
constantes de tags e comprimentos. A leitura final monta o mesmo framing v2
com Arrow em segmentos limitados pelas fontes. Essas tabelas não armazenam
valores financeiros. Veja o [contrato do digest](../reference/b3-schema-v2.md).

## Parser e leitura final: comparação de versões distintas

Três pares por modo processaram os mesmos 500.000 registros em quatro fontes,
em processos Python novos e ordem alternada. Ambiente: Python 3.13.9, PyArrow
23.0.1, Linux x86_64, oito CPUs, com os outros processos da máquina em execução.
O backend solicitado foi `thread`; `slow` manteve um worker.

| Modo | Mediana inicial | Mediana otimizada | Redução de tempo | Redução de CPU |
| --- | ---: | ---: | ---: | ---: |
| `fast` | 84,148 s | 57,901 s | 31,19% | 29,57% |
| `slow` | 66,477 s | 47,089 s | 29,16% | 28,63% |

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

| Modo | Mediana inicial | Mediana integrada | Redução de tempo | Redução de CPU |
| --- | ---: | ---: | ---: | ---: |
| `fast` | 96,363 s | 63,489 s | 34,11% | 29,34% |
| `slow` | 76,374 s | 50,380 s | 34,04% | 33,85% |

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

| Modo | API na campanha anterior | API na campanha atual | Redução observada |
| --- | ---: | ---: | ---: |
| `fast` | 3.895,088 s (64min55s) | 2.989,776 s (49min50s) | 23,24% |
| `slow` | 3.350,505 s (55min51s) | 2.297,342 s (38min17s) | 31,43% |

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

## Preflight concorrente optativo

O padrão continua `GDF_B3_EXECUTOR_BACKEND=thread`. Com ativação explícita de
`process`, o modo `fast` admite preflight concorrente somente quando há pelo
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
