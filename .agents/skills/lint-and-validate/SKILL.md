---
name: lint-and-validate
description: >-
  Use para escolher e executar validações nativas do repositório após alterações.
  Ative quando o usuário pedir "valida", "roda os checks", "garante que não
  quebrou", "roda testes", "passa o lint", "gera gate-report", "confere antes de
  finalizar" ou quando a entrega exigir evidência de terminal. Cobre lint,
  typecheck, testes, verificação nativa e gate-report. Não use para planejar
  estratégia de testes, investigar causa incerta ou validar UI no navegador quando
  a evidência exigir Playwright/screenshot.
---

# Lint And Validate

## Fundamentos

- **Confiança Cega é Falha:** Nunca entregue um código dizendo "Acredito que vai funcionar". Você deve executar lints e testes reais via terminal para comprovar.
- **Cheap First, Evidence Complete:** Comece pelos gates mais baratos de interpretar, mas execute a validação repo-native oficial declarada no repositório (`openspec/handoff.json`, `.pre-commit-config.yaml` ou `AGENTS.md`) antes de afirmar que a validação está completa.
- **Atribuição sem ocultação:** Investigue uma falha de TypeScript nos arquivos alterados e em seus dependentes. Só classifique um erro como preexistente com evidência de baseline; mesmo assim, reporte o gate oficial como falho, com seu escopo e código de saída.

## Procedimento

1. Identifique o artefato e leia o contrato do repositório antes de escolher comandos:
   - diff comum: use os comandos repo-native declarados em `AGENTS.md`, `.pre-commit-config.yaml` e, para evidência por change, `validationCommand` e `evidencePath` de `openspec/handoff.json`;
   - fonte de skills e agents nesta central: use os validadores oficiais listados no `AGENTS.md` desta central, conforme o escopo;
   - consumidor: use `harness-sync --check` para manifesto, lock e projeção; use `harness-validate --request <caminho>` para a validação estática dos escopos de skills, agents e workflows declarados no request. Se houver snapshot versionado, confira-o com `--check-result`.
2. Distinga checks pontuais de validação completa. `pre-commit run --all-files` cobre o estágio `pre-commit`, não os gates `commit-msg` e `pre-push`. Para gerar `gate-report`, execute o `validationCommand` declarado; nesta central ele chama o verificador canônico, que percorre os estágios declarados. No consumidor, use o verificador projetado somente se `tools/harness-verify` estiver selecionado ou se o contrato local apontar para ele.
3. Execute primeiro os checks baratos pertinentes e depois todos os gates exigidos pelo contrato. Leia o código de saída e o status de cada gate. Não trate gate ausente, não executado ou `skipped` como sucesso implícito; indique quando a validação foi apenas parcial.
4. Responda com evidência terminal mínima: comando, escopo, estágio, status, classificação da falha quando existir e próximo passo. Não declare sucesso completo se algum gate exigido falhou ou não rodou.

## Exemplos

### Caso positivo

**Entrada:** Após mudar frontend e backend, usuário pede validação antes de finalizar.
**Saída esperada:** Executar validação repo-native, resumir evidência e produzir gate-report quando exigido.

### Caso negativo

**Entrada:** Usuário pergunta qual arquitetura escolher antes de código existir.
**Por quê não:** Não há artefato para validar; use planejamento/arquitetura.

## Evals de trigger

Deve acionar:

- "roda validação depois das mudanças"
- "gera gate-report desse PR"
- "quero saber quais gates vão rodar antes"
- "uma gate falhou; resume o impacto"
- "essa mudança pequena precisa de E2E?"

Não deve acionar:

- "qual stack devo usar?"
- "desenha a arquitetura"
- "projete uma migration segura para este schema"
- "revise se este componente está com UX genérica"
- "implemente a feature inteira"
- "corrija automaticamente todos os problemas de lint"

## Evals de workflow

### Cenário 1 - diff comum

Entrada: repositório com `.pre-commit-config.yaml` configurado.

Assertions:

- [ ] escolhe a validação repo-native como entrypoint principal
- [ ] distingue os gates `pre-commit` dos estágios `commit-msg` e `pre-push`
- [ ] reporta status das gates executadas de forma determinística
- [ ] reporta falhas e saídas de terminal com clareza

### Cenário 2 - validação de skills, agents ou workflows

Entrada: pedido para validar skills, agents ou workflows projetados no consumidor.

Assertions:

- [ ] usa `harness-validate --request <caminho-do-request>` para os escopos estáticos declarados
- [ ] usa `harness-sync --check` para conferir manifesto, lock e projeção
- [ ] não afirma que `harness-validate` confere manifesto ou lock
- [ ] não recomenda `validate-skills.py` nem `validate-agent-protocols.py` fora da central
- [ ] reporta diagnósticos e códigos de erro de validação com clareza

### Cenário 3 - validação repo-native do projeto

Entrada: pedido para validar o projeto segundo seus comandos declarados.

Assertions:

- [ ] usa o comando oficial declarado pelo consumidor
- [ ] reporta status das gates executadas de forma determinística
- [ ] reporta falha estrutural sem declarar sucesso parcial implícito

### Cenário 4 - gate-report por change

Entrada: `openspec/handoff.json` declara `validationCommand` e `evidencePath`.

Assertions:

- [ ] executa o comando declarado com o caminho de evidência da change
- [ ] não inventa um comando `ai-verify` ausente do contrato
- [ ] confere os estágios exigidos antes de declarar todos os gates aprovados

### Cenário 5 - falha externa

Entrada: comando oficial falha por ausência de ferramenta no ambiente.

Assertions:

- [ ] classifica a falha como ambiente ou `external_failure`
- [ ] não classifica o problema como erro de código sem evidência
- [ ] devolve comando e sintoma mínimo para reproduzir

### Cenário 6 - E2E proporcional

Entrada: mudança de texto em componente interno sem fluxo de navegador afetado.

Assertions:

- [ ] não força E2E sem necessidade quando a mudança é puramente textual ou interna
- [ ] usa os testes repo-native correspondentes
- [ ] deixa explícito se testes adicionais são recomendados

### Cenário 7 - erro preexistente

Entrada: typecheck repo-native falha em arquivo fora do diff.

Assertions:

- [ ] só atribui a falha ao baseline se houver evidência comparável
- [ ] reporta o gate oficial como falho e não declara validação completa

## Scripts

- O executor de gate-report segue o `validationCommand` do repositório.
  Esta central publica o verificador como `tools/harness-verify`; o consumidor
  só encontra sua cópia projetada quando seleciona esse componente. Não
  presuma a existência de `ai-verify`.
- `scripts/normalize-skill-metadata.py`: helper privado desta skill que remove metadados extras do frontmatter de skills em lote controlado.
- `.agents/scripts/check-max-lines.py`: tool pública selecionada pelo catálogo (`tools/check-max-lines`) como gate portátil de tamanho de arquivo por responsabilidade (produção 400, teste 1000, documentação 500 linhas). O consumidor executa `python .agents/scripts/check-max-lines.py` e adiciona o comando ao próprio gate roster.

## Referências

Leia apenas o arquivo relevante para o tipo de validação em mãos:

| Problema                                             | Arquivo                   |
| ---------------------------------------------------- | ------------------------- |
| Ver exemplos de gate-report e resposta final         | `references/examples.md`  |
| Confirmar contrato operacional do fluxo de validação | `references/reference.md` |
