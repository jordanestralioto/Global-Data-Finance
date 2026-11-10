# Output Contract

Esta é a fonte única do esquema e das regras de uma decisão concluída. Durante
descoberta, responda com fatos, lacunas e recomendação provisória; não invente uma
causa comprovada ou uma decisão aceita para preencher o contrato.

## Contrato mínimo

Uma resposta arquitetural boa precisa entregar:

- **scope:** qual fronteira ou decisão está sendo avaliada
- **problem:** causa raiz, não apenas sintoma
- **context_and_constraints:** stack, prazo, legado, compliance, ownership e evidência; premissas identificadas
- **quality_attributes:** 3 a 5 atributos realmente relevantes
- **alternatives:** pelo menos 2 opções reais, salvo a exceção comprovada abaixo
- **alternatives_constraint:** razão e evidência de caminho único; `null` nos demais casos
- **recommendation:** uma opção vencedora
- **trade_offs_accepted:** custos aceitos conscientemente
- **harder_after_choice:** o que ficará mais difícil depois
- **irreversibilities:** ponto de não-retorno ou custo alto de desfazer
- **revisit_triggers:** sinais objetivos para reavaliar
- **adr:** necessidade e status do registro, respeitando a fase do fluxo ativo

## Shape recomendado

```yaml
architecture_decision:
  scope: <fronteira ou escolha estrutural>
  problem: <causa raiz>
  context_and_constraints:
    - <constraint 1>
    - <constraint 2>
  quality_attributes:
    - attribute: <nome>
      importance: <high|medium|low>
      note: <por que importa e que evidência ou premissa sustenta a avaliação>
  alternatives_constraint: null
  alternatives:
    - option: <nome>
      fit: <quando funciona>
      benefits:
        - <benefício>
      costs:
        - <custo ou trade-off>
      disqualifiers:
        - <quando deixa de ser boa opção>
  recommendation:
    choose: <opção vencedora>
    because:
      - <motivo 1>
      - <motivo 2>
    trade_offs_accepted:
      - <custo aceito>
    harder_after_choice:
      - <dificuldade nova>
    irreversibilities:
      - <ponto difícil de desfazer>
    revisit_triggers:
      - <sinal para reavaliar>
  adr:
    required: <yes|no>
    status: <not_required|deferred|proposed|accepted>
    title: <preencher se yes>
```

## Regras de qualidade

- `alternatives` contém pelo menos 2 opções reais, incluindo a mais simples viável.
  Uma única opção exige `alternatives_constraint.reason` e
  `alternatives_constraint.evidence` preenchidos: a restrição deve excluir as
  outras opções no escopo e a evidência deve apontar para a decisão, contrato ou
  requisito que a impõe. Preferência por tecnologia ou falta de investigação não
  prova caminho único. Não fabrique uma opção inviável para completar a lista.
- Mesmo com caminho único, preserve custos, o que piora e sinais para reabrir a escolha.
- `recommendation.choose` precisa apontar para um vencedor explícito.
- `trade_offs_accepted` não pode estar vazia.
- `harder_after_choice` não pode ser omitido.
- `revisit_triggers` deve ser observável; evite frases vagas como "quando crescer".
- Se verificabilidade ou isolamento de mudança forem dominantes, as notas comparam
  checagens locais, dependências externas e contexto compartilhado entre opções.
  Comandos vêm do projeto; estimativas e verificações não executadas ficam explícitas.
- `adr.status=not_required` corresponde a `adr.required=no`. Quando o ADR for
  necessário, preencha o título; use `deferred` enquanto o fluxo ativo adiar sua
  emissão e indique o evento que a libera. Nos demais casos, inclua o registro ou
  referência existente, sem placeholders, com status `proposed` ou `accepted`.

## Quando exigir ADR

Exija ADR curto quando a decisão:

- atravessa mais de um deploy ou owner
- muda contrato público ou boundary estável
- adiciona custo operacional duradouro
- tende a ser citada de novo em implementação futura

`required=yes` identifica a necessidade do registro, sem antecipar sua emissão.
Siga `decision-handoffs.md`: sabatina aberta adia ADR; sabatina fechada usa seus
rascunhos sem número; fora dela, prevalecem o template e o lifecycle locais.
Uma decisão proposta só passa a aceita com evidência de confirmação e autorização
do lifecycle. O contrato de resposta não concede permissão para criar arquivos.

Se o usuário preferir resposta em prosa, preserve esse contrato internamente e
renderize os campos como seções narrativas.
