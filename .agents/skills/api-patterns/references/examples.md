# API Examples

> Use estes exemplos quando a conversa pedir um shape concreto de rota, payload,
> precondition, job assíncrono ou contrato de erro. Adapte ao estilo já escolhido
> no repositório.

## REST: listagem paginada com envelope e problem details

```http
GET /api/v1/workspaces?page=2&per_page=20&sort=created_at&order=desc
Authorization: Bearer <token>
```

```json
{
  "data": [
    {
      "id": "ws_123",
      "name": "Research Workspace"
    }
  ],
  "meta": {
    "pagination": {
      "page": 2,
      "per_page": 20,
      "total": 41
    }
  }
}
```

```json
{
  "type": "https://api.example.com/problems/resource-not-found",
  "title": "Resource not found",
  "status": 404,
  "detail": "Workspace not found or inaccessible.",
  "instance": "/api/v1/workspaces/ws_999",
  "code": "RESOURCE_NOT_FOUND",
  "request_id": "req_7f3a9b2c"
}
```

## REST: update com concorrência otimista

```http
GET /api/v1/watchlists/wl_123
Authorization: Bearer <token>
```

```http
200 OK
ETag: "watchlist-v8"
```

```http
PATCH /api/v1/watchlists/wl_123
Authorization: Bearer <token>
If-Match: "watchlist-v8"
Content-Type: application/json

{
  "name": "Long-term portfolio"
}
```

Se outro cliente já alterou o recurso:

```json
{
  "type": "https://api.example.com/problems/precondition-failed",
  "title": "Precondition failed",
  "status": 412,
  "detail": "The resource changed after your last read. Fetch the latest version and retry.",
  "code": "PRECONDITION_FAILED",
  "request_id": "req_a19b31f0"
}
```

## REST: job assíncrono com `202 Accepted`

```http
POST /api/v1/report-exports
Authorization: Bearer <token>
Idempotency-Key: 6e1d3d43-2e8b-4d05-9f95-9f1dbf0ef32b
Content-Type: application/json

{
  "report_id": "rep_123",
  "format": "csv"
}
```

```http
202 Accepted
Location: /api/v1/report-export-jobs/job_123
Retry-After: 5
```

```json
{
  "data": {
    "id": "job_123",
    "status": "queued"
  }
}
```

## GraphQL: ownership e erro sanitizado

```graphql
query WorkspaceById($id: ID!) {
  workspace(id: $id) {
    id
    name
  }
}
```

```json
{
  "errors": [
    {
      "message": "Workspace not found.",
      "extensions": {
        "code": "RESOURCE_NOT_FOUND",
        "request_id": "req_abc123"
      }
    }
  ],
  "data": {
    "workspace": null
  }
}
```

## tRPC: procedure protegida com filtro de ownership

```typescript
export const workspaceRouter = router({
  byId: protectedProcedure
    .input(z.object({ id: z.string() }))
    .query(async ({ ctx, input }) => {
      const workspace = await db.workspace.findFirst({
        where: { id: input.id, ownerId: ctx.user.id },
      });

      if (!workspace) {
        throw new TRPCError({
          code: "NOT_FOUND",
          message: "Workspace not found.",
        });
      }

      return workspace;
    }),
});
```

## Webhook receiver: trust boundary explícita

```http
POST /api/v1/webhooks/payments
X-Signature: sha256=...
X-Event-Id: evt_123
X-Event-Timestamp: 1715000000
```

Regras esperadas:

- validar assinatura antes do processamento pesado
- rejeitar replay fora da janela de tolerância
- deduplicar por `event_id`
- responder rápido e despachar trabalho pesado para fila/job interno

## Rate limit antes do custo

```http
POST /api/v1/messages/stream
Idempotency-Key: 6e1d3d43-2e8b-4d05-9f95-9f1dbf0ef32b
X-API-Key: <redacted>
```

Regra esperada:

- validar auth e rate limit antes de abrir stream ou chamar provider
- retornar `429` com `Retry-After` se o saldo for insuficiente
- deduzir o custo do endpoint antes do trabalho caro começar

## Quando usar o validador

Entrada: "Revisei várias rotas REST e quero uma triagem rápida antes da revisão final."

Saída esperada:

- rodar `python .agents/skills/api-patterns/scripts/validate_api.py <path>`
- tratar o resultado como heurística
- complementar com revisão contextual de ownership, proxy, envelopes, auth, async,
  lifecycle e concorrência
- verificar `status`, arquivos omitidos e `unverified`; sem candidatos não há evidência
