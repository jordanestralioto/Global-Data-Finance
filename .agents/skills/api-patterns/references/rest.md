# REST Principles

> Recursos com substantivos, métodos HTTP com semântica correta.

## Naming de rotas

- Use substantivos, nunca verbos — `/workspaces`, não `/getWorkspaces`
- Plural para coleções — `/users`, não `/user`
- Lowercase com hífens — `/user-profiles`, não `/userProfiles`
- Aninhe para relacionamentos proprietários — `/users/123/posts`
- Máximo 3 níveis de aninhamento — mais que isso indica necessidade de recurso próprio

```
✅ /api/v1/workspaces
✅ /api/v1/workspaces/ws_123/members
✅ /api/v1/conversations/conv_abc/messages

❌ /api/v1/getWorkspace
❌ /api/v1/workspace/member/message/attachment/file
❌ /api/v1/workspaceMembers
```

## Query contract

- Use query params explícitos e previsíveis: `page`, `per_page`, `cursor`, `sort`,
  `order`, `filter[status]`, `include`, `fields[resource]`
- Defina allow-list para filtros e sort; não repasse colunas arbitrárias do cliente
- Escolha ordenação padrão estável para paginação confiável
- Seja consistente entre rotas irmãs; não invente nomes diferentes para a mesma ideia
- Evite "query object" opaco em string única quando params nomeados resolvem

```http
GET /api/v1/workspaces?cursor=eyJpZCI6IjEwMCJ9&sort=created_at&order=desc&include=owner
GET /api/v1/users?filter[status]=active&fields[users]=id,name,email
```

## Semântica que precisa de decisão

- GET não deve executar mutações de domínio; PUT e DELETE têm efeito idempotente,
  mas retries não precisam produzir o mesmo status HTTP.
- PATCH pode ser idempotente conforme as operações aceitas; incrementar um saldo
  e substituir um campo têm comportamentos diferentes sob retry.
- Escolha PUT para substituição completa e PATCH para atualização parcial conforme
  o contrato existente. Ambos precisam tratar concorrência quando aplicável.

## Status codes

| Situação                 | Code | Por quê                                                |
| ------------------------ | ---- | ------------------------------------------------------ |
| Sucesso (leitura/update) | 200  | Padrão de sucesso com body                             |
| Criação                  | 201  | Novo recurso criado                                    |
| Sem conteúdo             | 204  | Sucesso sem body (DELETE, PATCH sem retorno)           |
| Requisição malformada    | 400  | Syntax inválida ou parâmetro faltando                  |
| Não autenticado          | 401  | Token ausente, inválido ou expirado                    |
| Proibido                 | 403  | Auth válida, mas sem permissão sobre o recurso         |
| Não encontrado           | 404  | Recurso não existe — ou não existe *para este usuário* |
| Conflito de estado       | 409  | Duplicata, transição de estado inválida                |
| Erro de validação        | 422  | Syntax válida, mas dados semanticamente inválidos      |
| Rate limit               | 429  | Muitas requisições — inclua `Retry-After`              |
| Erro do servidor         | 500  | Falha não tratada do lado do servidor                  |

**404 vs 403:** prefira 404 quando o recurso existe mas o usuário não tem acesso —
retornar 403 confirma a existência do recurso para um atacante.

## Ações de domínio

REST deve modelar recursos primeiro, mas algumas ações de domínio são legítimas.
Quando a operação não é CRUD puro, prefira um sub-recurso ou comando explícito de
domínio em vez de verbo genérico na raiz:

```http
POST /api/v1/invoices/inv_123/cancel
POST /api/v1/reports/report_123/publish
```

Use isso para transições de estado claras. Não use como desculpa para transformar
toda a API em coleção de RPCs disfarçadas.

## Idempotência

GET, PUT e DELETE devem respeitar sua semântica idempotente; logs e observabilidade
não tornam uma operação de domínio não idempotente.

Para POST não-idempotente em operações críticas (pagamentos, criação de chaves),
aceite `Idempotency-Key` ou equivalente persistido. Escopie por caller/tenant e
operação, vincule à identidade do request e rejeite reutilização com payload
diferente. Reserve a chave atomicamente; duas requisições concorrentes não podem
criar dois efeitos. Defina retenção, estado em andamento e replay do resultado.

```
POST /api/v1/api-keys
Idempotency-Key: client-generated-uuid-v4

→ Primeira chamada: cria e retorna 201
→ Retry da mesma operação: devolve o resultado persistido conforme o contrato
```

## Operações longas

Se a operação depende de export, provider externo, batch, ETL ou processamento que
pode ultrapassar o budget razoável do request, prefira contrato assíncrono:

```http
POST /api/v1/exports
→ 202 Accepted
Location: /api/v1/export-jobs/job_123
```

Retorne um recurso de job com `status`, timestamps, erro sanitizado e ponteiro
para o artefato final quando concluído. Para mais detalhes, veja
`caching-concurrency.md` e `async-webhooks.md`.

## Concorrência e preconditions

Para recursos mutáveis com chance de edição concorrente:

- exponha `ETag` ou `version`
- valide `If-Match` ou versão atomicamente com a escrita em updates críticos
- retorne `412 Precondition Failed` para versão desatualizada
- use `409 Conflict` para conflito de negócio ou transição inválida

Não deixe sobrescrita silenciosa como comportamento padrão.

## Versionamento

| Estratégia     | Implementação       | Trade-off                                    |
| -------------- | ------------------- | -------------------------------------------- |
| **URI**        | `/v1/users`         | Clara, fácil de cachear, URLs verbosas       |
| **Header**     | `Accept-Version: 1` | URLs limpas, difícil de descobrir            |
| **Query**      | `?version=1`        | Fácil de adicionar, polui URLs               |
| **Sem versão** | Evolução cuidadosa  | Ideal para internos, arriscado para públicos |

**Regras práticas:**

- API pública ou consumida por terceiros → versão na URI (`/v1/`)
- API interna com único consumidor controlado → sem versão ou header
- GraphQL → sem versão (evolua o schema com deprecations)
- tRPC → tipos ajudam na integração; coordene versões/deploys e breaking changes

**Breaking changes** que exigem nova versão: remover campo, mudar tipo, alterar
semântica de status code, mudar formato de erro. Adicionar campo opcional não é
breaking change.
