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

## Escopo e modo de execução

Registre como o comando foi chamado, além do hook ao qual ele corresponde:

| Execução                                                | O que registrar                                                                               |
| ------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| Comando de lint, typecheck ou teste chamado diretamente | Modo direto/manual; estágio não executado. Cite o hook correspondente apenas como referência. |
| `pre-commit run --all-files`                            | Modo hook; estágio `pre-commit`; status de cada hook, incluindo `skipped`.                    |
| `pre-commit run --hook-stage pre-push --all-files`      | Modo hook; estágio `pre-push`, sem inferir execução dos demais estágios.                      |
| Verificador canônico declarado pelo repositório         | Modo verificador; estágios e gates efetivamente registrados no relatório.                     |

Compare os argumentos e arquivos com a configuração oficial. Nesta central,
o hook de mypy cobre `harness runtime scripts skills`; executá-lo apenas em
`skills/lint-and-validate` é um check pontual. O hook de pytest executa a suíte
`not release` com cobertura mínima de 85%; selecionar alguns arquivos sem medir
cobertura não comprova aprovação desse hook. Consulte a configuração vigente
antes de reutilizar esses exemplos.

Checks estruturais comprovam apenas suas regras implementadas. Em particular,
a checagem dos quatro assets de `ai-verify` em
`scripts/validate-agent-protocols.py` verifica presença, sem validar semanticamente
esses JSONs. Ao avaliar uma skill, diferencie instruções lidas estaticamente de
resultados observados: eficácia de trigger e workflow requer cenários executados,
transcrições e assertions avaliadas. Cenários apenas escritos continuam propostos.

## Vinculação da evidência

O verificador canônico calcula `stateFingerprint` com SHA-256 sobre um payload
serializado que inclui HEAD, estado dos arquivos alterados e resultados dos
gates. A reverificação compara esse hash com o estado atual. Use a expressão
"`gate-report.json` vinculado ao estado do repositório por `stateFingerprint`".
Esse mecanismo não fornece assinatura digital nem autentica quem executou os
checks. Depois de novas alterações, gere e confira a evidência exigida pelo
contrato antes de reutilizá-la.

## Compatibilidade dos assets publicados

A decisão Q70 de preservação de `ai-verify` mantém estes quatro arquivos:

- `schemas/ai-verify.schema.json`;
- `assets/verification-profiles.json`;
- `assets/path-rules.json`;
- `assets/escalation-rules.json`.

Eles publicam o contrato para um runner de propriedade do consumidor. Sua
presença não implica que o runner removido esteja disponível nem que o
verificador canônico carregue seus perfis ou regras: ele lê o roster local de
`.pre-commit-config.yaml`. O schema e o template de `gate-report` consumidos
pelo runtime de review também têm consumidores; sua localização não basta
para justificar remoção ou realocação.

Preservar esses arquivos não obriga manter regras de domínio de um consumidor
no asset compartilhado. Mantenha essas regras em arquivos de propriedade do
projeto, fora da projeção gerenciada. Confira no runner do consumidor como a
configuração é carregada; não presuma um mecanismo de override nem edite
`.agents/skills/` para configurá-las.

Ao remover uma regra específica da distribuição, documente a mudança de
comportamento para quem a utilizava. No caso corrigido, o caminho de domínio
deixa de ter uma regra `high-risk` e continua abrangido por `src/**/*.py`
(`standard`). O consumidor que depender da escalada removida precisa manter
essa regra na configuração local. A limpeza de
regras específicas preserva os quatro arquivos, seus formatos e as demais
regras genéricas. Retirar arquivos ou alterar formatos publicados exige avaliar
compatibilidade e migração como evolução do contrato.

Na árvore-fonte desta central, a decisão Q70 está em
`docs/internal/retire-ai-verify-references-contract.md`; a decisão D1 está em
`openspec/changes/archive/2026-08-19-retire-ai-verify-references/design.md`.
Esses documentos históricos não são pré-requisitos de instalação no consumidor.

## Leitura de falhas

- Registre comando, escopo, estágio, código de saída e status de cada gate
  executado. Um escopo opcional `skipped` só é aceitável quando o contrato o
  permite; ele não demonstra que o artefato foi validado.
- Separe falha de código, falha de ambiente e ausência de ferramenta pela
  evidência do terminal. Se não for possível determinar a causa, marque-a como
  indeterminada.
- Para falhas fora do diff, investigue dependências e compare com
  um baseline verificável antes de atribuir a origem. Mesmo quando for
  preexistente, o gate oficial permanece falho; relate isso explicitamente.

Não use autofix amplo como padrão nem substitua `review-workflow` ou
`security-engineer` por uma validação mecânica.

Veja [examples.md](./examples.md) para pedidos e respostas concretos.
