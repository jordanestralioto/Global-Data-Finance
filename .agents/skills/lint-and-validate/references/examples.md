# examples.md

## Exemplo 1 - positivo

Pedido: "Alterei código e preciso validar o minimo antes do review."
Esperado: ler os comandos declarados pelo repositório, executar os checks pertinentes e dizer se o resultado cobre apenas parte dos gates ou todos os estágios exigidos.

## Exemplo 2 - positivo

Pedido: "Gerar evidencia estruturada de gates para a change OpenSpec."
Esperado: usar `validationCommand` e `evidencePath` do `openspec/handoff.json`. Nesta central, o comando declarado é `uv run python scripts/harness_verify.py --evidence-path openspec/changes/<change>/evidence/gate-report.json`. Num consumidor, usar o comando declarado por ele; a cópia `.agents/scripts/harness_verify.py` só existe quando `tools/harness-verify` foi selecionado. Descrever o relatório como vinculado ao estado do repositório por `stateFingerprint`, sem chamá-lo de assinado.

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

## Exemplo 10 - checks pontuais aprovados

Pedido: "O mypy da skill e três arquivos de pytest passaram. Posso dizer que
todos os validadores passaram?"

Esperado: comparar com o contrato vigente e apresentar a evidência de escopo
delimitado. Por exemplo, se ambos os comandos abaixo tiverem sido executados
diretamente e retornado `0`, registrar:

| Comando                                                                                                                                                        | Modo          | Escopo                               | Estágio executado | Exit code | Status                |
| -------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------- | ------------------------------------ | ----------------- | --------- | --------------------- |
| `uv run --locked mypy --no-incremental skills/lint-and-validate`                                                                                               | Direto/manual | Apenas a skill                       | Nenhum            | 0         | Aprovado nesse escopo |
| `uv run --locked pytest -q tests/unit/test_agent_protocol_contracts.py tests/unit/test_component_catalog.py tests/integration/test_projected_tool_autonomy.py` | Direto/manual | Três arquivos, sem gate de cobertura | Nenhum            | 0         | Aprovado nesse escopo |

Declarar validação parcial. Listar o typecheck completo, a suíte com cobertura
e os estágios ainda não executados conforme o roster oficial. Não transformar
o exemplo em registro de uma execução real nem fixar uma contagem de testes.

## Exemplo 11 - compatibilidade e portabilidade

Pedido: "O runner de ai-verify sumiu; apague seus assets e uma regra exclusiva do meu projeto."

Esperado: preservar os quatro arquivos publicados e seus formatos, remover a
regra específica da distribuição e documentar o efeito para quem a utilizava.
Se o consumidor depender da escalada removida, inspecionar seu runner e manter
essa regra na configuração do projeto, fora da projeção gerenciada. Preservar
os assets não obriga manter caminhos de domínio no contrato compartilhado.
A aprovação do validador de protocolos só confirma a presença desses assets.

## Exemplo 12 - limite da avaliação estática

Pedido: "Os validadores passaram; isso prova que a skill evita conclusão prematura?"

Esperado: relatar o que os checks cobrem e que a skill instrui o agente a
distinguir validação parcial de completa. Eficácia comportamental requer evals
executados e transcrições; cenários propostos e leitura da description não a
demonstram.
