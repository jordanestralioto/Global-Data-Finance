# Evals de workflow para `agents-md-author`

## Estado de execução

**Luna Max:** not run. Esta entrega define os cenários e suas assertions; não
houve uma sessão real com Luna Max. Validações de Markdown ou pytest não contam
como execução desses evals.

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

- [ ] Registra o diretório inicial `packages/worker` e a raiz do projeto.
- [ ] Distingue o root `AGENTS.md` do override local e só considera
  `packages/TEAM_GUIDE.md` conforme a configuração mostrada.
- [ ] Aponta `packages/worker/src/worker.py` como primeiro caminho de código e
  `packages/worker/README.md` como próximo documento.
- [ ] Registra `uv run pytest -q tests/worker` do override e mantém a política comum
  somente no root.
- [ ] Explica o limite configurado sem afirmar que toda instrução descoberta
  coube na cadeia carregada.
- [ ] Não copia para o override regras compartilhadas sem diferença local.

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
