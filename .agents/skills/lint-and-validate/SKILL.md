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
- **Cheap First, Evidence Complete:** Comece pelos gates mais baratos de interpretar, mas execute a validação repo-native oficial declarada no repositório (`openspec/handoff.json`, `.pre-commit-config.yaml` ou `AGENTS.md`).
- **Isolamento:** Quando o TypeScript falhar, olhe apenas para o arquivo que você editou e os arquivos que dependem dele. Ignorar erros não relacionados ao escopo a menos que você os tenha causado.

## Procedimento

1. Identifique o artefato que precisa ser validado antes de escolher o comando:
   - diff comum do repositório: comando repo-native oficial declarado pelo consumidor (`openspec/handoff.json` via `validationCommand`, `.pre-commit-config.yaml` ou `AGENTS.md`)
   - skills, agents e workflows projetados no consumidor: executar `harness-validate --request <caminho>` (ex.: `harness-validate --request .agents/validation/request.json`)
2. Execute a suíte de validação e os gates pertinentes à mudança sem pular verificações obrigatórias.
3. Leia o resultado das gates e garanta que todas passaram com código 0. Não trate gate não executada ou skipped como sucesso implícito.
4. Responda com evidência terminal mínima: comando, escopo, status, classificação da falha quando existir e próximo passo. Não declare sucesso sem output correspondente.

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
- [ ] reporta status das gates executadas de forma determinística
- [ ] reporta falhas e saídas de terminal com clareza

### Cenário 2 - validação de skills, agents ou workflows

Entrada: pedido para validar skills, agents ou workflows projetados no consumidor.

Assertions:

- [ ] usa `harness-validate --request <caminho-do-request>`
- [ ] não recomenda `validate-skills.py` nem `validate-agent-protocols.py` fora da central
- [ ] reporta diagnósticos e códigos de erro de validação com clareza

### Cenário 3 - validação repo-native do projeto

Entrada: pedido para validar o projeto segundo seus comandos declarados.

Assertions:

- [ ] usa o comando oficial declarado pelo consumidor
- [ ] reporta status das gates executadas de forma determinística
- [ ] reporta falha estrutural sem declarar sucesso parcial implícito

### Cenário 4 - falha externa

Entrada: comando oficial falha por ausência de ferramenta no ambiente.

Assertions:

- [ ] classifica a falha como ambiente ou `external_failure`
- [ ] não classifica o problema como erro de código sem evidência
- [ ] devolve comando e sintoma mínimo para reproduzir

### Cenário 5 - E2E proporcional

Entrada: mudança de texto em componente interno sem fluxo de navegador afetado.

Assertions:

- [ ] não força E2E sem necessidade quando a mudança é puramente textual ou interna
- [ ] usa os testes repo-native correspondentes
- [ ] deixa explícito se testes adicionais são recomendados

## Scripts

- O executor de verificação (`ai-verify`) pertence ao projeto consumidor:
  ele codifica os gates, caminhos e escalações daquele repositório. Este
  harness publica o contrato que ele precisa satisfazer
  (`schemas/ai-verify.schema.json` e `assets/verification-profiles.json`),
  não o executor.
- `scripts/normalize-skill-metadata.py`: helper privado desta skill que remove metadados extras do frontmatter de skills em lote controlado.
- `.agents/scripts/check-max-lines.py`: tool pública selecionada pelo catálogo (`tools/check-max-lines`) como gate portátil de tamanho de arquivo por responsabilidade (produção 400, teste 1000, documentação 500 linhas). O consumidor executa `python .agents/scripts/check-max-lines.py` e adiciona o comando ao próprio gate roster.

## Referências

Leia apenas o arquivo relevante para o tipo de validação em mãos:

| Problema                                             | Arquivo                   |
| ---------------------------------------------------- | ------------------------- |
| Ver exemplos de gate-report e resposta final         | `references/examples.md`  |
| Confirmar contrato operacional do fluxo de validação | `references/reference.md` |
