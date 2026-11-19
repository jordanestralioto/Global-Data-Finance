---
name: api-patterns
description: >-
  Use para projetar, corrigir ou revisar contratos e rotas REST, GraphQL, tRPC
  e actions/functions expostas pelo framework.
  Ative com "como faço esse endpoint?", "minha rota dá 403", "CORS bloqueou",
  "webhook seguro?", "qual status code?", "como pagino?" ou "como bloqueio
  acesso a recurso alheio nesta rota?". Cobre autenticação, BOLA/IDOR, rate
  limit, OpenAPI, versionamento, SSE/polling, cancelamento de streams, jobs,
  Server Actions e cache HTTP (ETag/If-Match).
  Para auditoria ampla de segurança ou de RLS, use `vulnerability-scanner`.
  Não use para layout ou schema de banco puro.
---

# API Patterns

## Fundamentos não-óbvios

Estes pontos concentram os erros mais caros e menos visíveis em APIs reais:

**CORS e topologia de proxy:** inspecione a URL real, preflight, credenciais e
topologia antes de mudar headers. Se o projeto já usa proxy de mesma origem,
prefira o caminho relativo previsto por ele. Sem esse proxy, configure as origens
permitidas conforme o contrato; não presuma que toda falha de CORS tem a mesma causa.

**Envelopes e erro estável:** em APIs HTTP, arrays brutos na raiz quebram contratos
quando metadados precisarem ser adicionados. Prefira `{ "data": ..., "meta": ... }`
em novos contratos JSON quando metadados forem necessários, preservando APIs
existentes e formatos nativos de streaming. Para erros, siga o contrato do estilo:
RFC 9457 em REST/HTTP, `errors[]` sanitizado em GraphQL e `TRPCError` sanitizado em tRPC.

**Idempotência não é opcional em POST crítico:** criação de chave, pagamento,
disparo de job, replay de webhook e qualquer escrita sujeita a retry precisam
ser seguras para repetição. Use `Idempotency-Key`, chave natural forte ou
deduplicação persistida no backend.

**BOLA / IDOR:** `GET /resource/{id}` não pode apenas buscar por ID. A query,
policy, repositório ou middleware precisa validar que o caller tem acesso àquele
recurso específico. Nunca trate "o registro existe" como prova de autorização.

**Concorrência otimista:** em recursos mutáveis com múltiplos atores, `PATCH`
sem proteção perde atualização silenciosamente. Use `ETag` + `If-Match`, version
column ou estratégia equivalente. Prefira `412 Precondition Failed` quando o
cliente envia precondition desatualizada.

**Operações longas pedem decisão operacional:** compare duração e custo com o
budget do cliente, proxy e servidor. Escolha sync, `202 Accepted` com job, polling,
callback ou stream conforme o caso. Uma menção a provider não implica job, e `202`
não substitui idempotência nem aceitação durável do trabalho.

**Função de servidor pode ser entrada remota:** actions/functions expostas pelo
framework precisam dos mesmos controles de uma rota. Auth na página e a ausência
de uma URL escrita manualmente não comprovam proteção da action.

**Princípios são portáveis; sintaxe é do projeto:** adapte ao framework e à
linguagem existentes. Use o mecanismo de validação, auth e transação do consumidor;
não imponha Zod, um ORM, Python no backend ou uma convenção de rotas específica.

**Lifecycle e compatibilidade importam desde o início:** APIs quebram mais por
mudança silenciosa do que por bug explícito. Defina como versionar, deprecar,
estabilizar códigos de erro e comunicar sunset antes de abrir consumo. Adicionar
campo opcional costuma ser seguro; remover campo ou alterar tipo, semântica de
erro ou contrato de paginação é breaking change.

______________________________________________________________________

## Roteamento para referências

Os caminhos abaixo são relativos a esta pasta. Leia apenas os arquivos relevantes
para o problema em mãos:

| Problema                                                                          | Arquivo                             |
| --------------------------------------------------------------------------------- | ----------------------------------- |
| Design de rotas, substantivos vs verbos, métodos HTTP, status codes, query params | `references/rest.md`                |
| Versionamento, breaking changes, deprecation, sunset                              | `references/lifecycle.md`           |
| Schema de queries, mutations, subscriptions e segurança GraphQL                   | `references/graphql.md`             |
| Tipagem end-to-end, routers, procedures, middleware tRPC                          | `references/trpc.md`                |
| JWT, API Keys, OAuth, sessão, trust boundary                                      | `references/auth.md`                |
| Rate limiting, throttling, bypass patterns, custo diferenciado                    | `references/rate-limiting.md`       |
| Paginação, envelopes, formatos de resposta e erro                                 | `references/response.md`            |
| ETag, `If-Match`, `If-None-Match`, `304`, `412`, caching HTTP                     | `references/caching-concurrency.md` |
| `202 Accepted`, jobs, polling, webhooks, assinatura e deduplicação                | `references/async-webhooks.md`      |
| CORS, BOLA/IDOR, OWASP API Top 10, testes negativos de segurança                  | `references/security-testing.md`    |
| Escolha entre REST, GraphQL, tRPC e estilos adjacentes                            | `references/api-style.md`           |
| Exemplos de implementação completos                                               | `references/examples.md`            |
| Server Actions/Functions, actions de formulário e entradas geradas pelo framework | `references/server-functions.md`    |
| SSE/EventSource, stream via fetch/POST, cancelamento, reconexão e buffering       | `references/streaming.md`           |
| Executar a ferramenta Python, ajustar descoberta e interpretar limites/exit codes | `references/triage.md`              |

Se o problema tocar várias áreas, abra só as referências das decisões que ainda
estão em aberto; os fundamentos acima já cobrem os pontos comuns.

## Procedimento

1. Identifique o estilo da API no repositório e os consumidores reais.
   Pergunte mentalmente: API pública? monorepo TS? frontend flexível? integração
   com terceiros? job assíncrono? streaming?

2. Identifique o shape operacional antes da primeira rota.
   Diferencie se o caso é síncrono, streaming, polling, callback, webhook receiver
   ou operação eventual. Não modele export, ETL ou provider lento como se fosse
   uma leitura simples. Se a resposta não pode ser concluída com segurança no
   request atual, use `202 Accepted` com recurso de status, polling previsível,
   webhook assinado ou stream com autenticação e revogação corretas. Em stream,
   defina cancelamento upstream, limites, cleanup e retomada.

3. Verifique o stack já existente antes de sugerir biblioteca ou convenção.
   Descubra qual validador o projeto usa (Pydantic, Zod, Joi), qual mecanismo de
   auth existe, como erros são centralizados e se OpenAPI/AsyncAPI já fazem parte
   do repositório.

4. Defina o contrato completo, não só a rota: cada campo de `contract` no
   formato de saída abaixo. Em recurso mutável com vários atores, a estratégia
   de concorrência é explícita; rate limit atua antes de o trabalho caro
   começar; lifecycle é obrigatório quando há consumidores externos.

5. Opcionalmente, em revisão estrutural de vários endpoints, handlers, webhooks
   ou OpenAPI, rode
   `python .agents/skills/api-patterns/scripts/validate_api.py <path>` como
   triagem heurística, não como veredito. Zero arquivos, leitura falha ou
   truncamento significam cobertura incompleta; registre os checks manuais que
   permanecem. Consulte `references/triage.md` só para ajustar `--include` ou
   interpretar limites e exit codes.

______________________________________________________________________

## Formato de saída recomendado

Quando a conversa pedir desenho ou revisão de API, prefira responder neste shape:

```yaml
api_design_review:
  style: <REST|GraphQL|tRPC|hybrid>
  consumers: <browser shell, public integration, internal service, etc.>
  operation_shape: <sync|async-job|sse|webhook|polling>
  contract:
    route_or_procedure: <rota, resolver ou procedure>
    auth: <bearer, session, api key, public>
    authorization: <ownership, role, tenant binding, policy>
    input: <schema e validações principais>
    success: <status/body/eventos>
    errors: <codes + contrato sanitizado>
    pagination_filtering: <paginação, filtro, sort e includes, se houver listagem>
    caching_concurrency: <etag, if-match, cache-control, version column>
    rate_limit: <escopo + custo, aplicado antes do trabalho caro>
    lifecycle: <versioning, deprecation, sunset>
  negative_tests:
    - <teste de authz>
    - <teste de validação>
    - <teste de rate limit/custo>
    - <teste de precondition ou retry>
  notes:
    - <trade-off ou risco remanescente>
```

Se o usuário pediu implementação, use esse shape como checklist interno e então
edite o código diretamente.

## Scripts

- `scripts/validate_api.py`: CLI de triagem textual de código em várias linguagens
  e de contratos OpenAPI; usa apenas a biblioteca padrão do Python.
- `scripts/api_checks/`: módulos de descoberta, evidência, código e OpenAPI.
  A ferramenta não executa a aplicação nem prova authz, idempotência ou concorrência.

## Exemplos

### Caso positivo — BOLA detectado e corrigido

**Entrada:** "Implementei `GET /api/orders/{id}` que busca o pedido pelo ID."
**Saída esperada:** apontar ausência de validação de ownership; sugerir predicate
por `order_id` e `user_id` ou policy equivalente no repositório.

### Caso positivo — operação longa convertida para job

**Entrada:** "Tenho `POST /exports` que chama provider externo e pode levar 40s."
**Saída esperada:** sugerir `202 Accepted`, recurso `/exports/{job_id}`, status
de job, polling ou webhook assinado; não manter request bloqueado sem necessidade.

### Caso positivo — atualização protegida por precondition

**Entrada:** "Dois usuários podem editar a mesma carteira ao mesmo tempo."
**Saída esperada:** sugerir `ETag` + `If-Match` ou version column, com erro de
precondition quando o cliente usar versão obsoleta.

### Caso negativo — CORS resolvido errado

**Entrada:** "Estou com erro de CORS, vou adicionar `Access-Control-Allow-Origin: *`."
**Por quê não:** solução permissiva que ignora topologia local, credenciais e proxy.
Verifique primeiro se o frontend deveria chamar caminho relativo.

### Caso negativo — webhook sem autenticação

**Entrada:** "O provider chama `POST /webhooks/payment` e vou confiar só no IP."
**Por quê não:** IP não é prova suficiente. Exija assinatura, timestamp tolerável,
deduplicação por event id e resposta idempotente.
