# GraphQL Principles

> Queries flexíveis para dados complexos e interconectados.

## Design de Schema

- Pense em grafos, não em endpoints — modele relacionamentos, não operações.
- Projete para evolvabilidade: adicione campos, nunca remova sem deprecation explícita.
- Use connections para paginação (`edges`, `node`, `pageInfo`) — evita breaking changes futuros.
- Seja específico com tipos — evite `data: JSON` genérico que elimina type safety.
- Trate nullability com cuidado: campo nullable significa "pode não existir"; non-null significa "sempre presente ou erro".

## Mutations

- Nomeie mutations com verbos de domínio: `createWorkspace`, não `workspaceCreate`.
- Retorne o recurso modificado na resposta — evita round-trip extra do cliente.
- Use input types dedicados para mutations complexas, não argumentos inline.

## Segurança

**Depth attack:** queries profundamente aninhadas podem explodir o tempo de resolução.
Defina um limite máximo de profundidade (ex: 7 níveis) e rejeite queries que ultrapassem.

**Query complexity:** calcule o custo estimado da query antes de executar.
Atribua peso a cada campo/resolver e rejeite queries acima do threshold do workspace.

```
# Exemplo de política de complexidade
max_complexity: 100
field_costs:
  users: 1
  users.posts: 5        # join custoso
  users.posts.comments: 10
```

**Batching abuse:** limite o tamanho de listas de IDs em queries batch para evitar
extração massiva de dados em uma única requisição.

**Introspection:** desabilite em produção para não expor o schema completo a atacantes.
Mantenha habilitado apenas em ambientes de desenvolvimento com auth.

## Erros

- Use o campo `errors` do padrão GraphQL, não HTTP 4xx/5xx para erros de negócio.
- Inclua `extensions.code` para tratamento programático pelo cliente.
- Nunca exponha stack traces ou mensagens internas no campo `message`.

```json
{
  "errors": [{
    "message": "Recurso não encontrado",
    "extensions": {
      "code": "RESOURCE_NOT_FOUND",
      "request_id": "req_abc123"
    }
  }]
}
```
