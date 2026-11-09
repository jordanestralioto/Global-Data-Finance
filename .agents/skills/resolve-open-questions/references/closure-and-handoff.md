# Fechamento e handoff

Leia depois da confirmação do entendimento, com a sabatina `fechada` e datada.
Estas regras completam o template sem depender de um catálogo de ADRs externo.

## Rascunhos de ADR

Preserve em ADR somente decisões com impacto estrutural: fronteiras de camadas
ou subsistemas, contratos compartilhados, estratégia de processamento ou
persistência, governança ou dependências difíceis de reverter. Escolhas locais,
parâmetros e fatos apurados continuam no documento da sabatina.

Se o consumidor tiver uma política de ADRs, consulte-a e registre os critérios
aplicáveis. Na ausência dela, os critérios acima bastam para criar um rascunho
interno; não invente um catálogo, status canônico ou regra de numeração.

Use [o template](../assets/adr-draft-template.md) em:

```text
docs/internal/sabatina/adr-draft/adr-draft-<slug-da-decisao>.md
```

Este é o destino interno do workflow, aceito pelo validador. O slug descreve a
decisão em kebab-case, permitindo vários rascunhos por sabatina. Não atribua um
número `NNNN` antes da promoção. A tabela do documento usa
`adr-draft/adr-draft-<slug-da-decisao>.md` ou o caminho completo acima.

Compare a procedência antes de escrever: mesma sabatina e mesmas dúvidas
permitem retomar; procedência diferente exige slug desambiguado. Cite os `Qn`
que sustentam cada rascunho e as razões reais das alternativas rejeitadas.
Liste as decisões que não viraram ADR e explique o motivo. Zero rascunhos é
válido quando nenhuma decisão atende aos critérios.

A promoção pertence ao workflow seguinte e depende de sua autorização. Siga o
destino, os identificadores e os estados da política do consumidor quando ela
existir. Se não existir, mantenha o rascunho interno até uma decisão explícita
sobre um catálogo; a sabatina pode ser encerrada sem criar um.

## Conteúdo do handoff

Preencha as oito seções do template: objetivo, decisões e alternativas,
fatos com evidência, premissas e gatilhos, invariantes, critérios de aceite,
artefatos e próximo workflow proposto. O handoff deve permitir continuar sem
reinterpretar as decisões.

## Matriz determinística de rota

Registre valor e evidência para cada critério:

| critério                 | efeito de `sim`                                          |
| ------------------------ | -------------------------------------------------------- |
| `contrato duradouro`     | recomenda OpenSpec                                       |
| `multiplos consumidores` | recomenda OpenSpec                                       |
| `dado persistido novo`   | investiga contrato e lifecycle; não define rota sozinho  |
| `rollout supervisionado` | recomenda OpenSpec                                       |
| `rollback proprio`       | recomenda OpenSpec                                       |
| `lifecycle auditavel`    | recomenda OpenSpec                                       |
| `varios passos`          | recomenda plano quando nenhum critério formal se aplicar |

Em `contrato duradouro`, avalie contrato compartilhado ou responsabilidades de
owners independentes, seguindo os mesmos critérios de `openspec-workflow`.
Persistência local nova, por si só, não obriga um lifecycle formal. Quando ela
introduzir contrato compartilhado, migração com rollout, rollback próprio ou
auditoria, marque o critério correspondente com sua evidência.

Sem os cinco critérios formais, `varios passos: sim` recomenda plano; caso
contrário, execução direta. Critério ausente é uma lacuna,
nunca autorização para inferir uma rota. O porte da mudança e o número de
arquivos não substituem a matriz. Esses critérios escolhem o próximo workflow;
não são pré-requisitos para iniciar uma sabatina persistente.

Registre `autorizacao explicita: pendente` até haver autorização separada para
a rota. Confirmação do entendimento não autoriza plano, change ou código.
Apresente a rota calculada e ofereça as outras duas. Se o usuário preferir uma
alternativa, registre a escolha sem adulterar os critérios da matriz.

## Decomposição quando a rota for OpenSpec

Particione por resultado, contrato, owner, aceite, rollout e rollback próprios.
Quantidade de arquivos, requisitos ou tasks é apenas sinal para revisar o
recorte. Uma fonte pode produzir uma ou várias changes; não crie uma unidade
guarda-chuva sem implementação e aceite próprios.

A tabela usa IDs exclusivos, objetivo, aceite, rollout, rollback e dependências
sem ciclos. Cada `Qn` terminal pertence exatamente a uma unidade. O aceite
agregado cobre todas as unidades e a ordem de retomada respeita o DAG. Rotas
direta e de plano podem ter zero unidades formais.

## Validação final

Execute `sabatina --document <caminho-do-documento> --phase closed`. Corrija os
diagnósticos antes de entregar. Depois da validação, encerre com o handoff e a
solicitação de autorização ainda pendente; nenhum workflow começa sem ela.
