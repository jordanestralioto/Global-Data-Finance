# Aceite de release

O aceite reúne evidências do mesmo commit candidato antes da publicação.
Os contratos de [testes](testing.md), [publicação transacional](../reference/transactional-publication.md),
[HTTP e retry](retry-strategy.md) e [logs](logging-system.md) continuam nos seus
documentos canônicos.

## Validações obrigatórias

| Ambiente | Execução |
| --- | --- |
| Linux, Python 3.12/3.13/3.14 | Suíte determinística completa, gates, cobertura do produto e do executor de validação real. |
| Windows/macOS, Python 3.12/3.13/3.14 | Regressões nativas de lock, recuperação, ZIP, HTTP, retry, logs, CVM e B3. |
| Linux, Python 3.13 | Campanha completa de quedas e falhas de armazenamento em oito shards. |
| Distribuições | Inspeção de wheel/sdist e fluxos locais CVM/B3 em instalações independentes. |

Os pisos agregados de cobertura continuam em 85%, incluindo branches. A suíte
nativa é focada; os cenários obrigatórios precisam executar e passar. Uma
ausência de permissão Windows para criar symlink, identificada pelo erro 1314,
pode pular somente o cenário de alias correspondente. Isso não dispensa os
testes de publicação e recuperação.

O plugin `tests.support.release_evidence` registra os resultados reais do pytest
e rejeita suítes vazias, totalmente puladas, incompletas ou sem comportamento
crítico. Os artefatos incluem JUnit, versão do ambiente e commit candidato.

## Campanha de falhas

A campanha usa diretórios temporários, arquivos do chamador e pequenos Parquets
válidos. Ela cobre destinos novos/existentes e backups por hard link/cópia.
Cada operação é interrompida antes e depois; os estados resultantes recebem
novas quedas durante a recuperação. Após a retomada, três tentativas precisam
preservar um lote completo antigo ou novo, conforme o journal, sem alterar
arquivos do chamador ou deixar resíduos de ownership conhecido.

Também são injetados ENOSPC/EIO, escritas parciais, falhas persistentes no
rollback e interrupções na limpeza de filhos. Cada fase de recuperação recebe
falhas de armazenamento. O arquivo vazio de guarda no Windows é persistente
por contrato e não é lixo transacional.

Para executar toda a campanha localmente:

```bash
GDF_PUBLICATION_REPORT_DIR=.cache/publication-campaign/reports \
uv run --locked --no-sync pytest \
  tests/macro_infra/test_publication_fault_campaign.py \
  -m "integration and slow" --no-cov
```

Para particionar, defina `GDF_PUBLICATION_SHARDS=8` e execute cada índice de
`GDF_PUBLICATION_SHARD=0` até `7`, mantendo os relatórios no mesmo diretório.
Essas variáveis pertencem ao harness de testes; não configuram a biblioteca.
O isolamento da campanha completa usa processos Linux; a suíte nativa usa os
checkpoints portáveis. A coleta normal do pytest não inicia a campanha lenta.

O verificador exige os quatro cenários em todos os shards, reconstrói os casos
esperados a partir dos rastros e rejeita qualquer execução faltante:

```bash
uv run --locked --no-sync python scripts/check_release_evidence.py \
  .cache/publication-campaign/reports --shards 8
```

Uma execução sem particionamento usa `--shards 1` na verificação. Os processos
executam operações reais e terminam por `os._exit`; os erros de disco são
injetados na fronteira de I/O, sem encher o disco do computador.

## Pacotes e publicação

Depois de `uv build`, a inspeção verifica metadados, módulos de segurança e
digests das duas distribuições:

```bash
uv run --locked --no-sync python -m scripts.check_distributions dist
```

No workflow de release, `--expected-version` exige a versão da tag estável.
Um build local sem tag pode ter versão de desenvolvimento. Cada distribuição
é instalada em um ambiente separado, e o smoke roda com Python `-I`, fora do
checkout. Ele confere a instalação carregada, os exports públicos, extração
local CVM e B3 em ZIP/TXT com modos `fast`/`slow`.

O job `release-acceptance` exige os jobs de qualidade, segurança e pacotes,
todos os ambientes nativos, campanha completa, coberturas e digests dos
artefatos baixados. Uma falha produz um relatório pendente e bloqueia o job
de publicação. Um dry-run realiza essas verificações sem enviar ao PyPI.

## Evidência e limites

Os artefatos de aceite e testes ficam disponíveis por pelo menos 30 dias na
execução da CI. O relatório identifica o SHA, a versão, os hashes e o link da
execução, e separa `passed`, `failed`, `skipped` e `external_failure`.
O aceite usa as evidências produzidas pela CI, sem depender de planos ou
registros de revisão versionados no repositório.
Falta de ambiente nativo ou execução obrigatória mantém o aceite pendente.

Recuperação de queda do processo não garante durabilidade universal contra
queda de energia nem visibilidade simultânea de todo o lote para leitores
durante o commit. O limite HTTP também não é uma medição de toda a memória do
processo. Os contratos de ownership e do lock externo CVM permanecem vigentes.
