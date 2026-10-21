# Validação com dados externos

## Executar

Para auditar a matriz completa sem depender da configuração implícita do
ambiente, use o executor opt-in com todos os caminhos explícitos. O relatório e
os artefatos temporários devem ficar fora do repositório:

```bash
uv run --locked --no-sync python scripts/real_validation.py \
  --source all \
  --cotahist-path /external/path/COTAHIST \
  --cvm-output /tmp/globaldatafinance-cvm-output \
  --report /tmp/globaldatafinance-real-validation/first-run \
  --timeout 3600
```

## Escopo e validação

`all` cria casos COTAHIST para cada ano do catálogo local dentro do intervalo
solicitado (ou de todos os anos disponíveis quando o intervalo é omitido) e
as combinações válidas das sete janelas documentais CVM, incluindo IPE desde
2003. Anos ausentes no intervalo pedido fazem a campanha falhar antes do processamento.
Com `--cotahist-mode all`, cada ano recebe uma prova `fast` e uma paridade
integral `fast`/`slow`; a campanha também inclui uma paridade integral
multi-anual para todo o intervalo. A preparação confere nomes, containers,
anos e hashes e aplica a precedência ZIP. Representações ZIP/TXT do mesmo ano
continuam exigindo conteúdo completo equivalente. A validação de todas as
cotações acontece na API antes da publicação e novamente na reconciliação
independente; a preparação do manifesto não repete esse parsing completo.
Um container inválido impede a criação da campanha; campos inválidos nas
cotações produzem um caso `failed`, sem publicação pela API.
COTAHIST nunca é baixado pelo executor.
Na CVM, `--verify-cvm-catalog` grava `cvm-catalog.json` com todos os anos
publicados e omissões da seleção. Se um ano publicado dos documentos escolhidos
ficar fora da matriz, interrompe a campanha com código 1; omita essa opção em
campanhas intencionalmente parciais. Cada CSV é reconciliado campo a campo por
um parser independente, incluindo cabeçalho, ordem, vazios e contagem. O
resultado registra hashes de todos os membros ZIP, anexos e campos conferidos.
Para toda a história CVM, use `--initial-year 2003 --document all`; os ZIPs
retidos pela fachada no workspace isolado são removidos pelo executor somente
após persistir a evidência, junto com os demais artefatos da campanha.
A matriz CVM acessa somente os URLs oficiais explicitamente definidos pelo
código e classifica HTTP 404/410 como
`not_published`, indisponibilidade de rede como `external_failure` e conteúdo
inválido ou falha de processamento como `failed`.

## Baseline histórico e acompanhamento

Por padrão, a campanha COTAHIST reconcilia os arquivos fornecidos com os hashes
congelados no próprio manifesto da execução. Selecionar 2000–2026 não impõe
automaticamente o corpus histórico usado na auditoria inicial. Para exigir
aquele corpus específico, seus 27 checksums e as métricas históricas, selecione
explicitamente a paridade multi-anual com `--cotahist-frozen-baseline`:

```bash
uv run --locked --no-sync python scripts/real_validation.py \
  --source cotahist --cotahist-path /external/path/COTAHIST \
  --initial-year 2000 --last-year 2026 --cotahist-mode all \
  --cotahist-frozen-baseline --case cotahist-multi-parity-2000-2026 \
  --report /external/path/cotahist-historical-acceptance --timeout 43200 --progress
```

A opção `--progress` escreve em stderr a preparação, o início e o resultado
dos casos, e uma atualização a cada 30 segundos enquanto o worker está ativo.
O stdout continua contendo o resumo JSON final. As etapas de extração,
validação do Parquet e reconciliação aparecem no log individual do caso.
Uma atualização de atividade não equivale a progresso de linhas nem comprova
que a etapa atual está livre de bloqueios. A campanha completa lê todas as
cotações nos dois modos e pode levar horas; não inicie uma segunda execução
para substituir uma que ainda está ativa.

A opção `--cotahist-frozen-baseline` exige o intervalo completo e a seleção
do caso multi-anual. A intenção
fica em `frozenBaseline` no caso e é preservada por `--resume`; uma retomada
não troca uma campanha genérica pela aceitação histórica. Para mudar essa
seleção, use uma nova pasta de relatório. Sem `--resume`, o CLI rejeita pastas
com evidência de campanha anterior, preservando os arquivos existentes.
Caminhos de saída são resolvidos de forma
consistente, inclusive quando a pasta possui um link simbólico na ancestralidade;
a contenção no destino e a exigência de um único Parquet continuam obrigatórias.

Na campanha COTAHIST, `DiskFullError` e `PathPermissionError` reportados pela
extração são `external_failure`; os diagnósticos originais permanecem no
relatório. Conteúdo inválido e divergências de integridade continuam `failed`.

## Relatórios e retomada

Cada caso roda em um processo isolado. O diretório indicado por `--report`
contém `manifest.json`, um `results.jsonl` com apenas o resultado atual de cada
caso, `summary.json`, logs individuais e evidências de artefatos. Use
`--resume --report <mesmo-diretório>` para reexecutar somente casos
`external_failure` ou ainda não classificados; resultados funcionais e
`not_published` são preservados. Os resultados persistidos são evidência do
chamador, não uma atestação assinada: use `--resume` somente em um diretório
de relatório confiável quando a conclusão aprovada/reprovada precisar ter
valor probatório. Antes da retomada, cada arquivo COTAHIST é
comparado ao `inputSizeBytes` e ao `inputSha256` do manifesto. O hash é
calculado uma vez por caminho compartilhado; qualquer drift gera
`ReportFormatError`, não reexecuta nem sobrescreve resultados antigos e exige
uma nova campanha. O `caseId`, ano, modo e input COTAHIST também precisam
corresponder ao catálogo atual. Casos CVM primeiro validam o
`campaign.cvmOutput` persistido com a política de destinos externos e depois
são reconstruídos da matriz oficial de documento/ano: os campos persistidos,
inclusive `inputPath`, `url` e `outputRoot`, precisam ser idênticos ao caso
reconstruído e ao destino da campanha antes de um worker ser iniciado. Um
`outputRoot` adulterado falha antes de `mkdir`, `mkdtemp`, worker ou cliente
HTTP. A sonda CVM usa somente HTTPS no endpoint canônico, não segue
redirecionamentos e não persiste um corpo de preflight. O limite de bytes do
arquivo comprimido é aplicado tanto ao `Content-Length` quanto ao streaming da
fachada pública; o hash registrado é calculado no ZIP imediatamente antes da
extração pela própria fachada. `--report` e `--cvm-output` passam pela política
de destinos sensíveis antes de qualquer criação de diretório; raízes do
sistema, diretórios protegidos, drives Windows relativos e UNC não confiáveis
são rejeitados, enquanto `/tmp` e uma UNC explicitamente permitida podem ser
usados conforme a política compartilhada. O código de saída é `0` somente
quando toda a matriz foi executada sem falhas funcionais, falhas externas,
combinações não executadas ou processos órfãos; `1` indica falha funcional e
`2` indica dependência externa, timeout, execução incompleta ou processo órfão.
Falhas de I/O, formato de relatório, segurança ou configuração da campanha
tratadas como `invalid_campaign` retornam `3`. Erros de sintaxe dos argumentos
retornam `2` pelo `argparse`.

## Contratos relacionados

- [Decisão da campanha auditável](../decisions/real-validation-campaign.md)
- [Corpus COTAHIST auditado](../reference/cotahist-v2-supplied-corpus.md)
- [Aceite de release](release-readiness.md)
