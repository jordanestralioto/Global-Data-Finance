# Response Format Principles

> Preserve contratos existentes. Em erros, siga o formato do estilo da API e
> mantenha a resposta sanitizada.

## Quando usar envelope

Retornar um array bruto (`[{...}, {...}]`) na raiz da resposta parece simples, mas
pode exigir breaking change quando paginação ou metadados passarem a ser
necessários. Para novos contratos JSON, escolha envelope quando houver essa
necessidade. Não altere um contrato existente só para impor esse formato; headers
e links também podem carregar metadados. Streaming e formatos nativos do protocolo
não precisam ser convertidos para `{ data, meta }`.

## Formato de sucesso

```json
{
  "data": [...],
  "meta": {
    "pagination": {
      "total": 243,
      "page": 2,
      "per_page": 20,
      "next_cursor": "eyJpZCI6MTAwfQ=="
    }
  }
}
```

Para recursos únicos, `data` é um objeto, não array:

```json
{
  "data": {
    "id": "usr_123",
    "name": "Ana Silva",
    "created_at": "2025-01-15T10:30:00Z"
  }
}
```

## Formato de erro em REST/HTTP

Siga RFC 9457 ou problem details compatível. Nunca exponha stacktrace, mensagens
internas ou detalhes de provider.

```json
{
  "type": "https://api.example.com/problems/resource-not-found",
  "title": "Resource not found",
  "status": 404,
  "detail": "Conversa não encontrada ou sem permissão de acesso.",
  "instance": "/api/v1/conversations/conv_123",
  "code": "RESOURCE_NOT_FOUND",
  "request_id": "req_7f3a9b2c"
}
```

`type`, `title`, `status`, `detail` e `instance` seguem o shape padrão.
`code` é uma extensão útil para tratamento programático pelo cliente.
`request_id` é para suporte rastrear a causa raiz sem expor internals.

**Nunca inclua:** stack traces, queries SQL, mensagens de exceção internas,
tokens, API keys, URLs de providers ou detalhes de infraestrutura.

## Formato de erro em GraphQL e tRPC

- **GraphQL:** use `errors[]` com `extensions.code` e um `request_id` ou campo
  equivalente do projeto. O corpo de erro não precisa imitar RFC 9457.
- **tRPC:** use `TRPCError` com mensagem sanitizada e mapping HTTP nativo do framework.
- **Regra comum:** independente do estilo, nunca exponha segredo, stack trace,
  SQL bruto, payload upstream ou detalhe interno do provider.

## Paginação

| Tipo       | Melhor para                               | Trade-off                                 |
| ---------- | ----------------------------------------- | ----------------------------------------- |
| **Offset** | Datasets pequenos, navegação por página   | Performance degrada em datasets grandes   |
| **Cursor** | Datasets grandes, feeds em tempo real     | Não permite saltar para página específica |
| **Keyset** | Performance crítica com ordenação estável | Requer chave sortável e estável           |

**Regra de seleção:**

- Navegação por página com custo medido aceitável → offset
- Dataset grande ou dados mudam frequentemente → cursor
- Performance é o requisito principal → keyset

Inclua sempre no `meta.pagination`: total de registros (quando viável), cursor/page
atual e indicador de próxima página.

## Status codes e body

| Situação          | Code | Body                                            |
| ----------------- | ---- | ----------------------------------------------- |
| Sucesso com dados | 200  | `{ "data": ... }`                               |
| Criação           | 201  | `{ "data": recurso_criado }`                    |
| Sucesso sem dados | 204  | vazio — sem body                                |
| Erro de cliente   | 4xx  | problem detail sanitizado                       |
| Erro de servidor  | 500  | problem detail sanitizado com mensagem genérica |

Em erros 500, `detail` deve ser genérico — nunca a mensagem real da exceção.

[RFC 9457: Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
substitui RFC 7807. Adapte o tratamento ao contrato já publicado antes de mudar
campos ou semântica de erro.
