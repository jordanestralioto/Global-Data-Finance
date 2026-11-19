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

- **Evidência delimitada:** Execute os checks e restrinja a conclusão ao que eles verificaram. Aprovação estrutural não demonstra semântica dos assets nem eficácia comportamental de uma skill; esta requer evals e transcrições.
- **Cheap First, Evidence Complete:** Comece pelos gates mais baratos de interpretar, mas execute a validação repo-native oficial declarada no repositório (`openspec/handoff.json`, `.pre-commit-config.yaml` ou `AGENTS.md`) antes de afirmar que a validação está completa.
- **Atribuição sem ocultação:** Investigue a falha nos arquivos alterados e em seus dependentes. Só classifique um erro como preexistente com evidência de baseline; mesmo assim, reporte o gate oficial como falho, com seu escopo e código de saída.

## Procedimento

1. Identifique o artefato e leia o contrato do repositório antes de escolher comandos:
   - diff comum: use os comandos repo-native declarados em `AGENTS.md`, `.pre-commit-config.yaml` e, para evidência por change, `validationCommand` e `evidencePath` de `openspec/handoff.json`;
   - fonte de skills e agents nesta central: use os validadores oficiais listados no `AGENTS.md` desta central, conforme o escopo;
   - consumidor: use `harness-sync --check` para manifesto, lock e projeção; use `harness-validate --request <caminho>` para a validação estática dos escopos de skills, agents e workflows declarados no request. Se houver snapshot versionado, confira-o com `--check-result`.
2. Compare o escopo escolhido com o contrato: arquivos, opções, cobertura mínima e estágios. Um typecheck restrito à skill ou alguns arquivos de teste não substituem o gate oficial mais amplo. Executar diretamente o comando de um hook é execução manual; só registre um estágio como executado quando o runner de hooks o percorreu. `pre-commit run --all-files` cobre o estágio `pre-commit`, não os gates `commit-msg` e `pre-push`.
   For an OpenSpec change, generate `gate-report` with its declared `validationCommand`. For an ordinary review, use `record-gate-report.py --session-dir .agents/sessions/<review>` without `--change`; native evidence stays in that session. Do not create a change just to store a report. This central's canonical verifier executes every declared stage. In a consumer, use the projected verifier only when `tools/harness-verify` is selected or the local contract points to it.
3. Execute primeiro os checks baratos pertinentes e depois todos os gates exigidos pelo contrato. Leia o código de saída e o status de cada gate. Não trate gate ausente, não executado ou `skipped` como sucesso implícito; indique quando a validação foi apenas parcial.
4. Responda com evidência terminal mínima: comando, modo de execução (direto, hook ou verificador), escopo, estágio efetivamente executado, código de saída, status, classificação da falha quando existir e próximo passo. Liste gates exigidos que não rodaram. Não declare sucesso completo se algum gate exigido falhou ou não rodou.
5. Ao citar evidência do verificador canônico, descreva o `gate-report.json` como vinculado ao estado do repositório por `stateFingerprint`. Esse hash SHA-256 permite conferir a vinculação; não é assinatura nem prova de autenticidade.

## Exemplos

### Caso positivo

**Entrada:** Após mudar frontend e backend, usuário pede validação antes de finalizar.
**Saída esperada:** Executar validação repo-native, resumir evidência e produzir gate-report quando exigido.

### Caso negativo

**Entrada:** Usuário pergunta qual arquitetura escolher antes de código existir.
**Por quê não:** Não há artefato para validar; use planejamento/arquitetura.

## Scripts

- O executor de gate-report segue o `validationCommand` do repositório.
  Esta central publica o verificador como `tools/harness-verify`; o consumidor
  só encontra sua cópia projetada quando seleciona esse componente. Não
  presuma a existência de `ai-verify`.
- `.agents/scripts/check-max-lines.py`: tool pública selecionada pelo catálogo (`tools/check-max-lines`) como gate portátil de tamanho de arquivo por responsabilidade (produção 400, teste 1000, documentação 500 linhas). O consumidor executa `python .agents/scripts/check-max-lines.py` e adiciona o comando ao próprio gate roster.

Preserve os quatro assets de `ai-verify` (`schemas/` e `assets/`): são contrato
publicado e validado. Regras exclusivas de um consumidor ficam na configuração
local dele; detalhes em `references/reference.md`.

## Referências

Leia apenas o arquivo relevante para o tipo de validação em mãos:

| Problema                                             | Arquivo                   |
| ---------------------------------------------------- | ------------------------- |
| Ver exemplos de gate-report e resposta final         | `references/examples.md`  |
| Confirmar contrato operacional do fluxo de validação | `references/reference.md` |
