# Contratos de validação

## Escolha do comando

Leia os comandos declarados pelo repositório operado antes de executar qualquer
gate. A escolha depende do resultado solicitado:

| Resultado solicitado                                  | Comando e limite                                                                                                                                                                                                                                  |
| ----------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Checks pontuais de um diff                            | Use os comandos de lint, typecheck ou teste declarados pelo repositório. Relate que a cobertura é parcial.                                                                                                                                        |
| Validação completa ou `gate-report` de uma change     | Use `validationCommand` e `evidencePath` de `openspec/handoff.json`, se declarados. Nesta central, o executor é `scripts/harness_verify.py`; num consumidor que selecionou `tools/harness-verify`, a cópia é `.agents/scripts/harness_verify.py`. |
| Skills e agents na árvore-fonte desta central         | Use os validadores oficiais da central, como `scripts/validate-skills.py` e `scripts/validate-agent-protocols.py`, além dos demais gates exigidos pelo repositório.                                                                               |
| Manifesto, lock e projeção no consumidor              | Use `harness-sync --check`.                                                                                                                                                                                                                       |
| Estrutura de skills, agents e workflows no consumidor | Use `harness-validate --request <caminho-do-request>`. Ele só cobre os escopos declarados no request. Se houver snapshot versionado, use também `--check-result` para detectar evidência desatualizada.                                           |

Se `validationCommand` não existir, leia os hooks e seus estágios antes de
escolher os comandos. `pre-commit run --all-files` executa o estágio
`pre-commit`; hooks `commit-msg` e `pre-push` precisam de seus próprios estágios
ou de um verificador repo-native que os execute. Não apresente um check pontual
ou um único estágio como aprovação de todos os gates.

`harness-validate` inspeciona estaticamente os artefatos selecionados no
request. Ele não confere se o manifesto e o lock correspondem à projeção; essa
é a função de `harness-sync --check`. Também não produz `gate-report.json`.

## Leitura de falhas

- Registre comando, escopo, estágio, código de saída e status de cada gate
  executado. Um escopo opcional `skipped` só é aceitável quando o contrato o
  permite; ele não demonstra que o artefato foi validado.
- Separe falha de código, falha de ambiente e ausência de ferramenta pela
  evidência do terminal. Se não for possível determinar a causa, marque-a como
  indeterminada.
- Para falhas de TypeScript fora do diff, investigue dependências e compare com
  um baseline verificável antes de atribuir a origem. Mesmo quando for
  preexistente, o gate oficial permanece falho; relate isso explicitamente.

Não use autofix amplo como padrão nem substitua `review-workflow` ou
`security-engineer` por uma validação mecânica.

Veja [examples.md](./examples.md) para pedidos e respostas concretos.
