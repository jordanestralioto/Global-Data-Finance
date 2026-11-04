# Output Contract

Este arquivo define o que uma resposta da skill `architecture` precisa conter para
ser considerada completa.

## Contrato mínimo

Uma resposta arquitetural boa precisa entregar:

- **scope:** qual fronteira ou decisão está sendo avaliada
- **problem:** causa raiz, não apenas sintoma
- **context_and_constraints:** stack atual, prazo, legado, compliance, ownership
- **quality_attributes:** 3 a 5 atributos realmente relevantes
- **alternatives:** pelo menos 2 opções reais
- **recommendation:** uma opção vencedora
- **trade_offs_accepted:** custos aceitos conscientemente
- **harder_after_choice:** o que ficará mais difícil depois
- **irreversibilities:** ponto de não-retorno ou custo alto de desfazer
- **revisit_triggers:** sinais objetivos para reavaliar
- **adr:** obrigatório quando a decisão persistir além da task

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
      note: <por que importa>
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
    title: <preencher se yes>
```

## Regras de qualidade

- `alternatives` não pode ter apenas uma opção.
- `recommendation.choose` precisa apontar para um vencedor explícito.
- `trade_offs_accepted` não pode estar vazia.
- `harder_after_choice` não pode ser omitido.
- `revisit_triggers` deve ser observável; evite frases vagas como "quando crescer".
- Se `adr.required=yes`, o título e o resumo do ADR precisam vir preenchidos, sem placeholders.

## Quando exigir ADR

Exija ADR curto quando a decisão:

- atravessa mais de um deploy ou owner
- muda contrato público ou boundary estável
- adiciona custo operacional duradouro
- tende a ser citada de novo em implementação futura

Se o usuário preferir resposta em prosa, preserve esse contrato internamente e
renderize os campos como seções narrativas.
