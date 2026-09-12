---
name: local-quality-gates
description: >-
  Use para criar, inspecionar, reparar ou atualizar sistemas de quality gates
  locais e hooks de pre-commit e pre-push em qualquer stack. Ative quando o
  usuário pedir "cria um pre-commit", "configura quality gates locais", "arruma
  meu pre-commit", "adiciona validação de commit", "configura hooks git", "bloqueia
  debug no commit", "adiciona um atualizador
  de dependências ao pre-commit" ou "separa atualização de dependências dos
  hooks". Cobre integridade de repositório, sintaxe, auto-fix seguro, linter,
  typecheck com baseline, dependências circulares, secret scanning, sanidade de
  diff, integridade de testes, paridade de lockfiles e a separação entre
  validação, sincronização de ambiente e atualização de dependências. Ative
  também para limitar complexidade, aninhamento, funções longas e captura ampla
  de erros nos hooks locais. Não use
  para pipelines de CI/CD em nuvem, testes E2E lentos de navegador, validação
  pesada de dados de produção ou auditoria manual de segurança.
---

# Local Quality Gates & Pre-commit Architect

This skill guides agents to build, audit, and maintain deterministic local quality gates. The goal is a predictable first line of defense whose cost fits the repository and the developer workflow: start with focused checks, measure the actual cycle, and keep broader checks in pre-commit when the project explicitly accepts their cost. Move expensive checks to pre-push or CI only when their latency harms the workflow or encourages `--no-verify`.

______________________________________________________________________

## Princípios de Design 80/20 e Escopo do MVP

### O que o MVP Suporta Localmente (Pre-commit)

1. **Repository Hygiene**: Whitespace, nova linha final, marcadores de conflito, arquivos > 500KB.
2. **Safe Mechanical Auto-Fix**: Formatação padronizada e organização de imports (executada com staging explícito).
3. **Syntax / Fast Static**: Compilação/interpretação de arquivos alterados (`py_compile`, `tsc --noEmit`, `go vet`).
4. **Secret Scanning**: Detecção de chaves de API e credenciais no diff staged (`gitleaks protect --staged`).
5. **Diff Sanity (AI Traps)**: Bloqueio estrito por padrão de debuggers (`console.log`, `breakpoint()`), stubs (`throw new Error("TODO")`, `pass  # TODO`) e supressões de compilador/linter em código ou configuração (`@ts-ignore`, `@ts-nocheck`, `@ts-expect-error`, `# type: ignore`, `# noqa` e equivalentes). Arquivos `.md`, `.markdown`, `.rst` e `.txt` podem citar esses marcadores como conteúdo explicativo, inclusive em blocos de código documental; a citação não é executável. Os marcadores continuam proibidos em código, scripts, fixtures, docstrings, YAML, JSON, TOML, manifests e workflows.
   - **Operational Text Safety**: O mesmo gate inspeciona o texto adicionado em qualquer formato textual, sem exceções por diretório. Pipelines que enviam downloads diretamente a um shell, comandos que desativam hooks, variáveis de ambiente que saltam hooks, configurações que continuam após erro e fallbacks shell que forçam sucesso são violações, inclusive quando aparecem em documentação ou projeções geradas.
6. **Test Integrity**: Bloqueio sem exceção de testes focados (`.only`, `fit`, `fdescribe`), bloqueio por padrão de skips (`@pytest.mark.skip`, `it.skip` — exigem razão com `allow-skip: <reason>`), perda líquida de asserções (`allow-assertion-reduction: <reason>`) e deleções de arquivos de teste (exigem política staged em `.test-deletions.json` com razão por arquivo ou `--allow-deleted-tests`).
7. **Monorepo-Safe Lockfile Validation**: Garantia de que cada manifesto modificado (`pyproject.toml`, `package.json`, etc.) tenha seu lockfile local atualizado, ou o lockfile da raiz caso o manifesto pertença comprovadamente aos membros declarados de um workspace compartilhado na raiz. Para `package.json`, um arquivo que só contém metadados e não declara dependências não exige lockfile. Quando o gerenciador local fornece uma verificação determinística de coerência (`uv lock --check`, `poetry check --lock`, `cargo check --locked` ou uma verificação Go explicitamente configurada, como `go mod tidy -diff` quando suportada pela versão do projeto), um lockfile existente e confirmado como coerente também satisfaz o gate; ausência da ferramenta ou falha ao iniciar/executar o subprocesso é erro de infraestrutura (`ERROR`, código 2), enquanto lockfile ausente ou comando nativo retornando não zero continua sendo violação (`FAIL`, código 1). Este gate valida o estado existente; não atualiza dependências.
8. **Circular Imports / Dependencies (obrigatório)**: Todo projeto com código importável deve ter um gate explícito no pre-commit para detectar ciclos diretos e indiretos (`A → B → A` e `A → B → C → A`) no grafo afetado. Um ciclo novo falha; ciclos históricos somente podem ser mantidos por baseline não-crescente. A ausência de uma ferramenta dedicada não autoriza remover o gate: reutilize o compilador, o analisador arquitetural ou o comando de dependências que o projeto já possui e, se não houver nenhum mecanismo determinístico disponível, interrompa a configuração com `ERROR` em vez de declarar `PASS`.
9. **Structural Linting**: Require parser-aware `[LINTER]` coverage for
   complexity, nesting, flow simplification, error handling, and routine
   scope. Use project-native rules and explicit thresholds; never imitate AST
   analysis with staged-text regexes.

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

### O que Pertence ao Pre-push e CI (Fora do Pre-commit)

- **Pre-push**: Suítes completas de testes unitários, typecheck do branch inteiro e auditorias de dependências (`pip-audit`, `npm audit`) when the repository's workflow places them there.
- **CI / Pipelines Remotas**: Testes E2E com navegador (Playwright/Cypress), testes de integração pesados, Docker builds, scans SAST profundos, validações em bancos analíticos e migrações live contra bancos reais.

______________________________________________________________________

## Status de Execução e Política Fail-Closed

Os hooks e scripts devem seguir códigos de saída explícitos:

| Status  | Código | Significado                                                                                    | Comportamento                                                                |
| :------ | :----: | :--------------------------------------------------------------------------------------------- | :--------------------------------------------------------------------------- |
| `PASS`  |  `0`   | Todas as validações passaram no diff staged.                                                   | Permite o commit.                                                            |
| `FAIL`  |  `1`   | Violação determinística encontrada no diff (erro de sintaxe, secret, stub, perda de asserção). | Bloqueia o commit. Exibe arquivo, linha e comando sugerido.                  |
| `ERROR` |  `2`   | Falha de infraestrutura (erro no Git, ausência de ferramenta, crash).                          | **Bloqueia o commit (Fail-Closed)**. Jamais converter erro em falso sucesso. |
| `SKIP`  |  `0`   | Nenhum arquivo relevante para o hook no commit.                                                | Emite mensagem informativa explícita (`SKIP [<GATE>]`).                      |

______________________________________________________________________

## Procedimento

### Passo 1: Inspecionar o Workspace e Identificar a Stack

1. Inspecione a raiz e subpastas do workspace em busca de manifestos (`pyproject.toml`, `package.json`, `Cargo.toml`, `go.mod`, `composer.json`).
2. Identifique o gerenciador de pacotes e o prefixo de execução do projeto (ex: `uv run`, `pnpm exec`, `cargo`).
   Classifique também cada comando encontrado como **validação do lockfile**,
   **sincronização do ambiente** ou **atualização/resolução**. Quando `uv.lock`
   for parte do contrato do projeto, use `uv run --locked` nos gates normais;
   reserve `uv sync --locked` para setup explícito e `uv lock --upgrade` para
   atualizações deliberadas. Nunca deduza um updater de dependências só porque
   a stack possui um manifesto e um lockfile.
3. Consulte [stack-detection.md](references/stack-detection.md) para mapear linters, formatters, typecheckers e runners já configurados.
4. Inspecione se já existe um runner de hooks configurado (`.pre-commit-config.yaml`, `.husky/`, `lefthook.yml` ou scripts em `.git/hooks/`).

### Passo 2: Gap Analysis e Mapeamento de Slots

Compare o estado atual com a matriz de slots conceituais 80/20 (detalhada em [gate-catalog.md](references/gate-catalog.md)):

- `[HYGIENE]`: Espaços no final de linha, nova linha final, marcadores de conflito, arquivos > 500KB.
- `[SYNTAX]`: Compilação/interpretação básica (`py_compile`, `tsc --noEmit`, `go vet`).
- `[FORMATTER]`: Formatação padronizada como auto-fix mecânico seguro (`ruff format`, `prettier`).
- `[LINTER]`: Code quality plus parser-aware structural checks for complexity,
  nesting, flow simplification, error handling, and routine scope.
- `[SECRETS]`: Varredura de credenciais e chaves no diff staged (`gitleaks protect --staged`).
- `[CONFIG]`: Validação de sintaxe JSON, YAML e TOML.
- `[CIRCULAR_DEPENDENCIES]`: Detecção obrigatória de ciclos de imports/dependências e de regressões arquiteturais no grafo afetado; ciclos históricos usam baseline não-crescente.
- `[DIFF_SANITY]`: Interceptação de debuggers, stubs e bypasses recém-criados.
- `[LOCKFILE]`: Validação somente leitura da paridade entre manifesto modificado e lockfile (validando pertencimento a workspaces); nunca atualização automática de dependências.
- `[TEST_INTEGRITY]`: Alerta contra testes com `.only`, `skip`, perda de asserções ou arquivos deletados.

For each structural dimension, record the native rule, metric, threshold,
scope, and status: `ENABLED`, `DELEGATED`, `MANUAL`, or `UNSUPPORTED`.
Cyclomatic and cognitive complexity are separate metrics. The default ceilings
are `15` for each supported complexity metric, `4` nesting levels, and `50`
executable statements per routine. A complete blocking profile accepts only
`ENABLED` or `DELEGATED`; a requested blocking check that is unsupported is an
`ERROR`, not a false `PASS`. Read the complete policy in
[gate-catalog.md](references/gate-catalog.md) and the anti-pattern boundaries
in [agent-anti-patterns.md](references/agent-anti-patterns.md).

### Passo 3: Scaffolding e Composição dos Hooks

1. Se o projeto já utiliza um runner, adapte a configuração existente sem remover regras de negócio válidas.
2. Se o projeto não possui runner:
   - Para ecossistemas Python ou genéricos: utilize o template [.pre-commit-config.yaml](assets/templates/pre-commit-config.yaml.template).
   - Para ecossistemas Go, Rust, Node ou Polyglot: utilize o template [lefthook.yml](assets/templates/lefthook.yml.template).
3. Isole o escopo em monorepos ou projetos multi-stack usando regex de caminhos, conforme [multi-stack-patterns.md](references/multi-stack-patterns.md).
4. Configure `[LINTER]` with the project's existing parser-aware rules. Keep
   structural checks read-only: do not auto-fix conditionals, returns, handlers,
   or business logic. Do not enforce a blanket single-exit rule; guard clauses
   are useful only when they make preconditions and the main path clearer.
5. Configure o slot `[CIRCULAR_DEPENDENCIES]` em todo pre-commit que valide código importável. Se a ferramenta aceitar escopo, execute o grafo do pacote afetado; não substitua a validação por um `SKIP` silencioso. Registre ciclos existentes em baseline e faça qualquer ciclo novo retornar `FAIL`.
6. Configure o slot `[LOCKFILE]` como um gate de validação, não como um
   atualizador. Exija o lockfile correspondente no diff staged e use o comando
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
7. For each remote hook repository, resolve a release and freeze
   `rev` to a 40-character commit SHA before declaring the generated
   configuration ready. Preserve the release in a comment for maintenance;
   do not leave mutable tags in durable project configuration.
8. When a hook uses `additional_dependencies`, resolve and pin the compatible
   group as a unit. Update the base package and its plugins together, validate
   the resolution, and only then record exact pins.
9. Classifique projeções geradas (`.agents/`, `.claude/`, `.codex/`, mirrors e
   artefatos equivalentes) antes de atribuir hooks. Hooks auto-fixáveis e
   corretores lexicais (`end-of-file-fixer`, `ruff --fix`, formatadores e
   `codespell`) devem declarar `exclude` local para esses caminhos quando eles
   puderem estar rastreados. Mantenha scanners de segurança e validações
   semânticas no escopo apropriado e, quando a projeção precisar ser validada,
   use um gate dedicado somente leitura. Corrija sempre a fonte canônica e
   regenere a projeção; não corrija o espelho diretamente.

### Passo 4: Instalar Scripts Auxiliares de Sanidade de IA

Copie ou referencie os scripts portáteis da skill (sem dependências externas) na pasta `scripts/` do projeto:

- `check_diff_sanity.py`: Bloqueia `console.log`, `breakpoint()`, `print` órfão, `throw new Error("TODO")`, supressões de compilador/linter e operações perigosas recém-adicionadas. Marcadores de supressão são bloqueados em todos os formatos não documentais, inclusive com justificativa; os formatos `.md`, `.markdown`, `.rst` e `.txt` permitem somente a citação não executável. Para uma CLI que precisa emitir saída com `print()`, configure cada arquivo explicitamente com `--allow-print-file <path>` no hook; não isente um diretório inteiro. Structural complexity and nesting remain outside this staged-text scanner. Consulte [agent-anti-patterns.md](references/agent-anti-patterns.md).
- `check_test_integrity.py`: Bloqueia `.only`/`fit` sem exceção, bloqueia skips e perda de asserções sem razão e exige policy staged em `.test-deletions.json` para deleção de testes. It does not prove assertion meaning across every framework; use native test lint or `testing-patterns` for assertion vacuum and tautologies.
- `check_lockfile_sync.py`, `lockfile_checks.py`, `staged_changes.py` e `workspace_members.py`: Copie os quatro arquivos juntos para `scripts/`; o primeiro é o CLI, o segundo centraliza a leitura de manifests e as verificações nativas de coerência, o terceiro preserva relações de rename/copy no índice e o quarto fornece a leitura indexada e o matching conservador de membros. O conjunto bloqueia commit de manifesto alterado sem o respectivo lockfile atualizado, comprovando pertencimento aos membros do workspace. O CLI deve analisar o conteúdo staged de `package.json`, dispensar manifests sem dependências declaradas e consultar o gerenciador nativo quando ele puder comprovar a coerência do lockfile. Ele não deve executar atualizadores, resolvers ou sincronizadores de ambiente. Não imponha timeout universal ao comando: escolha escopo e estágio com base no custo observado do projeto.

### Passo 5: Verificação, Tratamento de Legado e Baseline

1. Execute o runner contra os arquivos staged para validar a instalação:
   ```bash
   uv run --locked pre-commit run --files <paths>  # quando uv.lock for autoritativo
   # ou npx lefthook run pre-commit
   ```
2. Se o projeto possuir dívida técnica pré-existente massiva (ex: centenas de erros de tipagem legados), crie um baseline não-crescente seguindo as receitas em [baseline-recipes.md](references/baseline-recipes.md).
3. Para o gate `[CIRCULAR_DEPENDENCIES]`, registre o grafo histórico somente quando necessário e congele a contagem/identidade dos ciclos existentes. Garanta que qualquer ciclo novo ou expansão do baseline retorne `FAIL`.
4. Garanta que novas alterações no diff tenham tolerância zero a regressões.
5. Apply structural baselines only to identified historical findings. New or
   changed routines must satisfy the configured thresholds.

______________________________________________________________________

## Auto-Fix Policy e Staging Seguro

### Ações Permitidas para Correção Automática

- Normalização de espaços em branco e quebras de linha (`trailing-whitespace`, `end-of-file-fixer`).
- Formatadores determinísticos da stack (`ruff format`, `prettier --write`, `gofmt`).
- Organização mecânica de imports (`isort`, `ruff check --select I --fix`).

### Ações Proibidas para Correção Automática

- Alterações em lógica de negócio, condicionais ou retorno de funções.
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

Quando um gate falhar, o relatório emitido para o agente deve conter arquivo, linha, motivo da falha e o comando local para reprodução. Para corrigir uma supressão, corrija o código ou documente o comportamento sem inseri-la no formato executável; nenhuma justificativa transforma um marcador de supressão em autorização:

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

1. Inspeciona `pyproject.toml`, identifica `uv`, `ruff` e `pytest`.
2. Identifica o validador de ciclos já configurado (por exemplo, `import-linter`) e preenche o gate obrigatório `[CIRCULAR_DEPENDENCIES]`.
3. Inspects the existing linter for all structural dimensions and records each
   rule, metric, threshold, scope, and coverage status.
4. Cria `.pre-commit-config.yaml` com `pre-commit-hooks` (higiene), `gitleaks` (secrets), `ruff-format`, `ruff-lint`, o gate de ciclos e os scripts locais `check_diff_sanity.py`, `check_test_integrity.py` e o conjunto `check_lockfile_sync.py` + `lockfile_checks.py` + `staged_changes.py` + `workspace_members.py`.
5. Execute `uv run pre-commit run --files pyproject.toml` and confirm that every relevant hook returns `PASS`. Record observed duration when it helps tune the workflow; do not enforce a universal time threshold.

### Exemplo 1b: Política de dependências em qualquer stack

**Entrada**: Usuário pede: "Adiciona um atualizador de dependências ao
pre-commit."
**Ação do Agente**:

1. Não adiciona um updater automaticamente. Primeiro identifica o gerenciador,
   o manifesto, o lockfile e se existe uma verificação nativa somente leitura.

2. Configura o `[LOCKFILE]` para validar paridade e coerência:

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
2. Configura a verificação do mypy para rodar apenas nos arquivos alterados (`git diff --cached --name-only`) ou registra o baseline com limite fixo de erros.
3. O pre-commit passa a aprovar commits com até 80 erros antigos, mas bloqueia imediatamente qualquer commit que adicione o 81º erro.

### Caso Negativo: Tentativa de Incluir Testes E2E Pesados no Pre-commit

**Entrada**: Usuário pede: "Coloca nossa suíte de testes Playwright E2E e o scan completo de banco no pre-commit."
**Ação do Agente**:

- **Por quê não**: Browser and live database workloads add environment and latency requirements that are disproportionate to a local commit gate. They can block the workflow and encourage the use of `--no-verify`.
- **Solução Correta**: O agente configura no pre-commit apenas a validação estática de sintaxe e diff sanity, posicionando a suíte Playwright e os testes pesados no `pre-push` ou na pipeline de `CI`.

______________________________________________________________________

## Evals de trigger

### Deve acionar

- "Cria uma configuração de pre-commit para este projeto."
- "Adiciona quality gates locais para impedir que a IA commite debugs e console.log."
- "Arruma os hooks do git que estão falhando no commit."
- "Configura pre-commit com ruff, prettier e gitleaks."
- "Adiciona checagem de lockfile e integridade de testes no commit."
- "Adiciona um atualizador de dependências ao pre-commit." → Acionar a
  política de lifecycle: configurar validação de lockfile e explicar por que
  o updater deve ser uma automação deliberada fora do hook.
- "Bloqueia imports circulares antes do commit."
- "Configura o linter para bloquear funções complexas e aninhamento profundo."
- "Adiciona gates para catch-all, handlers vazios e funções longas."

### Não deve acionar

- "Cria uma pipeline de CI no GitHub Actions para deploy em produção." → Encaminhar para arquitetura/CI.
- "Escreve testes E2E com Playwright para o fluxo de checkout." → Encaminhar para `webapp-testing`.
- "Audita a segurança da API contra vulnerabilidades OWASP." → Encaminhar para `vulnerability-scanner`.
- "Refatora essa função que está muito longa." → Encaminhar para `modularizar`.
- "Essa assertion realmente prova a regressão?" → Encaminhar para `testing-patterns`.

______________________________________________________________________

## Evals de workflow

- [ ] Assert: `check_diff_sanity.py` falha com exit code 2 quando o git falha ou fora de um repo git.
- [ ] Assert: `check_diff_sanity.py` bloqueia `@ts-ignore`, `@ts-nocheck`, `@ts-expect-error` e `# type: ignore` em código e configuração com exit code 1, mesmo com uma razão, e aceita suas citações somente nos formatos documentais declarados.
- [ ] Assert: `check_diff_sanity.py` bloqueia `# noqa`, `# noqa: BLE001`, `# noqa: F401` com razão e `# noqa` acompanhado de `allow-bypass`, sempre com exit code 1.
- [ ] Assert: `check_diff_sanity.py` bloqueia `throw new Error("TODO")` mesmo quando acompanhado de comentário de debug.
- [ ] Assert: `check_test_integrity.py` bloqueia `.only` e `fit` sem exceção e bloqueia `skip` sem razão explícita.
- [ ] Assert: `check_test_integrity.py` bloqueia deleção de arquivos de teste a menos que autorizada em `.test-deletions.json` staged no git.
- [ ] Assert: `check_lockfile_sync.py` bloqueia manifesto filho sem lockfile local quando não comprovado o pertencimento aos membros do workspace raiz.
- [ ] Assert: `check_lockfile_sync.py` permite `package.json` sem dependências declaradas sem exigir lockfile.
- [ ] Assert: `check_lockfile_sync.py` aceita lockfile existente somente quando o gerenciador nativo confirma a coerência; ferramenta ausente ou falha ao iniciar/executar o subprocesso retorna `ERROR` com exit code 2, enquanto retorno não zero continua `FAIL` com exit code 1.
- [ ] Assert: O agente separa validação do lockfile, sincronização do ambiente e atualização de dependências; não adiciona updater ou sincronizador mutável ao pre-commit por inferência.
- [ ] Assert: Para uma stack sem verificação nativa somente leitura, o agente mantém a exigência de paridade staged e não inventa um comando de instalação, atualização ou resolução.
- [ ] Assert: O agente não classifica `go mod verify` como coerência de `go.mod`/`go.sum`; quando suportado, usa `go mod tidy -diff` ou mantém a paridade staged.
- [ ] Assert: Uma atualização automática solicitada é colocada em script/job/PR separado, e o pre-commit permanece sem mutações no manifesto, lockfile ou ambiente.
- [ ] Assert: Todo pre-commit configurado para código importável contém o slot `[CIRCULAR_DEPENDENCIES]`; ciclo novo retorna `FAIL`, ciclo histórico só passa por baseline não-crescente e ausência de comando determinístico retorna `ERROR`.
- [ ] Assert: `[LINTER]` records complexity, nesting, flow simplification, error handling, and routine scope with a rule, threshold, scope, and coverage status.
- [ ] Assert: Cyclomatic and cognitive complexity remain separate metrics; unsupported blocking coverage returns `ERROR` instead of inventing a tool.
- [ ] Assert: Structural configuration never uses a generic diff regex, treats physical lines as executable statements, or enforces a blanket single-exit rule.
- [ ] Assert: Broad catches are accepted only at explicit boundaries with a narrow scope, defined handling, and preserved cause.
- [ ] Assert: Assertion vacuum and tautologies remain under `[TEST_INTEGRITY]` and `testing-patterns`, not `[LINTER]`.
