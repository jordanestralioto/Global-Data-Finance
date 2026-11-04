---
name: architecture
description: >-
  Use para decisões estruturais de software com trade-offs reais. Ative quando o
  usuário perguntar "isso fica onde na arquitetura?", "separo em módulos?", "crio outro
  serviço?", "vale usar fila?", "monólito ou serviço?", "isso está acoplado
  demais?", "preciso de ADR" ou "como organizo essa responsabilidade?". Cobre
  fronteiras, ownership, consistência, deploy, operabilidade e custo de mudança.
  Não use para bugs isolados, refatorações locais delimitadas, escolha de
  índices, layout visual ou planos simples sem decisão arquitetural.
---

# Architecture

## Fundamentos não-óbvios

Decisão arquitetural não é sinônimo de escolher framework, banco ou buzzword.
Ela existe quando a conversa mexe em fronteiras, ownership, deploy, consistência,
blast radius, operabilidade, contratos compartilhados ou custo de evolução.

O melhor critério raramente é "o que times maiores costumam usar". Tamanho de
equipe, volume e maturidade influenciam a análise, mas não decidem sozinhos.
Escolha a menor mudança estrutural que resolva o risco dominante.

Arquitetura boa explicita custo operacional. Se uma alternativa adiciona fila,
orquestração, tracing, múltiplos deploys ou reconciliação eventual, isso deve
aparecer na recomendação final em vez de ficar implícito.

Simplicidade é default, não dogma. Adiar complexidade faz sentido quando o risco
principal continua coberto; ignorar falha, latência, consistência ou isolamento
porque "depois a gente vê" costuma apenas empurrar dívida para produção.

Recomendação arquitetural boa escolhe um vencedor e nomeia o que fica mais difícil
depois da escolha. Se a resposta não diz o que piora, ela está incompleta.

## Roteamento para referências

Leia apenas os arquivos relevantes para a decisão em mãos:

| Problema                                                      | Arquivo                            |
| ------------------------------------------------------------- | ---------------------------------- |
| Descobrir contexto, constraints e atributos de qualidade      | `references/context-discovery.md`  |
| Escolher padrões e fronteiras por sintomas e trade-offs       | `references/pattern-selection.md`  |
| Consultar padrões comuns, custos operacionais e disqualifiers | `references/patterns-reference.md` |
| Estruturar comparação, decisão, mitigação e ADR               | `references/trade-off-analysis.md` |
| Ver o contrato esperado da resposta final                     | `references/output-contract.md`    |
| Validar manualmente a consistência da skill                   | `references/workflow-evals.md`     |
| Ver exemplos concretos de decisões parecidas                  | `references/examples.md`           |

Se o problema tocar HTTP, handlers, authz, status codes ou contratos de API, use
`api-patterns`. Se tocar schema, tipos de dados, constraints, migrations, indices,
consistencia ou ownership, use `database-design`. Se virar RLS, grants, pooling,
service role ou particularidades de Supabase/Postgres, use
`supabase`. Se a dúvida for organização local de componente,
hook ou módulo, use `modularizar` ou `frontend-design`.

## Procedimento

1. Classifique se a dúvida é realmente arquitetural antes de responder.
   Pergunte mentalmente se a decisão altera fronteiras, ownership, estratégia de
   deploy, consistência, falha, observabilidade, contratos compartilhados ou custo
   de mudança. Se não alterar nada disso, redirecione para a skill mais apropriada.

2. Descubra o contexto antes do padrão.
   Reúna problema real, sintomas, restrições, stack já existente, pressão de prazo,
   atributos de qualidade relevantes e o que precisa continuar fácil depois da
   mudança. Use `references/context-discovery.md`.

3. Escolha 3 a 5 critérios de avaliação antes de escolher alternativa.
   Exemplos: latência, consistência, custo operacional, isolamento de falha,
   facilidade de mudança, segurança, compliance, observabilidade e custo de deploy.
   Não avalie tudo com o mesmo peso.

4. Compare pelo menos 2 alternativas reais.
   Uma delas pode ser explicitamente a opção mais simples. Se o contexto impuser
   um caminho único, registre por que a decisão já veio amarrada e quais custos
   ainda precisam ser aceitos.

5. Explicite o custo operacional da alternativa escolhida.
   Fila, retries, eventual consistency, tracing distribuído, coordenação entre
   times, múltiplos repositórios, contrato público e migração incremental precisam
   aparecer como custo concreto, não como abstração elegante.

6. Recomende uma direção clara.
   A resposta final deve dizer qual opção vence, por que vence neste contexto, o
   que fica mais difícil depois dela, quais irreversibilidades foram aceitas e em
   que sinais a decisão deve ser revisitada.

7. Produza um ADR curto quando a decisão sobreviver à conversa.
   Se a escolha afetar mais de um owner, mais de um deploy, contrato público ou
   direção estrutural duradoura, emita também um ADR curto usando
   `references/trade-off-analysis.md` e `assets/adr-short-template.md`.

8. Se o usuário pedir implementação, use o contrato desta skill como checklist
   interno antes de editar código. Não pule direto para tecnologia específica sem
   fechar o problema estrutural.

## Anti-patterns recorrentes

- Escolher microservices porque o sistema "vai crescer" sem evidência de fronteiras
  estáveis, necessidades de deploy independente ou benefício real de isolamento.
- Escolher fila para esconder operação síncrona mal modelada, sem contrato de job,
  idempotência, observabilidade e estratégia de falha.
- Escolher CQRS ou event-driven porque soa escalável, sem divergência real entre
  modelo de escrita e leitura, ou sem tolerância operacional para consistência eventual.
- Empurrar regra crítica para frontend quando ela define source of truth, segurança,
  compliance ou invariantes de negócio.
- Prescrever framework cedo demais. Framework entra depois que a fronteira, o fluxo
  e os atributos de qualidade já estão claros.

## Formato de saída recomendado

Quando a conversa pedir desenho, revisão ou decisão arquitetural, prefira responder
com o shape abaixo. Adapte a forma para prosa se o usuário pedir, mas mantenha
essas informações completas.

```yaml
architecture_decision:
  scope: <qual fronteira está sendo decidida>
  problem: <problema real, não apenas sintoma>
  context_and_constraints:
    - <stack atual, prazo, carga, compliance, ownership, legado>
  quality_attributes:
    - attribute: <latency|consistency|operability|changeability|cost|security>
      importance: <high|medium|low>
      note: <por que importa aqui>
  alternatives:
    - option: <nome da alternativa>
      fit: <quando esta opção funciona bem>
      benefits:
        - <benefício concreto>
      costs:
        - <trade-off ou custo operacional>
      disqualifiers:
        - <quando ela deixa de ser boa opção>
  recommendation:
    choose: <opção vencedora>
    because:
      - <razão ligada aos critérios escolhidos>
    trade_offs_accepted:
      - <custo aceito conscientemente>
    harder_after_choice:
      - <o que ficará mais difícil depois>
    irreversibilities:
      - <ponto de não-retorno ou custo alto de rollback>
    revisit_triggers:
      - <sinal objetivo para reavaliar a decisão>
  adr:
    required: <yes|no>
    title: <preencher se yes>
```

Consulte `references/output-contract.md` para o contrato completo e os critérios de
qualidade da resposta.

## Exemplos

### Caso positivo — isolamento sem overengineering

**Entrada:** "O módulo de importação trava o backend quando o provider demora. Extraio
um worker com fila ou deixo no app principal?"
**Saída esperada:** identificar atributos dominantes como latência, isolamento de
falha, retries, operabilidade e custo de deploy; comparar pelo menos job interno,
worker isolado e serviço separado; recomendar a menor fronteira que resolva o risco
principal; incluir revisit trigger e ADR curto se a decisão for duradoura.

### Caso positivo — fronteira de responsabilidade

**Entrada:** "Essa regra de cálculo de risco fica no frontend ou no backend?"
**Saída esperada:** avaliar source of truth, sensibilidade da regra, necessidade
de consistência, custo de duplicação e impacto em UX; recomendar backend para a
invariante central e frontend apenas para projeção ou visualização se fizer sentido.

### Caso negativo

**Entrada:** "Onde coloco esse hook do React no meu repositório?"
**Por quê não:** decisão local de organização e implementação. Direcione para
`modularizar`, `frontend-design` ou `react-performance`.

## Evals de trigger

**Deve acionar:**

- "Como separo esses módulos sem virar um Frankenstein?"
- "Precisamos separar o worker do backend principal?"
- "Vale usar fila aqui ou estou complicando demais?"
- "Isso fica no backend ou no frontend?"
- "Devo manter monólito modular ou extrair serviço?"
- "Preciso de um ADR para essa decisão."
- "Essa arquitetura está acoplada demais e difícil de evoluir."
- "Essa estrutura hexagonal está certa?"

**Não deve acionar:**

- "Qual função do pandas eu uso para isso?" (Problema de linguagem/biblioteca)
- "Como eu otimizo essa query SQL?" (Problema de banco de dados, use `database-design`)
- "Minha policy RLS no Supabase esta lenta e preciso revisar grants." (Problema especifico de engine, use `supabase`)
- "Onde coloco o middleware no Express?" (Problema de API/framework, use `api-patterns`)
- "Esse componente React re-renderiza demais." (Problema de frontend/performance)
- "Escreve um hook para consumir esse endpoint." (Implementação local, não arquitetura)

## Assets

- `assets/adr-short-template.md`: template enxuto para decisões persistentes, com
  contexto, decisão, trade-offs, consequências e revisit trigger.
