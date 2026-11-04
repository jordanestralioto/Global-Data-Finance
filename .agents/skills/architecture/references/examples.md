# Architecture Examples

Exemplos abaixo mostram o tipo de decisão que esta skill deve conduzir.

## Exemplo 1: extrair serviço ou manter no deploy atual

**Entrada:** "Nosso gerador de relatórios trava o app em horários de pico. Extraio
um serviço com fila ou crio um worker separado?"

**Direção esperada:** comparar job interno, worker isolado e serviço separado.
Se o problema dominante for latência e isolamento de falha, mas não houver motivo
forte para contrato organizacional novo, recomendar worker isolado antes de um
microservice completo.

## Exemplo 2: fronteira frontend/backend

**Entrada:** "O score de elegibilidade do usuário deve ser calculado no frontend
para ficar mais rápido?"

**Direção esperada:** identificar source of truth, sensibilidade da regra, risco
de divergência e necessidade de auditoria. Regra crítica tende a ficar no backend;
frontend pode exibir explicação, estado derivado ou cache visual.

## Exemplo 3: síncrono vs assíncrono

**Entrada:** "O upload chama três providers e pode levar 25s. Mantenho tudo em
uma requisição ou devolvo status depois?"

**Direção esperada:** se o usuário tolera conclusão posterior, recomendar fluxo
assíncrono com job rastreável, retries idempotentes e estado observável em vez de
request síncrono frágil.

## Exemplo 4: modular monolith vs microservices

**Entrada:** "Billing e catálogo mudam em ritmos diferentes. Isso já pede dividir
em serviços?"

**Direção esperada:** avaliar se a dor principal é deploy, ownership, blast radius
ou apenas acoplamento interno. Se boundary e operação distribuída ainda não estão
claras, recomendar monólito modular com contratos internos antes de extrair serviço.

## Exemplo 5: CQRS rejeitado

**Entrada:** "Quero usar CQRS porque a tela de dashboard ficou lenta."

**Direção esperada:** rejeitar CQRS por default se a dor puder ser resolvida com
query otimizada, cache, read model local ou materialized view. CQRS só entra quando
leitura e escrita realmente exigem modelos distintos.

## Exemplo 6: ADR curto resultante

**Entrada:** "Decidimos isolar o processamento de importação em worker próprio.
Preciso registrar isso."

**Saída esperada:**

```markdown
# ADR: isolar processamento de importacao em worker

## Status
Accepted

## Contexto
- problema: provider lento derruba latencia do backend principal
- constraints: manter stack atual e evitar contrato distribuido desnecessario
- atributos dominantes: isolamento de falha, operabilidade, custo de mudanca

## Decisão
- escolhemos: worker isolado com job assíncrono
- por quê: reduz impacto no request principal sem exigir boundary de microservice

## Alternativas consideradas
- job no mesmo processo: mais simples, mas falha continua competindo com o app
- microservice completo: mais autonomia, custo operacional alto demais agora

## Consequências
- positivas: melhor isolamento e retries dedicados
- negativas: mais observabilidade e reconciliação
- mitigação: contract de job, logs estruturados e revisit trigger

## Nota de migração/rollback
- migrar por feature flag e fila única
- rollback custa baixo porque contrato externo não muda

## Revisit trigger
- rever se o worker exigir deploy independente frequente ou ownership próprio
```
