# Evals de workflow para `agents-md-author`

## Estado de execução

**Luna Max:** not run. Não houve uma sessão real com Luna Max. Validações de
Markdown ou pytest não contam como execução desses evals.

**Agentes independentes, 2026-11-06:** execução em fixtures sintéticos de Go,
Rust e TypeScript, usando o modelo herdado da sessão, sem override. A revisão
dos documentos foi separada da validação estrutural:

| Cenário e variante    | Resultado observado após iteração                                                       |
| --------------------- | --------------------------------------------------------------------------------------- |
| A, serviço Go         | Objetivo, `cmd/reports/main.go`, `make test` e próximo guia confirmados                 |
| B, workspace Rust     | Override contém somente navegação e teste locais; contexto da sessão fica na devolutiva |
| C, serviço TypeScript | README, manifest e CI oculto aparecem no conflito sem comando oficial inventado         |

A execução revelou duas falhas de workflow: metadados da sessão entraram no
override e uma busca sem `--hidden` omitiu CI. A orientação foi corrigida e os
casos foram reavaliados em contextos limpos. A CLI também detectou headings
incorretos, corrigidos pelos próprios agentes antes da entrega. Os três
documentos finais passaram na estrutura; as ferramentas do projeto não foram
executadas. Esses casos não medem ganho estatístico de acerto, custo ou eficácia
em projetos reais e não substituem a execução com Luna Max.

## Variações de linguagem

Repita o Eval A trocando as fontes e as assertions de tooling pela variante
selecionada. A linguagem do projeto não muda o procedimento de autoria:

| Variante | Fonte de tooling      | Primeiro caminho      | Comando confirmado |
| -------- | --------------------- | --------------------- | ------------------ |
| Python   | `pyproject.toml`      | `src/main.py`         | `uv run pytest -q` |
| Go       | `go.mod` e `Makefile` | `cmd/reports/main.go` | `go test ./...`    |
| Rust     | `Cargo.toml` e CI     | `src/main.rs`         | `cargo test`       |

Use cada comando somente se as fontes do fixture o confirmarem. Execute os
helpers da skill com Python em qualquer variante, sem gravar essa dependência
como requisito do projeto. A avaliação deve verificar o documento e a sequência
de ações; um script portátil ou um teste de conteúdo não prova a execução do
workflow por um modelo.

## Eval A — Projeto simples

**Entrada:** “Crie ou revise as instruções deste serviço para que um agente saiba
onde começar e como validar.”

**Fontes disponíveis no projeto de avaliação:**

- `README.md`: o serviço processa arquivos de configuração para gerar relatórios;
- `src/main.py`: entrypoint do serviço;
- `pyproject.toml`: declara `uv` e o comando de teste `uv run pytest -q`;
- `docs/architecture.md`: descreve o fluxo e seus owners.

**Assertions:**

- [ ] Explica o objetivo como processamento de arquivos de configuração para
  gerar relatórios.
- [ ] Aponta `src/main.py` como primeiro caminho de código.
- [ ] Registra `uv run pytest -q` como comando de teste e associa-o a
  `pyproject.toml`.
- [ ] Aponta `docs/architecture.md` como próximo documento para o fluxo.
- [ ] Não executa enumeração irrestrita da árvore inteira, como `find .` ou
  `rg --files` sem filtros.
- [ ] Não adiciona framework, owner, métrica ou comando ausente das fontes.

## Eval B — Monorepo com override local

**Entrada:** “Revise as instruções do workspace `packages/worker`, iniciado
naquela pasta, e garanta que as regras compartilhadas não sejam copiadas para o
arquivo local.”

**Fontes disponíveis no projeto de avaliação:**

- root `AGENTS.md`: política comum e teste geral `uv run pytest -q`;
- `packages/TEAM_GUIDE.md`: mapa compartilhado de pacotes;
- `packages/worker/AGENTS.override.md`: executa `uv run pytest -q tests/worker` para validar o worker;
- `packages/worker/src/worker.py`: entrypoint local;
- `packages/worker/README.md`: guia local;
- configuração do cliente: registra `TEAM_GUIDE.md` como fallback e define
  `project_doc_max_bytes = 65536`.

**Assertions:**

- [ ] Registra na devolutiva o diretório inicial `packages/worker` e a raiz do projeto.
- [ ] Distingue o root `AGENTS.md` do override local e só considera
  `packages/TEAM_GUIDE.md` conforme a configuração mostrada.
- [ ] Aponta `packages/worker/src/worker.py` como primeiro caminho de código e
  `packages/worker/README.md` como próximo documento.
- [ ] Registra `uv run pytest -q tests/worker` do override e mantém a política comum
  somente no root.
- [ ] Explica na devolutiva o limite configurado sem afirmar que toda instrução descoberta
  coube na cadeia carregada.
- [ ] Não copia para o override regras compartilhadas sem diferença local.
- [ ] Não grava o diretório da sessão, seus fallbacks ou seu orçamento no override
  como política do projeto sem uma fonte compartilhada que os adote.

## Eval C — Fontes conflitantes

**Entrada:** “Escreva instruções para o serviço de pagamentos usando as fontes
atuais. Não presuma qual delas está certa.”

**Fontes disponíveis no projeto de avaliação:**

- `README.md`: descreve o serviço como responsável por emitir e conciliar
  pagamentos e recomenda `npm test`;
- `package.json`: declara `pnpm` e um script de testes diferente;
- `.github/workflows/ci.yml`: executa `bun test`;
- `packages/payments/src/index.ts`: entrypoint de pagamentos;
- `packages/payments/README.md`: guia específico do serviço.

**Assertions:**

- [ ] Descreve o objetivo usando o README e aponta
  `packages/payments/src/index.ts` como primeiro caminho de código.
- [ ] Lista as três fontes e os respectivos comandos conflitantes sem declarar
  um deles como validação oficial.
- [ ] Identifica `packages/payments/README.md` como próximo documento para o
  escopo local.
- [ ] Deixa a escolha de comando sem resolução e pede a decisão apenas para
  materializar essa regra; fatos independentes permanecem documentados.
- [ ] Não executa um comando de teste escolhido por preferência ou por uma
  suposição sobre precedência.
- [ ] Não inventa owner, framework, política ou resultado de validação.
