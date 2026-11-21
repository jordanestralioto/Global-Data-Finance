---
name: local-quality-gates
description: >-
  Use para criar, revisar ou reparar quality gates locais e hooks de pre-commit
  e pre-push em qualquer stack. Ative com pedidos como "configura os hooks Git",
  "cria um pre-push", "arruma meu pre-commit", "bloqueia debug no commit",
  "valida o lockfile", "limita complexidade no linter", "audita dependências no
  push", "divide testes entre commit e push" ou
  "bloqueia código morto antes do commit". Cobre escolha de runner e estágio,
  segurança de auto-fix, baseline, validação do estado staged, instalação e
  teste dos hooks. Não use para pipeline remota, E2E de navegador, auditoria
  manual de segurança, remoção de código obsoleto da aplicação sem configurar
  gates ou validação pesada de dados de produção.
---

# Quality gates locais

Configure gates determinísticos, meça seu custo e escolha o estágio conforme o
contrato do projeto. Hooks locais podem ser ignorados ou estar ausentes;
controles essenciais também precisam de proteção remota equivalente.

## Escolha o modo antes de começar

**Ajuste pontual:** consertar, adicionar ou remover um hook ou gate específico
("arruma meu pre-commit", "o push não roda nada", "adiciona o gitleaks").
Preserve o runner e os gates existentes, aplique as regras abaixo, teste o hook
alterado e relate só o que mudou. Não monte a matriz completa, não percorra o
catálogo de slots nem abra uma auditoria de código morto.

1. Fixe o `rev` de cada repositório remoto de hooks no SHA de 40 caracteres do
   commit da release, com a release em comentário. Numa tag anotada,
   `git rev-parse <tag>` e `pre-commit autoupdate --freeze` devolvem o SHA do
   objeto da tag; resolva o commit como no item 07 do Passo 3.
2. Nenhum hook atualiza, sincroniza ou resolve dependências. Para lockfile, use
   só checks somente leitura (`uv lock --check`, `poetry check --lock`,
   `cargo check --locked`); `go mod verify` não prova a coerência entre `go.mod`
   e `go.sum`.
3. Auto-fixers e corretores lexicais excluem projeções geradas rastreadas;
   corrija a fonte canônica e regenere.
4. Auto-fix só para espaços, formatadores determinísticos e imports. Não
   enfraqueça asserções nem adicione supressões para passar.
5. Depois de um auto-fix, rode `git add --` apenas nos arquivos alterados.
6. Dívida pré-existente vira baseline por identidade do achado, não por
   contagem.
7. Confira se o hook está instalado, se `core.hooksPath` muda o local efetivo e
   se o conteúdo instalado é a versão esperada, inclusive um `<hook>.legacy` que
   o pre-commit preserva e continua executando.
8. Ferramenta ausente ou quebrada é `ERROR`, não sucesso; `SKIP` declara o
   motivo.
9. Rode o gate alterado pelo runner, no estágio dele, e mostre o código de
   saída. `pre-commit run --all-files` não cobre `commit-msg` nem `pre-push`.

**Setup completo ou auditoria:** projeto sem runner, novo estágio, revisão de
todos os gates, código morto, limites ou perfil estrito. Siga as seções abaixo e
o procedimento inteiro, incluindo a matriz do Passo 2 e a prova de `PASS` e
`FAIL` do Passo 5. Se um ajuste pontual crescer para um desses casos, troque de
modo e diga isso ao usuário.

## Contrato portátil e política do projeto

1. Leia as regras e os comandos oficiais do projeto antes de escolher gates.
   Preserve o runner, o gerenciador e as exceções já contratadas.
2. Para cada gate, registre: estágio, comando e versão da ferramenta, arquivos
   ou snapshot inspecionados, custo observado, efeitos no workspace, política
   que aplica e status (`ENABLED`, `DELEGATED`, `MANUAL`, `UNSUPPORTED`).
3. Aplique em toda stack os invariantes de execução: nenhuma falha declarada
   bloqueante vira sucesso silencioso; auto-fix é revisado antes de staging;
   validação de dependências não atualiza versões; o hook instalado é testado.
4. Os slots abaixo formam um catálogo, não uma lista universal obrigatória.
   Ative regras de estilo, limites numéricos e os scanners estritos de IA quando
   o contrato do projeto ou o usuário os pedir. Se uma cobertura bloqueante
   pedida não tiver ferramenta determinística, informe `UNSUPPORTED` e pare a
   configuração daquele gate; não declare `PASS` nem invente um substituto.
5. Escolha a ferramenta nativa ou já instalada antes de copiar helpers desta
   skill. Um hook local que chama `python` exige Python no `PATH`; declare e
   prove esse requisito mesmo em projetos Node, Go, Rust ou poliglotas.
6. Em setups completos, auditorias ou pedidos sobre código morto, avalie as
   sete capacidades de `[DEAD_CODE]`. Em manutenção pontual de outro hook,
   preserve os gates existentes e registre essa avaliação como fora do escopo;
   não abra uma auditoria adicional nem declare cobertura não avaliada.

### Política transversal de dependências (todas as stacks)

Separe três operações antes de compor o hook:

1. **Validar o lockfile**: confirmar coerência sem alterar arquivos rastreados,
   instalar pacotes no ambiente do projeto ou persistir uma nova resolução.
   Rede, caches e build exigem contrato declarado e custo medido. É a única
   operação de dependências permitida ao `[LOCKFILE]` no `pre-commit`.
2. **Sincronizar o ambiente**: instalar o que já está fixado no lockfile em
   `.venv`, `node_modules` ou equivalente. É uma ação de bootstrap/setup; não
   deve ser adicionada ao `pre-commit` por inferência. Por exemplo,
   `uv sync --locked` valida o lockfile e pode modificar `.venv`, mas não
   atualiza as versões resolvidas.
3. **Atualizar ou resolver dependências**: escolher versões ou reescrever o
   lockfile em uma alteração deliberada, revisada, testada e auditada fora do
   hook. Consulte os comandos por stack em
   [stack-detection.md](references/stack-detection.md#11-dependency-lifecycle-classification).

Um prefixo usado apenas para invocar uma ferramenta já fixada do gate, como
`uv run --locked`, não é um updater por si só. Mantenha-o somente quando fizer
parte do contrato existente do projeto; se a execução puder sincronizar o
ambiente implicitamente, considere `--no-sync` depois que o setup local já
estiver concluído. Com `--no-sync`, o `--locked` do `uv run` deixa de verificar
o lockfile, e o comando roda mesmo com `uv.lock` desatualizado: mantenha
`uv lock --check` como gate próprio. Veja as demais nuances do uv em
[stack-detection.md](references/stack-detection.md#11-dependency-lifecycle-classification).

Se a stack não fornecer uma verificação nativa somente leitura, exija a paridade
staged entre manifesto e lockfile usando o gate compartilhado; não invente um
comando de atualização para preencher a lacuna. Se o projeto declarar uma
verificação nativa, mas a ferramenta não puder ser iniciada, o resultado é
`ERROR`, código 2, conforme a política fail-closed.

### Fronteira entre documentação e supressão executável

Classifique citações de supressões pela extensão, não pelo diretório. `.md`,
`.markdown`, `.rst` e `.txt` permitem citações explicativas, inclusive blocos de
código documentais, OpenSpec e projeções. Outros formatos textuais rejeitam
esses marcadores em strings, docstrings, fixtures, configurações e manifestos.
Debug e stubs são inspecionados no código; segurança operacional cobre texto
adicionado em todo formato textual, inclusive documentação. Consulte
[agent-anti-patterns.md](references/agent-anti-patterns.md).

### Pre-push e CI

- **Pre-push**: Escolha suítes, typechecks e auditorias pelo custo medido e pelo
  contrato. Identifique commits/refspecs enviados ou a cobertura residual do
  working tree. Helpers de diff staged não comprovam cobertura do push. Com o
  runner pre-commit, confira o que ele inspeciona em cada estágio (stash, commit
  raiz, refs remotas desatualizadas, push de vários refs) em
  [gate-catalog.md](references/gate-catalog.md#6-hook-runner-pins-and-snapshots).
- **Testes por estágio**: `[TESTS_FAST]` tem escopo e custo delimitados;
  `[TESTS_FULL]` executa toda a suíte local atribuída ao push.
- **Auditoria de dependências**: Fixe um scanner somente leitura e registre
  fonte, grafo, política de achados e indisponibilidade. Ausência de consulta
  não comprova uma auditoria limpa. Leia
  [gate-catalog.md](references/gate-catalog.md).
- **CI**: Atribua E2E, integrações e scans de infraestrutura ao contrato remoto.

## Status de Execução e Política Fail-Closed

Os hooks e scripts devem seguir códigos de saída explícitos:

| Status  | Código | Significado                                                           | Comportamento                                                             |
| :------ | :----: | :-------------------------------------------------------------------- | :------------------------------------------------------------------------ |
| `PASS`  |  `0`   | O gate executou e validou seu snapshot declarado.                     | Permite a operação daquele estágio.                                       |
| `FAIL`  |  `1`   | Violação determinística encontrada.                                   | Bloqueia a operação; exibe motivo e reprodução.                           |
| `ERROR` |  `2`   | Falha de infraestrutura (erro no Git, ausência de ferramenta, crash). | Bloqueia a operação; não converte erro em sucesso.                        |
| `SKIP`  |  `0`   | Nenhuma entrada relevante segundo a política do gate.                 | Declara o motivo; não conta como gate executado em evidência obrigatória. |

Estes resultados são normalizados. Preserve os códigos nativos e mapeie sua
semântica e severidade documentadas antes de classificar; consulte
[dead-code-policy.md](references/dead-code-policy.md#5-native-outcomes-and-evidence).

## Procedimento

### Passo 1: Inspecionar o Workspace e Identificar a Stack

1. Inspecione a raiz e subpastas do workspace em busca de manifestos
   (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `composer.json`).
2. Identifique gerenciador e prefixo de execução (`uv run`, `pnpm exec`,
   `cargo`). Classifique os comandos pelo lifecycle de dependências acima; não
   deduza atualização ou sincronização a partir da presença de manifesto e
   lockfile.
3. Consulte [stack-detection.md](references/stack-detection.md) para mapear
   linters, formatters, typecheckers e runners já configurados.
4. Inspecione se já existe runner configurado (`.pre-commit-config.yaml`,
   `.husky/`, `lefthook.yml` ou scripts em `.git/hooks/`), se os hooks estão
   instalados e se `core.hooksPath` altera o local efetivo. Identifique o
   runtime disponível para qualquer helper local.
5. Determine a entrada de cada estágio: index no pre-commit, mensagem no
   commit-msg e commits/refspecs no pre-push. Um check de projeto que lê o
   working tree deve tratar alterações não staged como outro snapshot. O stash
   do runner não esconde arquivos não rastreados: um gate de repositório inteiro
   que lê o disco pode aprovar o commit graças a um arquivo que ficou fora dele.
   Classifique essa cobertura como parcial (working tree) e feche-a com pre-push
   em checkout limpo do commit enviado ou com CI.

### Passo 2: Análise de Lacunas e Mapeamento de Slots

Compare o estado atual com a matriz e os perfis em
[gate-catalog.md](references/gate-catalog.md). Selecione os slots pertinentes ao
pedido; uma manutenção pontual não exige preencher todo o catálogo.

- `[DEAD_CODE]`: No escopo definido acima, avalie as sete capacidades e seus
  status em
  [dead-code-policy.md](references/dead-code-policy.md#1-capability-report).
  Lint aprovado não comprova cobertura completa nem aprova APIs de
  compatibilidade.

No setup completo, registre a decisão em uma matriz com colunas `gate`,
`estágio`, `comando/versão`, `snapshot`, `efeito`, `duração observada`, `status`
e `justificativa`. Inclua slots omitidos quando a ausência poderia ser
confundida com cobertura.

Para cada slot selecionado, registre regra nativa, métrica, limite, escopo,
estágio e status (`ENABLED`, `DELEGATED`, `MANUAL`, `UNSUPPORTED`).
Complexidade ciclomática e cognitiva são métricas distintas. O perfil estrito
de exemplo usa tetos de `15` para cada métrica suportada, `4` níveis de
aninhamento e `50` statements por rotina; adote-os somente se o projeto
concordar. Um perfil bloqueante completo aceita apenas `ENABLED` ou
`DELEGATED`; cobertura pedida mas indisponível é `UNSUPPORTED`, não `PASS`.
Leia a política em [gate-catalog.md](references/gate-catalog.md) e os limites
de análise em [agent-anti-patterns.md](references/agent-anti-patterns.md).

### Passo 3: Scaffolding e Composição dos Hooks

01. Se o projeto já utiliza um runner, adapte a configuração existente sem
    remover regras de negócio válidas.
02. Sem runner, escolha um que a equipe possa instalar e manter com as
    ferramentas já adotadas. Use
    [.pre-commit-config.yaml](assets/templates/pre-commit-config.yaml.template)
    ou [lefthook.yml](assets/templates/lefthook.yml.template) como scaffold, não
    como configuração pronta: preencha comandos, congele versões e remova
    exemplos não selecionados. A escolha não depende só da linguagem.
03. Isole o escopo em monorepos ou projetos multi-stack usando regex de
    caminhos, conforme
    [multi-stack-patterns.md](references/multi-stack-patterns.md).
04. Configure `[LINTER]` com as regras existentes baseadas em parser. Prefira
    diagnósticos somente leitura. Correções seguras de fluxo ou retorno exigem
    contrato explícito e revisão antes de staging. Não habilite correções
    inseguras nem reescritas automáticas de negócio. Não imponha uma regra de
    retorno único; guard clauses devem esclarecer precondições e fluxo
    principal.
05. Configure `[CIRCULAR_DEPENDENCIES]` quando requerido. Um ciclo novo falha.
    Se a ferramenta aceitar escopo, execute o grafo afetado; não substitua uma
    exigência do projeto por `SKIP`. Registre ciclos históricos por identidade.
06. Configure `[LOCKFILE]` em projetos com lockfile autoritativo como gate de
    validação, conforme a política de dependências acima: exija o lockfile
    correspondente no diff staged ou um comando nativo que comprove coerência
    sem persistir resolução, reescrever manifestos ou instalar dependências
    (`uv lock --check`, `poetry check --lock`, `cargo check --locked`,
    `go mod tidy -diff` quando suportado). Sem esse comando, mantenha a paridade
    e registre a limitação; nunca substitua o gate por `install`, `sync`,
    `update`, `upgrade`, `lock` ou `tidy`. `go mod verify` audita o cache de
    módulos, não a coerência entre `go.mod` e `go.sum`.
07. Para cada repositório remoto de hooks, resolva uma release e fixe `rev` em
    um SHA de commit de 40 caracteres antes de declarar a configuração pronta.
    Preserve a release em comentário; não deixe tags mutáveis na configuração.
    Numa tag anotada, `git rev-parse <tag>` e `pre-commit autoupdate --freeze`
    devolvem o SHA do objeto da tag. Resolva o commit com
    `git rev-parse '<tag>^{commit}'` ou consulte o upstream com
    `git ls-remote <repo> 'refs/tags/<tag>' 'refs/tags/<tag>^{}'`; sem linha
    `^{}`, a tag é leve e a própria ref aponta para o commit. Confira cada pin
    contra o upstream.
08. Quando houver `additional_dependencies`, resolva e fixe o grupo compatível
    em conjunto. Atualize pacote base e plugins juntos, valide a resolução e só
    então registre versões exatas.
09. Classifique projeções geradas (`.agents/`, `.claude/`, `.codex/`, mirrors e
    artefatos equivalentes) antes de atribuir hooks. Hooks auto-fixáveis e
    corretores lexicais (`end-of-file-fixer`, `ruff --fix`, formatadores e
    `codespell`) devem declarar `exclude` local para esses caminhos quando eles
    puderem estar rastreados. Mantenha scanners de segurança e validações
    semânticas no escopo apropriado e, quando a projeção precisar ser validada,
    use um gate dedicado somente leitura. Adaptadores de diff do consumidor,
    como a varredura operacional e a checagem de sintaxe shell, não excluem a
    projeção rastreada, sobretudo quando hooks executam scripts dela; só o
    classificador de debug e stubs pode excluí-la. Corrija sempre a fonte
    canônica e regenere a projeção; não corrija o espelho diretamente.
10. Quando pre-push fizer parte do pedido ou contrato do projeto, substitua o
    placeholder pelo gate escolhido, declare `stages: [pre-push]` ou `pre-push:`
    e instale esse estágio. Fora desse escopo, remova o placeholder e o estágio
    do scaffold. Se o working tree estiver sujo, teste os commits em checkout
    isolado quando a garantia for sobre o push; caso contrário, reporte que o
    resultado cobre o working tree, não o snapshot enviado.
11. Para `[FILE_LINES]` em um consumidor do harness, selecione
    `"check-max-lines"` em `components.tools` de `.agents/harness.json`, rode
    `harness-sync` e configure a tool projetada (`tools/check-max-lines`) sem
    filenames. Confirme Python 3.13+, limites e escopo compatíveis; o gate lê o
    working tree. Só declare cobertura staged se o runner isolar alterações não
    staged. Veja [gate-catalog.md](references/gate-catalog.md).
12. Quando `[DEAD_CODE]` fizer parte do escopo, siga
    [dead-code-policy.md](references/dead-code-policy.md). Use um analisador
    nativo fixado, somente leitura, no escopo completo declarado, incluindo
    deleções e mudanças de configuração. Cobertura staged exige isolamento ou
    rejeição de entradas divergentes, inclusive consumidores não rastreados.
    Cobertura apenas do working tree é parcial. Meça e prove o bloqueio.

### Passo 4: Instalar Scripts Auxiliares de Sanidade de IA

Quando o projeto seleciona estes helpers e dispõe de Python 3.10+, copie ou
referencie apenas os helpers necessários na pasta `scripts/` do projeto. Eles
usam a biblioteca padrão, mas exigem o runtime Python; não os instale por
inferência em qualquer stack:

- `check_diff_sanity.py`: Bloqueia debug, stubs, supressões e operações
  perigosas recém-adicionadas conforme
  [agent-anti-patterns.md](references/agent-anti-patterns.md). Para saída
  legítima de CLI, autorize cada arquivo com `--allow-print-file <path>`;
  diretórios de scripts não recebem liberação automática. Complexidade e
  aninhamento exigem analisador com parser.
- `check_test_integrity.py`: Bloqueia `.only`/`fit`, skips e perda de asserções
  sem razão; exige policy staged em `.test-deletions.json` para deleções e
  renames que removam a classificação de teste ou a coleta padrão do pytest,
  Jest ou Vitest em alguma plataforma: a caixa do nome conta, e diretórios
  ignorados por padrão, como `build/`, `dist/`, ocultos e `node_modules/`, tiram
  o teste da coleta. Autorize o caminho antigo exato em `allowed_deletions`; a
  policy só no working tree não vale. O helper lê os caminhos dos metadados
  staged como bytes e o patch de cada teste como texto, e verifica todas as
  deleções e renames staged, mesmo com filtro de arquivos no CLI. Adapte as
  raízes e os padrões de coleta à configuração do projeto, como
  `testDir`/`testMatch` do Playwright e
  `testpaths`/`python_files`/`norecursedirs` do pytest. Justificativas de
  redução vêm do índice, inclusive fora do hunk alterado; uma justificativa só
  no working tree não autoriza o snapshot staged. Semântica de assertions e
  tautologias exigem lint nativo ou `testing-patterns`.
- `check_lockfile_sync.py`, `lockfile_checks.py`, `staged_changes.py` e
  `workspace_members.py`: copie os quatro juntos para `scripts/`, porque o CLI
  `check_lockfile_sync.py` importa os outros três. O conjunto exige lockfile
  staged ou confirmação nativa de coerência, comprova pertencimento ao workspace
  e não executa atualizadores nem sincronizadores. Paridade staged sozinha não
  prova que o conteúdo do lockfile está correto; registre essa limitação.

### Passo 5: Verificação, Tratamento de Legado e Baseline

1. Confirme que todos os placeholders foram substituídos, que o comando de cada
   gate existe e que as ferramentas estão fixadas no contrato do projeto.
2. Instale e execute cada estágio configurado. Nos exemplos abaixo, execute
   pre-push somente quando ele fizer parte do contrato selecionado:
   ```bash
   pre-commit install
   pre-commit run --all-files
   pre-commit run --hook-stage pre-push --all-files
   # ou, se o runner escolhido for Lefthook:
   lefthook install
   lefthook run pre-commit
   lefthook run pre-push
   ```
   Use o prefixo fixado pelo projeto (`uv run --locked`, `pnpm exec` etc.)
   quando necessário. Evite invocação que baixe um runner não fixado.
3. No setup completo, prove pelo menos um `PASS` e um `FAIL` real em cada
   estágio configurado, usando um checkout de teste. Inclua um arquivo
   parcialmente staged, uma ferramenta ausente e um formatter que altera
   arquivos quando aplicáveis.
4. Para dívida pré-existente, use
   [baseline-recipes.md](references/baseline-recipes.md) e congele achados por
   identidade. Contagem total isolada não garante zero regressões: um achado
   novo pode substituir um antigo sem mudar o total.
5. Registre gates executados, `SKIP`s, duração e cobertura residual. Não declare
   completo um estágio que só foi configurado ou executado manualmente sem
   comprovar que o hook efetivo está instalado.
6. Compare a evidência com o roster oficial: escopo, opções, cobertura mínima e
   estágios. Checks diretos são execução manual; um check focado não prova
   aprovação de todos os gates. `pre-commit run --all-files` não executa
   `commit-msg` nem `pre-push`. Liste gates falhos ou não executados. Ausência
   de achados em scanners não prova ausência de vulnerabilidades; lint e testes
   de contrato não demonstram eficácia comportamental da skill. Nomeie modos
   como `--strict` somente quando as opções executadas os comprovarem.

## Correção Automática e Staging Seguro

### Ações Permitidas para Correção Automática

- Normalização de espaços em branco e quebras de linha (`trailing-whitespace`,
  `end-of-file-fixer`).
- Formatadores determinísticos da stack (`ruff format`, `prettier --write`,
  `gofmt`).
- Organização mecânica de imports (`isort`, `ruff check --select I --fix`).

### Ações Proibidas para Correção Automática

- Reescritas de lógica de negócio e correções automáticas de fluxo ou retorno
  sem permissão explícita no contrato do projeto e revisão antes de staging.
- Modificação, enfraquecimento ou deleção de asserções de testes.
- Adição de tipos `any`, `@ts-ignore`, `# type: ignore` ou `# noqa` para forçar
  aprovação.
- Migrations e comandos destrutivos de banco de dados.

### Protocolo de Staging Seguro

1. Quando um formatador alterar arquivos, o hook falha de forma visível
   notificando quais arquivos foram modificados.
2. O agente ou desenvolvedor revisa as mudanças geradas pelo auto-fix.
3. O agente adiciona ao estágio **apenas os arquivos modificados específicos**:
   ```bash
   git add -- <caminho_do_arquivo_1> <caminho_do_arquivo_2>
   ```
4. Proibido executar comandos amplos como `git add .` ou `git add -A` para
   evitar estagiar arquivos temporários ou alterações não relacionadas.
5. Re-executar o pre-commit para confirmar que o código formatado passa nos
   linters e verificadores estáticos.

## Formato de Diagnóstico Acionável

Quando um gate falhar, informe arquivo, linha quando aplicável, regra, motivo e
comando local para reprodução. No perfil estrito de `diff-sanity`, corrija o
código em vez de inserir uma supressão executável.

## Exemplos

### Exemplo 1: Setup Inicial em Projeto Python com `uv`

**Entrada**: Usuário pede: "Configura um pre-commit rápido no meu projeto Python
que usa ruff e pytest." **Ação do Agente**:

1. Inspeciona `pyproject.toml`, identifica `uv`, `ruff`, `pytest` e as regras
   locais; verifica se já há runner e hooks instalados.
2. Configura higiene e Ruff em pre-commit. Coloca a suíte de testes no estágio
   que seu custo medido comporta; adiciona o detector de ciclos se o projeto
   requerer grafo acíclico e os helpers Python somente se a política os pedir.
3. Instala os estágios declarados, executa pre-commit e pre-push quando
   configurado e prova um bloqueio real em checkout de teste.

### Exemplo 1b: Política de dependências em qualquer stack

**Entrada**: Usuário pede: "Adiciona um atualizador de dependências ao
pre-commit." **Ação do Agente**:

1. Identifique gerenciador, manifesto, lockfile e checks somente leitura.
2. Configure `[LOCKFILE]` com paridade staged ou confirmação nativa sem
   mutações. Consulte [stack-detection.md](references/stack-detection.md).
3. Sem check nativo seguro, mantenha paridade e informe a limitação; instalação,
   sincronização e atualização não são validação.
4. Reserve sincronização do ambiente para setup explícito fora do hook.

### Automação de atualização fora do hook

Quando o usuário pedir atualização automática, crie um script, job ou PR
explícito com resolução revisada, testes e auditoria. Caso contrário, documente
o comando deliberado de manutenção; não deduza CI, bots ou agendamentos.

### Exemplo 2: Projeto Legado com Dívida de Tipagem

**Entrada**: Usuário pede: "Quero colocar typecheck no pre-commit, mas o
repositório já tem 80 erros antigos de mypy." **Ação do Agente**:

1. Consulta [baseline-recipes.md](references/baseline-recipes.md).
2. Registra os 80 achados históricos por identidade estável e compara o conjunto
   atual ao baseline; um novo achado falha mesmo se outro desaparecer.
3. Se não houver ferramenta para comparar identidades, declara cobertura parcial
   e não promete zero regressões com um teto de 80 erros.

### Caso Negativo: Tentativa de Incluir Testes E2E Pesados no Pre-commit

**Entrada**: Usuário pede: "Coloca nossa suíte de testes Playwright E2E e o scan
completo de banco no pre-commit." **Ação do Agente**:

- **Por quê não**: Navegador e banco ativo acrescentam dependências de ambiente
  e latência desproporcionais ao commit local, incentivando contornar o hook.
- **Solução Correta**: O agente mede custo e dependências, mantém checks locais
  rápidos no pre-commit e escolhe pre-push ou CI para os testes pesados conforme
  o contrato do projeto.
