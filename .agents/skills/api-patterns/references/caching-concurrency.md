# HTTP Caching And Concurrency

> Use caching para economizar custo e latência. Use preconditions para evitar
> sobrescrita silenciosa e leituras inconsistentes.

## Leituras cacheáveis

Prefira headers HTTP nativos antes de inventar semântica própria:

- `Cache-Control` define política de cache
- `ETag` identifica a representação atual
- `Last-Modified` ajuda quando ETag não estiver disponível
- `Vary` evita servir resposta errada entre callers/contextos diferentes
- `If-None-Match` e `If-Modified-Since` habilitam revalidação barata

```http
GET /api/v1/companies/petr4
If-None-Match: "company-petr4-v17"

→ 304 Not Modified
```

## Regras práticas de cache

- Resposta autenticada raramente deve ser `public`; prefira `private`
- Não cacheie payload com segredo, escopo de usuário ambíguo ou permissão dinâmica
- Se a resposta varia por auth, idioma, workspace ou origin, ajuste `Vary`
- `stale-while-revalidate` ajuda em leitura frequente, mas não substitui invalidação

## Concorrência otimista

Para recurso editável por múltiplos atores, exponha uma prova de versão:

- header `ETag`
- campo `version`
- timestamp forte, se realmente monotônico e controlado pelo servidor

No update, o cliente envia a precondition:

```http
PATCH /api/v1/watchlists/wl_123
If-Match: "watchlist-v8"
Content-Type: application/json
```

Se o recurso mudou desde a leitura do cliente:

```http
412 Precondition Failed
```

## 412 vs 409

- `412 Precondition Failed`: o cliente enviou `If-Match`, `If-Unmodified-Since`
  ou precondition equivalente que não bate mais
- `409 Conflict`: o request é válido, mas entra em conflito de negócio, regra de
  estado ou unicidade que não depende só da versão da representação

## Anti-patterns

**Usar `updated_at` do cliente como prova de versão:** falha porque o cliente pode
forjar ou truncar valor; a autoridade da versão deve ser do servidor.

**Ignorar precondition em delete:** exclusão também é mutação. Se o recurso é
editável por mais de um ator, `DELETE` pode precisar de `If-Match`.

**Retornar ETag sem exigir precondition em update crítico:** isso transforma ETag
em ornamentação; a proteção só existe se o servidor realmente validar a versão.

## Checklist

- Leitura frequente tem estratégia explícita de cache
- `Vary` cobre auth/workspace/origin quando necessário
- Recurso mutável com múltiplos atores expõe versão forte
- `PATCH`, `PUT` e `DELETE` críticos tratam preconditions explicitamente
- `304`, `409` e `412` são usados com semântica consistente
