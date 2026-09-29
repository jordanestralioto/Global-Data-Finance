---
name: local-quality-gates
description: >-
  Use para criar, revisar ou reparar quality gates locais e hooks de pre-commit,
  commit-msg e pre-push em qualquer stack. Ative com pedidos como "configura os
  hooks Git", "cria um pre-push", "arruma meu pre-commit", "bloqueia debug no
  commit", "valida o lockfile", "limita linhas por arquivo", "limita
  complexidade no linter", "audita dependências no push", "divide testes entre
  commit e push" ou "adiciona um atualizador de dependências ao pre-commit". Cobre escolha de runner e estágio,
  segurança de auto-fix, baseline, validação do estado staged, instalação e
  teste dos hooks. Não use para pipeline remota, E2E de navegador, auditoria
  manual de segurança ou validação pesada de dados de produção.
---

# Local Quality Gates Architect

Build deterministic local gates whose cost fits the repository. Start with
focused checks, measure the cycle, and move expensive checks to pre-push or CI
when their latency harms the workflow or encourages bypasses.

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

______________________________________________________________________

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

Como regra normativa, `pre-commit` **não deve** executar resolvers,
updaters, installers ou sincronizadores que possam modificar o lockfile, o
manifesto, o ambiente do projeto ou a árvore de dependências. Isso inclui, por
exemplo, `uv lock --upgrade`, `uv sync --locked`, `poetry update`, `npm update`,
`pnpm update`, `yarn up`, `bun update`, `cargo update`, `go get -u` e
`composer update`. Só inclua um comando de gerenciador quando ele for uma
verificação somente leitura comprovada pelo próprio projeto; efeitos em cache
ou artefatos temporários são aceitáveis quando fazem parte desse contrato e o
custo observado cabe no hook.

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

O `diff-sanity` classifica a extensão do arquivo, não o diretório que o
contém. Em `.md`, `.markdown`, `.rst` e `.txt`, uma ocorrência de marcador de
supressão pode ser uma citação explicativa em prosa ou em um bloco de código
documental. Essa exceção também cobre Markdown em mudanças OpenSpec e arquivos
sob `tools/` ou projeções, desde que o formato seja documental.

Em qualquer outro formato textual, os mesmos marcadores são tratados como
supressão executável e bloqueados, mesmo dentro de uma string, docstring,
fixture, configuração ou manifesto. A análise de debuggers e stubs permanece
restrita a arquivos de código; a análise de operações perigosas permanece
universal e lê o texto bruto adicionado. Assim, o conteúdo explicativo não
permite transformar uma operação de bypass em uma exceção.

### Pre-push e CI

- **Pre-push**: Suítes de testes, typecheck do projeto e auditorias quando o
  tempo medido e as dependências locais forem adequados. Execute sobre o
  snapshot que será enviado ou identifique claramente quando o resultado
  cobre apenas o working tree. Scripts de diff staged não validam commits já
  feitos; não os reutilize como evidência de pre-push.
- **Testes por estágio**: `[TESTS_FAST]` no pre-commit só quando forem rápidos e
  cobrirem o escopo declarado; `[TESTS_FULL]` no pre-push executa a suíte local
  completa, sem usar apenas testes afetados como prova de cobertura total.
- **Auditoria de dependências**: Quando selecionada, use scanner fixado e
  somente leitura sobre dependências resolvidas; declare fonte, escopo,
  política de achados e indisponibilidade. Não confunda ausência de consulta
  com auditoria limpa. Consulte [gate-catalog.md](references/gate-catalog.md).
- **CI / Pipelines Remotas**: Testes E2E com navegador, integrações pesadas,
  builds e scans profundos que dependam de infraestrutura. Gates essenciais
  para aceitar mudanças precisam de proteção remota equivalente, pois hooks
  locais podem ser ignorados ou não instalados.

______________________________________________________________________

## Status de Execução e Política Fail-Closed

Os hooks e scripts devem seguir códigos de saída explícitos:

| Status  | Código | Significado                                                           | Comportamento                                                             |
| :------ | :----: | :-------------------------------------------------------------------- | :------------------------------------------------------------------------ |
| `PASS`  |  `0`   | O gate executou e validou seu snapshot declarado.                     | Permite a operação daquele estágio.                                       |
| `FAIL`  |  `1`   | Violação determinística encontrada.                                   | Bloqueia a operação; exibe motivo e reprodução.                           |
| `ERROR` |  `2`   | Falha de infraestrutura (erro no Git, ausência de ferramenta, crash). | Bloqueia a operação; não converte erro em sucesso.                        |
| `SKIP`  |  `0`   | Nenhuma entrada relevante segundo a política do gate.                 | Declara o motivo; não conta como gate executado em evidência obrigatória. |

______________________________________________________________________

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

______________________________________________________________________

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

______________________________________________________________________

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

______________________________________________________________________

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

**Entrada**: Usuário pede: "Adiciona um atualizador de dependências ao
pre-commit."
**Ação do Agente**:

1. Não adiciona um updater automaticamente. Primeiro identifica o gerenciador,
   o manifesto, o lockfile e se existe uma verificação nativa somente leitura.

2. Configura o `[LOCKFILE]` para exigir paridade staged ou confirmar coerência
   com um comando nativo somente leitura:

   | Stack                  | Verificação no hook                                                    | Atualização deliberada fora do hook            |
   | :--------------------- | :--------------------------------------------------------------------- | :--------------------------------------------- |
   | `uv`                   | `uv lock --check`                                                      | `uv lock --upgrade`                            |
   | Poetry                 | `poetry check --lock`                                                  | `poetry update`                                |
   | Cargo                  | `cargo check --locked`                                                 | `cargo update`                                 |
   | Go                     | `go mod tidy -diff` (se suportado)                                     | `go get -u` / `go mod tidy`                    |
   | npm, pnpm, Yarn ou Bun | paridade staged e comando imutável documentado pelo projeto, se houver | updater escolhido deliberadamente pelo projeto |

3. Se não houver comando nativo seguro para a stack, mantém o gate de paridade
   e registra a limitação. Não substitui a validação por `install`, `sync`,
   `update`, `upgrade`, `lock` ou `tidy` mutável.

4. Oferece o comando de sincronização do ambiente como setup explícito (por
   exemplo, `uv sync --locked`), sem colocá-lo no pre-commit por inferência.

### Automação de atualização fora do hook

Quando o usuário realmente pedir atualização automática, crie uma automação
separada do ciclo de commit: um script/manual job ou uma execução agendada que
abre uma branch/PR, roda o updater nativo da stack, testa a resolução e executa
as auditorias de segurança. O hook de `pre-commit` continua apenas validando o
estado staged. Se o usuário não pediu CI, bot ou job agendado, documente o
comando deliberado de atualização e não invente uma automação silenciosa.

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

______________________________________________________________________

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

______________________________________________________________________

## Evals de workflow

Execute os três cenários e as assertions binárias em
[eval-scenarios.md](references/eval-scenarios.md) antes de chamar uma mudança
de templates portátil entre stacks.

- [ ] Assert: `check_diff_sanity.py` falha com exit code 2 quando o git falha ou fora de um repo git.
- [ ] Assert: `check_diff_sanity.py` bloqueia `@ts-ignore`, `@ts-nocheck`, `@ts-expect-error` e `# type: ignore` em código e configuração com exit code 1, mesmo com uma razão, e aceita suas citações somente nos formatos documentais declarados.
- [ ] Assert: `check_diff_sanity.py` bloqueia `# noqa`, `# noqa: BLE001`, `# noqa: F401` com razão e `# noqa` acompanhado de `allow-bypass`, sempre com exit code 1.
- [ ] Assert: `check_diff_sanity.py` bloqueia `throw new Error("TODO")` mesmo quando acompanhado de comentário de debug.
- [ ] Assert: `check_test_integrity.py` bloqueia `.only` e `fit` sem exceção e bloqueia `skip` sem razão explícita.
- [ ] Assert: `check_test_integrity.py` bloqueia deleção de arquivos de teste a menos que autorizada em `.test-deletions.json` staged no git.
- [ ] Assert: `check_lockfile_sync.py` bloqueia manifesto filho sem lockfile local quando não comprovado o pertencimento aos membros do workspace raiz.
- [ ] Assert: `check_lockfile_sync.py` permite `package.json` sem dependências declaradas sem exigir lockfile.
- [ ] Assert: `check_lockfile_sync.py` aceita lockfile staged como paridade sem prometer coerência; sem update staged, exige confirmação nativa quando disponível. Ferramenta ausente ou falha ao executar retorna `ERROR` código 2; retorno não zero é `FAIL` código 1.
- [ ] Assert: `check_lockfile_sync.py` reconhece `bun.lock` e bloqueia uma verificação nativa do working tree quando manifesto ou lockfile diverge do index.
- [ ] Assert: O agente separa validação do lockfile, sincronização do ambiente e atualização de dependências; não adiciona updater ou sincronizador mutável ao pre-commit por inferência.
- [ ] Assert: Para uma stack sem verificação nativa somente leitura, o agente mantém a exigência de paridade staged e não inventa um comando de instalação, atualização ou resolução.
- [ ] Assert: O agente não classifica `go mod verify` como coerência de `go.mod`/`go.sum`; quando suportado, usa `go mod tidy -diff` ou mantém a paridade staged.
- [ ] Assert: Uma atualização automática solicitada é colocada em script/job/PR separado, e o pre-commit permanece sem mutações no manifesto, lockfile ou ambiente.
- [ ] Assert: `[DEPENDENCY_AUDIT]` declara grafo inspecionado, política de achados e indisponibilidade; falta de consulta não vira auditoria limpa.
- [ ] Assert: `[TESTS_FAST]` não substitui `[TESTS_FULL]`; o relatório distingue testes afetados, suíte completa e snapshot validado.
- [ ] Assert: Quando o projeto exige grafo acíclico, `[CIRCULAR_DEPENDENCIES]` bloqueia ciclo novo; ausência de comando é `UNSUPPORTED`, não `PASS`.
- [ ] Assert: Um `[LINTER]` estrutural selecionado registra complexidade, aninhamento, fluxo, erros e tamanho de rotina com regra, limite, escopo e status.
- [ ] Assert: `[FILE_LINES]` seleciona `tools/check-max-lines` só quando limites, classificação, exclusões e runtime forem compatíveis; declara cobertura do working tree ou do index conforme o runner.
- [ ] Assert: Complexidades ciclomática e cognitiva permanecem distintas; cobertura bloqueante indisponível não é declarada `PASS`.
- [ ] Assert: Structural configuration never uses a generic diff regex, treats physical lines as executable statements, or enforces a blanket single-exit rule.
- [ ] Assert: Broad catches are accepted only at explicit boundaries with a narrow scope, defined handling, and preserved cause.
- [ ] Assert: Assertion vacuum and tautologies remain under `[TEST_INTEGRITY]` and `testing-patterns`, not `[LINTER]`.
- [ ] Assert: Os dois templates incluem pre-push ativo, exigem substituir o comando do projeto e instruem instalação e teste de falha do estágio.
- [ ] Assert: Em três cenários (Python com runner existente, monorepo Node e Go/Rust sem runner), o agente registra estágio, snapshot, runtime e cobertura, instala cada hook declarado e prova ao menos um bloqueio real.
- [ ] Assert: Um baseline com `{A, B}` não aceita `{B, C}` como zero regressões.
