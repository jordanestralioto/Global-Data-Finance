# examples.md

## Exemplo 1 - positivo

Pedido: "Alterei código e preciso validar o minimo antes do review."
Esperado: ler os comandos declarados pelo repositório, executar os checks pertinentes e dizer se o resultado cobre apenas parte dos gates ou todos os estágios exigidos.

## Exemplo 2 - positivo

Pedido: "Gerar evidencia estruturada de gates para a change OpenSpec."
Esperado: usar `validationCommand` e `evidencePath` do `openspec/handoff.json`. Nesta central, o comando declarado é `uv run python scripts/harness_verify.py --evidence-path openspec/changes/<change>/evidence/gate-report.json`. Num consumidor, usar o comando declarado por ele; a cópia `.agents/scripts/harness_verify.py` só existe quando `tools/harness-verify` foi selecionado.

## Exemplo 3 - positivo

Pedido: "Uma das validações falhou; resuma o impacto."
Esperado: reportar o gate que falhou, o comando, o estágio, o exit code e o impacto. Não declarar aprovação completa.

## Exemplo 4 - positivo

Pedido: "Quero rodar apenas typecheck e linter."
Esperado: usar os comandos repo-native correspondentes e relatar que os outros gates não foram executados.

## Exemplo 5 - positivo

Pedido: "Valide as skills projetadas do consumidor contra a governance."
Esperado: conferir o request existente e usar `harness-validate --request .agents/validation/request.json` para a estrutura dos escopos declarados. Se houver snapshot versionado, conferir também com `--check-result`.

## Exemplo 6 - positivo

Pedido: "Confere agents, manifests e skills projetadas."
Esperado: usar `harness-sync --check` para manifesto, lock e projeção; usar `harness-validate --request .agents/validation/request.json` para agents e skills somente se esses escopos estiverem declarados. Relatar qualquer escopo ausente.

## Exemplo 7 - positivo

Pedido: "O typecheck falhou em outro arquivo; posso considerar validado?"
Esperado: manter o gate como falho. Só chamar a falha de preexistente após comparar com um baseline verificável e relatar a evidência.

## Exemplo 8 - negativo

Pedido: "Quero desenhar a arquitetura da nova feature."
Esperado: nao acionar `lint-and-validate`; isso e planejamento, nao validacao.

## Exemplo 9 - negativo

Pedido: "Aplique ruff --fix no repo inteiro."
Esperado: nao acionar como fluxo padrao; autofix e mutacao ampla e precisa autorizacao explicita.
