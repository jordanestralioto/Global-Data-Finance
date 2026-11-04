# Pattern Selection

Escolha padrões por problema dominante e atributo de qualidade, não por moda,
organograma ou tamanho de time isolado.

## Escada de simplicidade

Suba um degrau por vez:

1. manter dentro do módulo atual
2. modularizar dentro do mesmo deploy
3. mover para job interno ou worker isolado
4. separar deploy ou ownership
5. distribuir por múltiplos serviços

Se um degrau menor já resolve o risco dominante, prefira o menor.

## Sintoma para direção provável

| Sintoma dominante                                                 | Direções prováveis                                   | Só escolha se...                                                             | Sinal de overengineering                              |
| ----------------------------------------------------------------- | ---------------------------------------------------- | ---------------------------------------------------------------------------- | ----------------------------------------------------- |
| Deploys e mudanças locais quebram áreas sem relação               | modular monolith, boundary explícita, pacote interno | a dor principal é acoplamento de mudança e ownership                         | extrair serviço sem precisar de deploy independente   |
| Operação longa ou instável trava request síncrono                 | job assíncrono, worker, fila                         | o usuário tolera conclusão posterior e há estratégia de retries/idempotência | usar fila sem contrato de job nem observabilidade     |
| Partes diferentes precisam de isolamento forte de falha ou escala | worker isolado, serviço separado                     | o ganho operacional supera tracing, coordenação e custo de deploy            | dizer "vai escalar no futuro" sem evidência atual     |
| Modelo de leitura diverge muito do de escrita                     | projeção dedicada, CQRS seletivo                     | há consultas caras ou view denormalizada recorrente                          | aplicar CQRS em CRUD comum                            |
| Domínio tem invariantes densas e risco alto de regra duplicada    | domain model, boundary clara, DDD-lite               | a lógica realmente concentra valor e conflito                                | usar DDD completo para fluxo simples                  |
| Dependência externa domina o desenho                              | anti-corruption layer, adapter, ports/adapters       | a integração muda, falha ou impõe vocabulário estranho                       | criar abstração genérica sem múltiplos adapters reais |

## Decisões clássicas

### Quando manter monólito modular

Prefira monólito modular quando a principal dor é acoplamento interno, mas os
benefícios de deploy separado ainda são menores do que o custo de observabilidade,
coordenação e compatibilidade entre serviços.

### Quando isolar worker

Prefira worker isolado quando a operação é lenta, falha de modo independente ou
precisa de retries próprios, mas o domínio ainda não pede uma boundary organizacional
completa.

### Quando separar serviço

Considere serviço separado quando houver combinação de:

- necessidade real de deploy independente
- ritmo de mudança diferente
- risco relevante de blast radius
- contrato explícito entre partes
- operação que o time sabe sustentar

### Quando aceitar consistência eventual

Aceite consistência eventual quando a experiência do usuário e o domínio suportam
atraso controlado, reconciliação e comunicação clara do estado intermediário.
Sem isso, o "assíncrono" vira bug difícil de explicar.

### Quando CQRS ou event-driven se justificam

Use CQRS ou eventos quando a divergência de leitura e escrita é estrutural, não
cosmética. O ganho precisa pagar o custo de versionar eventos, observar pipelines,
reprocessar projeções e lidar com ordem, duplicidade e atraso.

## Perguntas de corte

- Qual alternativa menor resolve 80% do problema?
- O custo de operação da opção complexa cabe na maturidade atual do time?
- A decisão melhora o atributo dominante ou só muda o formato do código?
- Existe plano de migração incremental ou a troca exige big bang?
