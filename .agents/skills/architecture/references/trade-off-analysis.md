# Trade-off Analysis

Use esta referência para comparar alternativas e produzir uma decisão que seja
auditável depois. O objetivo não é dar nota bonita, e sim deixar claro por que
uma opção venceu neste contexto.

## Rubrica mínima

Avalie cada alternativa pelos critérios que realmente importam para o caso:

- **Time to value:** quanto atrasa ou acelera a entrega segura.
- **Consistência/correção:** risco de conflito, duplicação ou estado incoerente.
- **Latência e UX:** impacto no caminho síncrono do usuário.
- **Isolamento de falha:** quanto um problema se espalha.
- **Operabilidade:** deploy, observabilidade, retries, runbooks, suporte.
- **Facilidade de mudança:** quão caro fica evoluir ou desfazer depois.
- **Custo total:** infraestrutura, coordenação entre times e dependências novas.

## Quadro de comparação

Use um quadro como este antes de recomendar:

```markdown
| Opção | Resolve o problema central? | Benefícios | Custos aceitos | O que fica mais difícil | Quando deixa de servir |
|---|---|---|---|---|---|
| A | sim/parcial/não | ... | ... | ... | ... |
| B | sim/parcial/não | ... | ... | ... | ... |
```

Evite falsa precisão. `alto/medio/baixo` ou `sim/parcial/não` costuma comunicar
melhor do que números arbitrários.

## Recomendação mínima

A decisão final precisa conter:

- problema real
- alternativas comparadas
- recomendação única
- trade-offs aceitos
- o que ficará mais difícil
- irreversibilidades ou custo de rollback
- mitigação dos custos mais relevantes
- revisit triggers objetivos

## ADR curto

Quando a decisão persistir além da conversa, use este shape:

```markdown
# ADR: <titulo curto e concreto>

## Status
Proposed | Accepted

## Contexto
- problema:
- constraints:
- atributos dominantes:

## Decisão
- escolhemos:
- por quê:

## Alternativas consideradas
- opção A:
- opção B:

## Consequências
- positivas:
- negativas:
- mitigação:

## Nota de migração/rollback
- como migrar sem big bang:
- o que custa desfazer:

## Revisit trigger
- rever quando:
```

Consulte também `../assets/adr-short-template.md` para um template reutilizável.

## Sinais de decisão fraca

- a opção vencedora não foi nomeada
- só existe uma alternativa descrita
- o texto fala em escalabilidade genérica sem atributo dominante
- não existe custo operacional explícito
- "depois a gente extrai" aparece sem revisit trigger claro
