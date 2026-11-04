# Campanha real auditável de validação

**Status:** Aceita
**Data:** 2026-09-01
**Escopo:** validação opt-in de dados externos e artefatos da biblioteca

## Decisão

A validação integral de COTAHIST e CVM é executada por
`scripts/real_validation.py`, um comando de desenvolvimento opt-in que não
faz parte da API da biblioteca. O executor é dividido em matriz de casos,
workers isolados, validadores de fonte e persistência de evidências.

O comando exige caminhos explícitos. COTAHIST é sempre caller-owned e nunca é
baixado; CVM acessa somente os endpoints oficiais da matriz. Relatórios,
artefatos de trabalho e saída CVM devem ficar fora do repositório. A campanha
não lê `.env` implicitamente nem incorpora dados financeiros ao Git.

Cada caso usa a facade pública correspondente (`HistoricalQuotesB3` ou
`FundamentalStocksDataCVM`) como único caminho de processamento. O worker
valida a entrada, executa o caso, lê os Parquets produzidos com os engines
reais e verifica schema, contagem, conteúdo mínimo e limpeza. Um processo
separado por caso limita vazamentos de estado e permite timeout com
classificação explícita.

O relatório externo tem `manifest.json`, um resultado corrente por caso em
`results.jsonl`, logs individuais, evidência dos artefatos e `summary.json`.
Os estados são `passed`, `failed`, `skipped`, `external_failure` e
`not_published`. O código de saída só é zero quando todos os casos foram
classificados sem falha, não há dependência externa pendente e a verificação de
processos não encontra órfãos. `--resume` usa o manifesto existente e só
reexecuta falhas externas ou casos ainda não executados.

Todo `--report`, `--cvm-output` e `campaign.cvmOutput` persistido no manifesto
passa pela política compartilhada de destinos sensíveis, mantendo o texto
original do caminho para validar drives, raízes relativas e UNC mesmo em um
host POSIX. A validação ocorre antes de `mkdir`, `mkdtemp`, manifesto ou
artefato. Ao retomar COTAHIST, o executor valida novamente o catálogo, compara
tamanho e SHA-256 de cada input com o manifesto e calcula o hash uma única vez
por caminho compartilhado. Drift gera `ReportFormatError` com `caseId` e exige
uma nova campanha; resultados existentes não são reexecutados nem
sobrescritos.

Os resultados persistidos são evidência do chamador, não uma atestação
assinada. Quando uma conclusão aprovada/reprovada precisar ter valor
probatório, a retomada exige um diretório de relatório confiável.

Ao retomar CVM, o executor primeiro lê, normaliza e valida
`campaign.cvmOutput` com essa mesma política. Em seguida reconstrói cada caso
pela matriz oficial de documento/ano e exige igualdade de `caseId`, fonte,
documento, ano, modo, `inputPath`, `url` e `outputRoot` com o destino da
campanha antes de criar um worker. Um `outputRoot` adulterado é rejeitado antes
de `mkdir`, `mkdtemp`, worker ou cliente HTTP. A sonda de publicação usa
somente o URL HTTPS canônico, não segue redirects e não grava o corpo da
resposta. O limite de ZIP comprimido é imposto antes da escrita pelo
`Content-Length`, quando disponível, e pelo contador do streaming da fachada.
O tamanho e SHA-256 registrados são observados no ZIP que a fachada pública
passa à extração, e não em uma cópia baixada separadamente.

Os scripts do executor têm uma cobertura determinística separada da cobertura
de `src`, com piso próprio de 85% no pre-push e na pipeline de qualidade.

## Consequências

Essa fronteira mantém rede, datasets grandes, tempo de execução e relatórios
fora do runtime da biblioteca. A matriz pode provar a disponibilidade real sem
transformar uma indisponibilidade de CVM ou de DNS em aprovação. A execução é
mais lenta que a suíte determinística e exige que o chamador forneça o
dataset COTAHIST e um diretório externo para a saída CVM.

As regras detalhadas de cada fonte continuam nos seus owners: a resolução e o
catálogo COTAHIST ficam em `brazil/b3_data/historical_quotes/`; download,
extração e commit CVM ficam em `brazil/cvm/fundamental_stocks_data/`.
