# examples.md

## Exemplo 1 - positivo

Pedido: "Alterei código e preciso validar o minimo antes do review."
Esperado: rodar a validação repo-native (`pre-commit run --all-files` ou o comando oficial do projeto).

## Exemplo 2 - positivo

Pedido: "Gerar evidencia estruturada de gates para a change OpenSpec."
Esperado: usar o entrypoint oficial do projeto (`uv run python -m scripts.ai_verify --evidence-path ...` ou equivalente).

## Exemplo 3 - positivo

Pedido: "Uma das validações falhou; resuma o impacto."
Esperado: reportar o gate que falhou, o comando executado, o exit code e o impacto.

## Exemplo 4 - positivo

Pedido: "Quero rodar apenas typecheck e linter."
Esperado: usar os comandos repo-native correspondentes (`uv run ruff check .` e `uv run mypy .` ou hooks do pre-commit).

## Exemplo 5 - positivo

Pedido: "Valide as skills projetadas do consumidor contra a governance."
Esperado: usar `harness-validate --request .agents/validation/request.json`.

## Exemplo 6 - positivo

Pedido: "Confere agents, manifests e skills projetadas."
Esperado: usar `harness-validate --request .agents/validation/request.json` e deixar claro que a validação portátil cobre a projeção do consumidor.

## Exemplo 7 - negativo

Pedido: "Quero desenhar a arquitetura da nova feature."
Esperado: nao acionar `lint-and-validate`; isso e planejamento, nao validacao.

## Exemplo 8 - negativo

Pedido: "Aplique ruff --fix no repo inteiro."
Esperado: nao acionar como fluxo padrao; autofix e mutacao ampla e precisa autorizacao explicita.
