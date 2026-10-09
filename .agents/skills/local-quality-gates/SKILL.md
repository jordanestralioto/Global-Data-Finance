---
name: local-quality-gates
description: >-
  Use para criar, revisar ou reparar quality gates locais e hooks de pre-commit,
  commit-msg e pre-push em qualquer stack. Ative com pedidos como "configura os
  hooks Git", "cria um pre-push", "arruma meu pre-commit", "bloqueia debug no
  commit", "valida o lockfile", "limita linhas por arquivo", "limita
  complexidade no linter", "audita dependências no push", "divide testes entre
  commit e push", "bloqueia código morto antes do commit" ou "adiciona um
  atualizador de dependências ao pre-commit". Cobre escolha de runner e estágio,
  segurança de auto-fix, baseline, validação do estado staged, instalação e
  teste dos hooks. Não use para pipeline remota, E2E de navegador, auditoria
  manual de segurança, remoção de código obsoleto da aplicação sem configurar
  gates ou validação pesada de dados de produção.
---

# Local Quality Gates Architect

Build deterministic local gates, measure their cost, and choose commit,
push, or delegated enforcement from the project contract.

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

## Catálogo de gates locais

### Slots possíveis no pre-commit

01. **Repository Hygiene**: Whitespace, nova linha final, marcadores de conflito e limite de tamanho em bytes definido pelo projeto.
02. **Safe Mechanical Auto-Fix**: Formatação padronizada e organização de imports (executada com staging explícito).
03. **Syntax / Fast Static**: Compilação/interpretação de arquivos alterados (`py_compile`, `tsc --noEmit`, `go vet`).
04. **Secret Scanning**: Detecção de credenciais no diff staged com um scanner fixado, como o hook oficial do Gitleaks ou `gitleaks git --pre-commit --staged --redact`.
05. **Diff Sanity (perfil estrito)**: Bloqueio de debuggers (`console.log`, `breakpoint()`), stubs (`throw new Error("TODO")`, `pass  # TODO`) e supressões (`@ts-ignore`, `@ts-nocheck`, `@ts-expect-error`, `# type: ignore`, `# noqa` e equivalentes). Ao selecionar esse perfil, documente suas exceções e confirme que o projeto aceita essa política: essas construções podem ser legítimas em outros contextos. Arquivos `.md`, `.markdown`, `.rst` e `.txt` podem citar os marcadores como conteúdo explicativo; os formatos executáveis e de configuração seguem a política estrita.
    - **Operational Text Safety**: O mesmo gate inspeciona o texto adicionado em qualquer formato textual, sem exceções por diretório. Pipelines que enviam downloads diretamente a um shell, comandos que desativam hooks, variáveis de ambiente que saltam hooks, configurações que continuam após erro e fallbacks shell que forçam sucesso são violações, inclusive quando aparecem em documentação ou projeções geradas.
06. **Test Integrity (perfil estrito)**: Bloqueio de testes focados (`.only`, `fit`, `fdescribe`), skips sem razão, perda líquida de asserções e deleções sem política staged. Ajuste os marcadores e a política ao framework do projeto.
07. **Monorepo-Safe Lockfile Validation**: Em projeto com lockfile autoritativo, exija que manifesto modificado tenha lockfile correspondente no diff staged ou uma verificação nativa somente leitura que confirme coerência. Confirme membros de workspace; `package.json` sem dependências pode não exigir lockfile. Uma ferramenta ausente para um check nativo declarado é `ERROR` (código 2); lockfile ausente ou check que retorna não zero é `FAIL` (código 1).
08. **Circular Imports / Dependencies**: Quando o projeto requer arquitetura acíclica, valide ciclos diretos e indiretos no grafo afetado. Um ciclo novo falha; ciclos históricos exigem baseline por identidade. Use compilador ou analisador existente. Se o gate bloqueante foi pedido e nenhuma ferramenta determinística o cobre, registre `UNSUPPORTED` e deixe a configuração desse gate incompleta.
09. **Structural Linting**: Quando selecionado, use linter com parser para
    complexidade, aninhamento, simplificação de fluxo, erros e tamanho de
    rotinas. Registre as regras e os limiares definidos pelo projeto; não
    simule análise de AST com regexes no diff.
10. **File Line Limits**: Quando o projeto exigir limite de linhas por arquivo,
    use o componente `tools/check-max-lines` se seus limites, classificação e
    exclusões fixas forem compatíveis com a política local. O gate mede linhas
    físicas dos arquivos elegíveis rastreados; não substitui limite em bytes
    nem análise de rotinas por AST.
11. **Dead Code**: Assess `[DEAD_CODE]` in every setup or review. Record each
    capability and its actual coverage; selected blocking rules require
    automatic enforcement. Review obsolete compatibility contracts separately.
    Read [dead-code-policy.md](references/dead-code-policy.md).

### Política transversal de dependências (todas as stacks)

O agente deve separar três operações que frequentemente recebem o mesmo nome
de “sincronizar dependências”:

1. **Validar o lockfile**: verificar, sem reescrever o manifesto, o lockfile ou
   as dependências declaradas, que os arquivos são coerentes. A ferramenta pode
   consultar a rede, caches ou diretórios de build se isso fizer parte do seu
   contrato, mas não pode persistir alterações nos arquivos rastreados, instalar
   pacotes no ambiente do projeto ou persistir uma nova resolução. Esta é a
   única operação de dependências que o `[LOCKFILE]` deve executar no
   `pre-commit`.
2. **Sincronizar o ambiente**: instalar o que já está fixado no lockfile em
   `.venv`, `node_modules` ou equivalente. É uma ação de bootstrap/setup; não
   deve ser adicionada ao `pre-commit` por inferência. Por exemplo,
   `uv sync --locked` valida o lockfile e pode modificar `.venv`, mas não
   atualiza as versões resolvidas.
3. **Atualizar ou resolver dependências**: escolher novas versões ou reescrever
   o lockfile. É uma alteração deliberada, que precisa ser revisada, testada e
   auditada fora do hook de commit.

Keep resolvers, updaters, installers, and environment synchronization outside
`pre-commit`. See [stack-detection.md](references/stack-detection.md#11-dependency-lifecycle-classification).
Accept only verified read-only commands; cache/build effects require a declared
contract and measured cost that fits the hook.

Um prefixo usado apenas para invocar uma ferramenta já fixada do gate, como
`uv run --locked`, não é um updater por si só. Mantenha-o somente quando fizer
parte do contrato existente do projeto; se a execução puder sincronizar o
ambiente implicitamente, considere `--no-sync` depois que o setup local já
estiver concluído.

Se a stack não fornecer uma verificação nativa somente leitura, exija a
paridade staged entre manifesto e lockfile usando o gate compartilhado; não
invente um comando de atualização para preencher a lacuna. Se o projeto
declarar uma verificação nativa, mas a ferramenta não puder ser iniciada, o
resultado é `ERROR`, código 2, conforme a política fail-closed.

### Fronteira entre documentação e supressão executável

Classify suppression citations by extension, not directory. `.md`, `.markdown`,
`.rst`, and `.txt` permit explanatory citations, including documentary code
blocks, OpenSpec, tools, and projections. Other textual formats reject markers
in strings, docstrings, fixtures, configuration, and manifests. Debug/stub scans
cover code; operational safety scans raw added text in every textual format.
Documentation never authorizes an operational bypass. Read
[agent-anti-patterns.md](references/agent-anti-patterns.md).

### Pre-push e CI

- **Pre-push**: Run suites, typechecks, and audits according to measured cost
  and the project contract. Identify pushed commits/refspecs or residual
  working-tree coverage. Staged-diff helpers do not prove push coverage.
- **Tests by stage**: `[TESTS_FAST]` has a bounded commit scope and cost;
  `[TESTS_FULL]` runs the complete local push tier, not just affected tests.
- **Dependency audit**: A pinned read-only scanner records source, graph,
  findings policy, and unavailability. Missing consultation is not a clean
  audit. Read [gate-catalog.md](references/gate-catalog.md).
- **CI**: Assign E2E, integrations, and infrastructure scans under the remote
  contract. Essential gates need equivalent remote protection because local
  hooks can be bypassed or absent.

## Status de Execução e Política Fail-Closed

Os hooks e scripts devem seguir códigos de saída explícitos:

| Status  | Código | Significado                                                           | Comportamento                                                             |
| :------ | :----: | :-------------------------------------------------------------------- | :------------------------------------------------------------------------ |
| `PASS`  |  `0`   | O gate executou e validou seu snapshot declarado.                     | Permite a operação daquele estágio.                                       |
| `FAIL`  |  `1`   | Violação determinística encontrada.                                   | Bloqueia a operação; exibe motivo e reprodução.                           |
| `ERROR` |  `2`   | Falha de infraestrutura (erro no Git, ausência de ferramenta, crash). | Bloqueia a operação; não converte erro em sucesso.                        |
| `SKIP`  |  `0`   | Nenhuma entrada relevante segundo a política do gate.                 | Declara o motivo; não conta como gate executado em evidência obrigatória. |

These are normalized outcomes. Preserve native analyzer exit codes and map
their documented semantics and severity before classification; see
[dead-code-policy.md](references/dead-code-policy.md#5-native-outcomes-and-evidence).

## Procedimento

### Passo 1: Inspecionar o Workspace e Identificar a Stack

1. Inspecione a raiz e subpastas do workspace em busca de manifestos (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `composer.json`).
2. Identifique o gerenciador de pacotes e o prefixo de execução do projeto (ex: `uv run`, `pnpm exec`, `cargo`).
   Classifique também cada comando encontrado como **validação do lockfile**,
   **sincronização do ambiente** ou **atualização/resolução**. Em projetos `uv`,
   siga o comando oficial e verifique se `uv run --locked` sincroniza o ambiente;
   use `--no-sync` só após setup confirmado. Reserve `uv sync --locked` para
   setup e `uv lock --upgrade` para manutenção deliberada. Nunca deduza um
   updater da presença de manifesto e lockfile.
3. Consulte [stack-detection.md](references/stack-detection.md) para mapear linters, formatters, typecheckers e runners já configurados.
4. Inspecione se já existe runner configurado (`.pre-commit-config.yaml`,
   `.husky/`, `lefthook.yml` ou scripts em `.git/hooks/`), se os hooks estão
   instalados e se `core.hooksPath` altera o local efetivo. Identifique o
   runtime disponível para qualquer helper local.
5. Determine a entrada de cada estágio: index no pre-commit, mensagem no
   commit-msg e commits/refspecs no pre-push. Um check de projeto que lê o
   working tree deve tratar alterações não staged como outro snapshot.

### Passo 2: Gap Analysis e Mapeamento de Slots

Compare o estado atual com a matriz de slots conceituais 80/20 (detalhada em [gate-catalog.md](references/gate-catalog.md)):

- `[HYGIENE]`: Espaços no final de linha, nova linha final, marcadores de conflito e limite de tamanho acordado.
- `[FILE_LINES]`: Limite de linhas por arquivo com ferramenta nativa ou
  `tools/check-max-lines` quando o projeto consumir o harness e aceitar seus
  limites de 400/1000/500 linhas para produção/testes/documentação, além da
  classificação e das exclusões do componente.
- `[SYNTAX]`: Compilação/interpretação básica (`py_compile`, `tsc --noEmit`, `go vet`).
- `[FORMATTER]`: Formatação padronizada como auto-fix mecânico seguro (`ruff format`, `prettier`).
- `[LINTER]`: Code quality plus parser-aware structural checks for complexity,
  nesting, flow simplification, error handling, and routine scope.
- `[DEAD_CODE]`: Assess all seven capabilities and their coverage statuses in
  [dead-code-policy.md](references/dead-code-policy.md#1-capability-report).
  A lint pass does not establish full coverage or approve compatibility APIs.
- `[SECRETS]`: Varredura de credenciais no diff staged (hook oficial do Gitleaks ou comando atual fixado).
- `[CONFIG]`: Validação de sintaxe JSON, YAML e TOML.
- `[CIRCULAR_DEPENDENCIES]`: Detecção de ciclos quando o projeto exige grafo acíclico; ciclos históricos usam baseline por identidade.
- `[DIFF_SANITY]`: Interceptação de debuggers, stubs e bypasses recém-criados.
- `[LOCKFILE]`: Validação somente leitura da paridade entre manifesto modificado e lockfile (validando pertencimento a workspaces); nunca atualização automática de dependências.
- `[TEST_INTEGRITY]`: Alerta contra testes com `.only`, `skip`, perda de asserções ou arquivos deletados.
- `[TESTS_FAST]`: Subconjunto rápido e definido de testes no pre-commit, com cobertura residual declarada.
- `[TESTS_FULL]`: Suíte local completa no pre-push ou delegação explícita para CI.
- `[DEPENDENCY_AUDIT]`: Vulnerabilidades conhecidas nas dependências resolvidas; gate separado de `[LOCKFILE]`.

Registre a decisão em uma matriz com colunas `gate`, `estágio`, `comando/versão`,
`snapshot`, `efeito`, `duração observada`, `status` e `justificativa`. Inclua
slots omitidos quando a ausência poderia ser confundida com cobertura.

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

01. Se o projeto já utiliza um runner, adapte a configuração existente sem remover regras de negócio válidas.
02. Sem runner, escolha um que a equipe possa instalar e manter com as
    ferramentas já adotadas. Use [.pre-commit-config.yaml](assets/templates/pre-commit-config.yaml.template)
    ou [lefthook.yml](assets/templates/lefthook.yml.template) como scaffold,
    não como configuração pronta: preencha comandos, congele versões e remova
    exemplos não selecionados. A escolha não depende só da linguagem.
03. Isole o escopo em monorepos ou projetos multi-stack usando regex de caminhos, conforme [multi-stack-patterns.md](references/multi-stack-patterns.md).
04. Configure `[LINTER]` with the project's existing parser-aware rules.
    Prefer read-only structural diagnostics. If the project's explicit
    contract allows the tool's safe fixes for flow or return rules, preserve
    that policy and require review before staging. Never enable unsafe fixes
    or automatic business-logic rewrites. Do not enforce a blanket single-exit
    rule; guard clauses are useful only when they make preconditions and the
    main path clearer.
05. Configure `[CIRCULAR_DEPENDENCIES]` quando requerido. Se a ferramenta
    aceitar escopo, execute o grafo afetado; não substitua uma exigência do
    projeto por `SKIP`. Registre ciclos históricos por identidade.
06. Configure `[LOCKFILE]` em projetos com lockfile autoritativo como um gate
    de validação. Exija o lockfile correspondente no diff staged ou use o comando
    nativo somente quando ele comprovar coerência sem persistir uma nova
    resolução, reescrever manifestos/lockfiles ou instalar dependências. Para stacks sem
    esse comando, mantenha a exigência de paridade e registre a limitação; nunca
    substitua o gate por comandos
    mutáveis como `install`, `sync`, `update`, `upgrade`, `lock` ou `tidy`.
    Comandos explicitamente somente leitura, como `uv lock --check`,
    `poetry check --lock`, `cargo check --locked` e `go mod tidy -diff` (quando
    suportado), são exceções autorizadas. `go mod verify` verifica a integridade
    do cache de módulos e não a coerência entre `go.mod` e `go.sum`; trate-o como
    auditoria de integridade separada, nunca como substituto do `[LOCKFILE]`.
07. For each remote hook repository, resolve a release and freeze
    `rev` to a 40-character commit SHA before declaring the generated
    configuration ready. Preserve the release in a comment for maintenance;
    do not leave mutable tags in durable project configuration.
08. When a hook uses `additional_dependencies`, resolve and pin the compatible
    group as a unit. Update the base package and its plugins together, validate
    the resolution, and only then record exact pins.
09. Classifique projeções geradas (`.agents/`, `.claude/`, `.codex/`, mirrors e
    artefatos equivalentes) antes de atribuir hooks. Hooks auto-fixáveis e
    corretores lexicais (`end-of-file-fixer`, `ruff --fix`, formatadores e
    `codespell`) devem declarar `exclude` local para esses caminhos quando eles
    puderem estar rastreados. Mantenha scanners de segurança e validações
    semânticas no escopo apropriado e, quando a projeção precisar ser validada,
    use um gate dedicado somente leitura. Corrija sempre a fonte canônica e
    regenere a projeção; não corrija o espelho diretamente.
10. Quando pre-push fizer parte do pedido ou contrato do projeto, substitua o
    placeholder pelo gate escolhido, declare `stages: [pre-push]` ou
    `pre-push:` e instale esse estágio. Fora desse escopo, remova o placeholder
    e o estágio do scaffold. Se o working tree estiver sujo, teste os commits
    em checkout isolado quando a garantia for sobre o push; caso contrário,
    reporte que o resultado cobre o working tree, não o snapshot enviado.
11. Para `[FILE_LINES]` em um consumidor do harness, selecione
    `"check-max-lines"` em `components.tools` de `.agents/harness.json`, rode
    `harness-sync` e configure a tool projetada (`tools/check-max-lines`) sem
    filenames. Confirme Python 3.13+, limites e escopo compatíveis; o gate lê o
    working tree. Só declare cobertura staged se o runner isolar alterações
    não staged. Veja [gate-catalog.md](references/gate-catalog.md).
12. For `[DEAD_CODE]`, follow the selection, snapshot, review, and native-outcome
    contracts in [dead-code-policy.md](references/dead-code-policy.md). Use the
    optional template entry with a pinned project-native analyzer; analyze the
    complete declared scope, including deletions and configuration changes.
    Required commit coverage needs index isolation or rejection of divergent
    inputs, including untracked consumers. Working-tree coverage remains partial.
    Measure placement and prove blocking behavior; keep execution read-only.

### Passo 4: Instalar Scripts Auxiliares de Sanidade de IA

Quando o projeto seleciona estes helpers e dispõe de Python 3.10+, copie
ou referencie apenas os helpers necessários na pasta `scripts/` do projeto.
Eles usam a biblioteca padrão, mas exigem o runtime Python; não os instale por
inferência em qualquer stack:

- `check_diff_sanity.py`: Bloqueia `console.log`, `breakpoint()`, `print` órfão, `throw new Error("TODO")`, supressões de compilador/linter e operações perigosas recém-adicionadas. Marcadores de supressão são bloqueados em todos os formatos não documentais, inclusive com justificativa; os formatos `.md`, `.markdown`, `.rst` e `.txt` permitem somente a citação não executável. Para uma CLI que precisa emitir saída com `print()`, configure cada arquivo explicitamente com `--allow-print-file <path>` no hook; não isente um diretório inteiro. Structural complexity and nesting remain outside this staged-text scanner. Consulte [agent-anti-patterns.md](references/agent-anti-patterns.md).
- `check_test_integrity.py`: Bloqueia `.only`/`fit` sem exceção, bloqueia skips e perda de asserções sem razão e exige policy staged em `.test-deletions.json` para deleção de testes. It does not prove assertion meaning across every framework; use native test lint or `testing-patterns` for assertion vacuum and tautologies.
- `check_lockfile_sync.py`, `lockfile_checks.py`, `staged_changes.py` e `workspace_members.py`: Copie os quatro arquivos juntos para `scripts/`; o primeiro é o CLI, o segundo centraliza a leitura de manifests e as verificações nativas de coerência, o terceiro preserva relações de rename/copy no índice e o quarto fornece a leitura indexada e o matching conservador de membros. O conjunto exige lockfile staged ou confirmação nativa de coerência e comprova pertencimento ao workspace. Paridade staged sozinha não prova que o conteúdo do lockfile está correto; registre essa limitação. O CLI deve analisar o conteúdo staged de `package.json`, dispensar manifests sem dependências declaradas e recusar confirmação nativa quando arquivos relevantes divergem do index. Ele não executa atualizadores ou sincronizadores de ambiente.

### Passo 5: Verificação, Tratamento de Legado e Baseline

1. Confirme que todos os placeholders foram substituídos, que o comando de
   cada gate existe e que as ferramentas estão fixadas no contrato do projeto.
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
3. Em um checkout de teste, prove pelo menos um `PASS` e um `FAIL` real em
   cada estágio configurado. Inclua um arquivo parcialmente staged, uma
   ferramenta ausente e um formatter que altera arquivos quando aplicáveis.
4. Para dívida pré-existente, use [baseline-recipes.md](references/baseline-recipes.md)
   e congele achados por identidade. Contagem total isolada não garante zero
   regressões: um achado novo pode substituir um antigo sem mudar o total.
5. Registre gates executados, `SKIP`s, duração e cobertura residual. Não
   declare completo um estágio que só foi configurado ou executado manualmente
   sem comprovar que o hook efetivo está instalado.

## Auto-Fix Policy e Staging Seguro

### Ações Permitidas para Correção Automática

- Normalização de espaços em branco e quebras de linha (`trailing-whitespace`, `end-of-file-fixer`).
- Formatadores determinísticos da stack (`ruff format`, `prettier --write`, `gofmt`).
- Organização mecânica de imports (`isort`, `ruff check --select I --fix`).

### Ações Proibidas para Correção Automática

- Reescritas de lógica de negócio e correções automáticas de fluxo ou retorno
  sem permissão explícita no contrato do projeto e revisão antes de staging.
- Modificação, enfraquecimento ou deleção de asserções de testes.
- Adição de tipos `any`, `@ts-ignore`, `# type: ignore` ou `# noqa` para forçar aprovação.
- Migrations e comandos destrutivos de banco de dados.

### Protocolo de Staging Seguro

1. Quando um formatador alterar arquivos, o hook falha de forma visível notificando quais arquivos foram modificados.
2. O agente ou desenvolvedor revisa as mudanças geradas pelo auto-fix.
3. O agente adiciona ao estágio **apenas os arquivos modificados específicos**:
   ```bash
   git add -- <caminho_do_arquivo_1> <caminho_do_arquivo_2>
   ```
4. Proibido executar comandos amplos como `git add .` ou `git add -A` para evitar estagiar arquivos temporários ou alterações não relacionadas.
5. Re-executar o pre-commit para confirmar que o código formatado passa nos linters e verificadores estáticos.

## Formato de Diagnóstico Acionável

Quando um gate falhar, o diagnóstico deve conter arquivo, linha quando
aplicável, motivo e comando local para reprodução. No perfil estrito de
`diff-sanity`, corrija o código em vez de inserir uma supressão executável:

```text
======================================================================
FAIL [DIFF_SANITY]: Potential AI agent artifacts detected in staged diff:
  • src/services/auth.ts:42: [DEBUG] console.log/debug statement detected
  • src/services/auth.ts:89: [BYPASS] TypeScript check bypass (@ts-ignore) added

Suggested command:
pnpm eslint src/services/auth.ts
======================================================================
```

## Exemplos

### Exemplo 1: Setup Inicial em Projeto Python com `uv`

**Entrada**: Usuário pede: "Configura um pre-commit rápido no meu projeto Python que usa ruff e pytest."
**Ação do Agente**:

1. Inspeciona `pyproject.toml`, identifica `uv`, `ruff`, `pytest` e as regras
   locais; verifica se já há runner e hooks instalados.
2. Configura higiene e Ruff em pre-commit. Coloca a suíte de testes no estágio
   que seu custo medido comporta; adiciona o detector de ciclos se o projeto
   requerer grafo acíclico e os helpers Python somente se a política os pedir.
3. Instala os estágios declarados, executa pre-commit e pre-push quando
   configurado e prova um bloqueio real em checkout de teste.

### Exemplo 1b: Política de dependências em qualquer stack

**Entrada**: Usuário pede: "Adiciona um atualizador de dependências ao pre-commit."
**Ação do Agente**:

1. Identify the manager, manifest, lockfile, and read-only checks.
2. Configure `[LOCKFILE]` with staged parity or native confirmation without
   mutations. Read [stack-detection.md](references/stack-detection.md).
3. Without a safe native check, retain parity and report the limitation;
   installation, synchronization, updates, and resolution are not validation.
4. Reserve environment synchronization for explicit setup outside the hook.

### Automação de atualização fora do hook

When automatic updates are requested, create an explicit script/job/PR with
native updates, reviewed resolution, tests, and auditing. Otherwise document
the deliberate maintenance command; do not infer CI, bots, or scheduled jobs.

### Exemplo 2: Projeto Legado com Dívida de Tipagem

**Entrada**: Usuário pede: "Quero colocar typecheck no pre-commit, mas o repositório já tem 80 erros antigos de mypy."
**Ação do Agente**:

1. Consulta [baseline-recipes.md](references/baseline-recipes.md).
2. Registra os 80 achados históricos por identidade estável e compara o
   conjunto atual ao baseline; um novo achado falha mesmo se outro desaparecer.
3. Se não houver ferramenta para comparar identidades, declara cobertura
   parcial e não promete zero regressões com um teto de 80 erros.

### Caso Negativo: Tentativa de Incluir Testes E2E Pesados no Pre-commit

**Entrada**: Usuário pede: "Coloca nossa suíte de testes Playwright E2E e o scan completo de banco no pre-commit."
**Ação do Agente**:

- **Por quê não**: Browser and live database workloads add environment and latency requirements that are disproportionate to a local commit gate. They can block the workflow and encourage the use of `--no-verify`.
- **Solução Correta**: O agente mede custo e dependências, mantém checks locais
  rápidos no pre-commit e escolhe pre-push ou CI para os testes pesados conforme
  o contrato do projeto.

## Evals de trigger

### Deve acionar

- "Cria uma configuração de pre-commit para este projeto."
- "Configura um pre-push que rode os testes antes de enviar a branch."
- "O arquivo de hooks existe, mas o git push não roda nada."
- "Adiciona quality gates locais para impedir que a IA commite debugs e console.log."
- "Arruma os hooks do git que estão falhando no commit."
- "Configura pre-commit com ruff, prettier e gitleaks."
- "Adiciona checagem de lockfile e integridade de testes no commit."
- "Adiciona um atualizador de dependências ao pre-commit." → Acionar a
  política de lifecycle: configurar validação de lockfile e explicar por que
  o updater deve ser uma automação deliberada fora do hook.
- "Bloqueia imports circulares antes do commit."
- "Bloqueia código morto antes do commit."
- "Revisa se nossos hooks detectam exports e arquivos sem uso."
- "Configura o linter para bloquear funções complexas e aninhamento profundo."
- "Bloqueia arquivos com mais de 400 linhas no pre-commit."
- "Adiciona gates para catch-all, handlers vazios e funções longas."
- "Distribui testes rápidos no commit e completos no push; audita as dependências."

### Não deve acionar

- "Cria uma pipeline de CI no GitHub Actions para deploy em produção." → Encaminhar para arquitetura/CI.
- "Escreve testes E2E com Playwright para o fluxo de checkout." → Encaminhar para `webapp-testing`.
- "Audita a segurança da API contra vulnerabilidades OWASP." → Encaminhar para `vulnerability-scanner`.
- "Refatora essa função que está muito longa." → Encaminhar para `modularizar`.
- "Essa assertion realmente prova a regressão?" → Encaminhar para `testing-patterns`.
- "Remove esse alias obsoleto da aplicação." → Review consumers and contracts
  in the application; no hook configuration was requested.
- "Apaga as funções sem uso deste módulo." → Application cleanup with reviewed
  removals; do not infer a gate setup.

## Evals de workflow

Execute os três cenários e as assertions binárias em
[eval-scenarios.md](references/eval-scenarios.md) antes de chamar uma mudança
de templates portátil entre stacks.

Retain the existing regression assertions when extending those evaluations.
