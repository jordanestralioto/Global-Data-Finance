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
  Para auditoria ampla de segurança, use `vulnerability-scanner`; para RLS e
  outros recursos específicos de Supabase, use `supabase`. Não use para layout
  ou schema de banco puro.
---

# API Patterns

## Fundamentos não-óbvios

Absorva estes pontos antes de propor qualquer solução. Eles concentram os erros
mais caros, menos visíveis e mais comuns em APIs reais:

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
estabilizar códigos de erro e comunicar sunset antes de abrir consumo.

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

Se o problema tocar múltiplas áreas, leia todos os arquivos correspondentes antes
de propor solução.

## Procedimento

1. Identifique o estilo da API no repositório e os consumidores reais.
   Pergunte mentalmente: API pública? monorepo TS? frontend flexível? integração
   com terceiros? job assíncrono? streaming?

2. Identifique o shape operacional antes da primeira rota.
   Diferencie se o caso é síncrono, streaming, polling, callback, webhook receiver
   ou operação eventual. Não modele export, ETL ou provider lento como se fosse
   uma leitura simples.

3. Verifique o stack já existente antes de sugerir biblioteca ou convenção.
   Descubra qual validador o projeto usa (Pydantic, Zod, Joi), qual mecanismo de
   auth existe, como erros são centralizados e se OpenAPI/AsyncAPI já fazem parte
   do repositório.

4. Defina o contrato completo, não só a rota.
   Cubra pelo menos:

   - rota ou procedure
   - authn e authz
   - schema de input
   - shape de sucesso
   - shape de erro
   - paginação, filtro, sort e includes se houver listagem
   - rate limit
   - cache, preconditions e concorrência se houver escrita ou leitura cacheável
   - lifecycle/versionamento se houver consumidores externos

5. Para recursos mutáveis, escolha a estratégia de consistência explicitamente.
   Se múltiplos clientes podem editar o mesmo recurso, use `ETag`/`If-Match`,
   coluna de versão ou regra equivalente. Não deixe conflito implícito.

6. Para operações caras ou demoradas, escolha a estratégia assíncrona explicitamente.
   Se a resposta não pode ser confiavelmente concluída no request atual, use
   `202 Accepted` com recurso de status, polling previsível, webhook assinado
   ou stream com autenticação e revogação corretas.

7. Para APIs públicas ou compartilhadas, documente lifecycle antes de concluir.
   Adicionar campo opcional costuma ser seguro. Remover campo, alterar tipo,
   semântica de erro ou contrato de paginação é breaking change.

8. Se a tarefa envolver endpoints HTTP, OpenAPI, handlers, webhooks ou revisão
   estrutural, rode
   `python .agents/skills/api-patterns/scripts/validate_api.py <path>` como
   triagem heurística. Use o resultado como checklist inicial, não como
   veredito final. Leia `references/triage.md`: configure `--include` para
   convenções não descobertas e trate zero arquivos, leitura falha ou truncamento
   como cobertura incompleta. Registre os checks manuais que permanecem.

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
    pagination_filtering: <se aplicável>
    caching_concurrency: <etag, if-match, cache-control, version column>
    rate_limit: <escopo + custo>
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

______________________________________________________________________

## Evals de trigger

**Deve acionar:**

- "Como estruturo o endpoint de criação de workspace?"
- "Minha rota está retornando 403 mas o token está correto."
- "O CORS está bloqueando tudo no dev."
- "Como impeço GET /documents/{id} de expor dados de outro usuário?"
- "Preciso paginar os resultados da listagem."
- "Devo versionar minha API?"
- "Essa operação deveria responder 202?"
- "Como faço um webhook seguro?"
- "Preciso usar ETag ou If-Match aqui?"
- "Como depreco esse endpoint sem quebrar cliente?"
- "A Server Action que altera o pedido precisa validar ownership?"
- "Meu stream POST continua consumindo o provider depois de fechar a página."

**Não deve acionar:**

- "Audite auth, RLS e uploads deste app."
  *(near-miss: auditoria ampla de segurança, use `vulnerability-scanner`)*
- "Crie um componente React para exibir a lista de usuários."
  *(near-miss: consome API, mas não é design de API)*
- "Como configuro variáveis de ambiente no deploy?"
  *(near-miss: infraestrutura, não contrato)*
- "Escreva um teste unitário para a função de cálculo de desconto."
  *(fora do escopo)*
- "Meu useActionState está com espaçamento ruim e botão desalinhado."
  *(near-miss: layout de formulário, use `frontend-design`)*

______________________________________________________________________

## Evals de workflow

Os cenários abaixo são casos de avaliação, não resultados de execução. Registre
modelo/versão, prompts, transcrições e assertions ao medir o comportamento do
agente. Os testes Python da ferramenta não demonstram ganho do modelo com a skill.

### Cenário: BOLA/IDOR

**Entrada:** "Implementei `GET /invoices/{id}` que busca a fatura pelo ID no banco."

Assertions:

- [ ] resposta identifica ausência de validação de ownership
- [ ] sugere filtro por `user_id`, predicate de tenant, RLS ou middleware de ownership
- [ ] não sugere apenas checar se o recurso existe
- [ ] referencia `references/security-testing.md` ou aplica seus critérios

### Cenário: CORS

**Entrada:** "Frontend em `localhost:3000` não consegue chamar o backend em `localhost:8000`."

Assertions:

- [ ] verifica proxy local antes de sugerir headers
- [ ] se há proxy, sugere caminho relativo como solução primária
- [ ] não sugere `Access-Control-Allow-Origin: *` como primeira resposta

### Cenário: design de rota

**Entrada:** "Vou criar a rota `POST /createUser`."

Assertions:

- [ ] aponta que verbos não pertencem à rota REST
- [ ] sugere `POST /users` como alternativa
- [ ] referencia `references/rest.md` antes de detalhar a implementação

### Cenário: operação assíncrona

**Entrada:** "Meu endpoint de export demora até 60 segundos e às vezes estoura timeout."

Assertions:

- [ ] sugere `202 Accepted` ou stream apenas se fizer sentido para o caso
- [ ] propõe recurso de status, polling ou webhook
- [ ] trata retry e idempotência explicitamente
- [ ] referencia `references/async-webhooks.md` ou aplica seus critérios

### Cenário: concorrência otimista

**Entrada:** "Dois analistas podem editar o mesmo relatório."

Assertions:

- [ ] sugere `ETag` + `If-Match` ou coluna de versão
- [ ] distingue conflito de estado de precondition desatualizada
- [ ] referencia `references/caching-concurrency.md` ou aplica seus critérios

### Cenário: webhook receiver

**Entrada:** "Vou expor `POST /webhooks/provider` para receber eventos do gateway."

Assertions:

- [ ] exige assinatura ou esquema forte equivalente
- [ ] menciona deduplicação por event id
- [ ] menciona tolerância de replay/timestamp quando aplicável
- [ ] não trata webhook como endpoint público comum sem trust boundary especial

### Cenário: action exposta pelo framework

**Entrada:** "A action recebe `order_id` e atualiza o pedido; a página já exige login."

Assertions:

- [ ] identifica se a action pode ser invocada diretamente pelo transporte do framework
- [ ] exige authn e ownership/tenant binding na action ou serviço de dados chamado
- [ ] valida input com o mecanismo do projeto, sem impor biblioteca ou linguagem
- [ ] verifica rate limit, retry/idempotência e proteção de origem/CSRF aplicáveis
- [ ] referencia `references/server-functions.md` ou aplica seus critérios

### Cenário: streaming com POST e cancelamento

**Entrada:** "Envio um POST e leio SSE via fetch; fechar a aba não cancela o provider."

Assertions:

- [ ] distingue fetch/POST de EventSource e não promete reconexão automática do fetch
- [ ] propõe propagar cancelamento ao upstream e liberar recursos/reservas
- [ ] define política de retomada e deduplicação antes de repetir um POST
- [ ] trata buffering conforme o proxy efetivamente utilizado
- [ ] referencia `references/streaming.md` ou aplica seus critérios

### Cenário: triagem em projeto de outra linguagem

**Entrada:** "Revise os handlers Go em internal/http; o scanner não achou arquivos."

Assertions:

- [ ] ajusta o alvo ou `--include` em vez de reescrever o backend em Python
- [ ] não interpreta zero arquivos ou truncamento como aprovação
- [ ] distingue evidência lexical de controles efetivamente implementados
- [ ] usa os testes e validadores nativos do consumidor para comprovar comportamento

______________________________________________________________________

## Checklist antes de entregar

- [ ] Estilo da API identificado e arquivo de referência correspondente lido
- [ ] Shape operacional identificado: sync, async, stream, webhook ou polling
- [ ] Rotas usam substantivos, não verbos, quando o estilo for REST
- [ ] Shape de sucesso respeita o contrato existente; erros são sanitizados
- [ ] Endpoints com `{id}` validam ownership, tenant binding ou policy equivalente
- [ ] CORS investigado via topologia de proxy antes de sugerir headers
- [ ] Biblioteca de validação do projeto verificada antes de recomendar uma
- [ ] Rate limit verificado antes do trabalho caro começar
- [ ] Operações críticas tratam retry e idempotência explicitamente
- [ ] Recursos mutáveis com múltiplos atores têm estratégia de concorrência definida
- [ ] Operações longas têm contrato assíncrono quando necessário
- [ ] APIs públicas ou compartilhadas têm regra de versionamento/deprecation definida
- [ ] Actions/functions remotas têm controles no ponto de entrada ou serviço chamado
- [ ] Streaming define cancelamento upstream, limites, cleanup e retomada quando aplicável
- [ ] Triagem registra arquivos omitidos e verificações que dependem de leitura contextual
