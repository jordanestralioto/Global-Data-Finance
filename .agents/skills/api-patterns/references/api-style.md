# API Style Selection

> Escolha o estilo antes de escrever a primeira rota. Mudar depois tem custo alto.

## Decision Tree

```
Quem vai consumir a API?
│
├── API pública / múltiplas plataformas
│   └── REST + OpenAPI (compatibilidade máxima)
│
├── Dados complexos / múltiplos frontends com necessidades distintas
│   └── GraphQL (queries flexíveis, evita over-fetching)
│
├── TypeScript no frontend e backend (monorepo)
│   └── tRPC (type safety end-to-end sem schema manual)
│
├── Tempo real / streaming autenticado
│   └── SSE ou WebSocket com auth, revogação e limite de custo explícitos
│
├── Integração orientada a eventos / callbacks
│   └── REST + webhooks assinados; AsyncAPI quando o ecossistema justificar
│
└── Microserviços internos
    └── gRPC (performance) ou REST (simplicidade)
```

## Comparação

| Fator                | REST             | GraphQL               | tRPC                |
| -------------------- | ---------------- | --------------------- | ------------------- |
| Melhor para          | APIs públicas    | Apps complexos        | Monorepos TS        |
| Curva de aprendizado | Baixa            | Média                 | Baixa (se TS)       |
| Over/under fetching  | Comum            | Resolvido             | Resolvido           |
| Type safety          | Manual (OpenAPI) | Schema-based          | Automático          |
| Caching              | HTTP nativo      | Complexo              | Client-based        |
| Clientes não-TS      | Sim              | Sim                   | Não                 |
| API pública          | Sim              | Sim                   | Não                 |
| Webhooks/callbacks   | Natural          | Possível, menos usual | Fraco para externos |

## Perguntas de seleção

1. Os consumidores são externos ou de outras linguagens? → REST
2. O frontend precisa compor queries com campos variáveis? → GraphQL
3. Frontend e backend são TypeScript no mesmo repositório? → tRPC
4. O caching HTTP é crítico para performance? → REST
5. A operação é longa e dirigida por eventos? → REST + jobs/webhooks ou stream
6. A equipe já conhece GraphQL? Se não, o benefício justifica a curva?
