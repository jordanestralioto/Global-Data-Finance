# Workflow Evals

Use estes cenários para revisar a consistência da skill após mudanças.

## Eval 1: gatilho informal deve acionar

**Prompt:** "Como separo esses módulos sem virar um Frankenstein?"

**Assertions:**

- [ ] identifica que a dúvida é arquitetural
- [ ] nomeia o problema real antes da solução
- [ ] compara pelo menos 2 alternativas

## Eval 2: detalhe local não deve acionar

**Prompt:** "Onde coloco esse hook do React?"

**Assertions:**

- [ ] não responde como se fosse arquitetura
- [ ] redireciona para uma skill mais adequada
- [ ] não propõe microservice, DDD ou boundary estrutural

## Eval 3: recomendação com trade-off explícito

**Prompt:** "Extraio um worker ou deixo essa importação no backend principal?"

**Assertions:**

- [ ] identifica atributos dominantes como latência, falha ou operabilidade
- [ ] nomeia a opção vencedora
- [ ] explicita pelo menos um custo operacional aceito
- [ ] descreve o que ficará mais difícil depois da escolha

## Eval 4: frontend vs backend

**Prompt:** "Essa regra de risco fica no frontend ou no backend?"

**Assertions:**

- [ ] discute source of truth e consistência
- [ ] evita decidir apenas por conveniência de implementação
- [ ] recomenda uma fronteira clara para a regra

## Eval 5: ADR obrigatório

**Prompt:** "Decidimos isolar billing em deploy separado e preciso registrar isso."

**Assertions:**

- [ ] inclui ADR curto
- [ ] ADR não contém placeholders em aberto
- [ ] existe nota de migração ou rollback
- [ ] existe revisit trigger objetivo

## Eval 6: CQRS rejeitado por exagero

**Prompt:** "Quero usar CQRS porque a dashboard está lenta."

**Assertions:**

- [ ] pede evidência do problema dominante
- [ ] compara CQRS com alternativa mais simples
- [ ] rejeita CQRS se a dor puder ser resolvida sem separar modelos
