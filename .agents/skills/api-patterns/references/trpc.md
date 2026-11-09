# tRPC Principles

> Type safety end-to-end sem schema manual, sem code generation.

## Anatomia de um router

```typescript
// server/routers/workspace.ts
import { z } from "zod";
import { router, protectedProcedure, publicProcedure } from "../trpc";

export const workspaceRouter = router({
  list: protectedProcedure
    .query(async ({ ctx }) => {
      // ctx.user vem do middleware de auth — nunca confie em input do cliente
      return db.workspace.findMany({
        where: { userId: ctx.user.id },
      });
    }),

  create: protectedProcedure
    .input(z.object({
      name: z.string().min(1).max(100),
      slug: z.string().regex(/^[a-z0-9-]+$/),
    }))
    .mutation(async ({ ctx, input }) => {
      return db.workspace.create({
        data: { ...input, ownerId: ctx.user.id },
      });
    }),

  byId: protectedProcedure
    .input(z.object({ id: z.string() }))
    .query(async ({ ctx, input }) => {
      const workspace = await db.workspace.findFirst({
        // Sempre filtre por userId — não busque só pelo id
        where: { id: input.id, ownerId: ctx.user.id },
      });
      if (!workspace) throw new TRPCError({ code: "NOT_FOUND" });
      return workspace;
    }),
});
```

## Middleware de autenticação

```typescript
// server/trpc.ts
import { initTRPC, TRPCError } from "@trpc/server";
import { getSession } from "./auth";

const t = initTRPC.context<Context>().create();

// Procedure pública — sem auth
export const publicProcedure = t.procedure;

// Procedure protegida — rejeita antes de chegar no handler
export const protectedProcedure = t.procedure.use(async ({ ctx, next }) => {
  if (!ctx.session?.user) {
    throw new TRPCError({ code: "UNAUTHORIZED" });
  }
  return next({ ctx: { ...ctx, user: ctx.session.user } });
});

// Procedure de admin — dupla verificação
export const adminProcedure = protectedProcedure.use(async ({ ctx, next }) => {
  if (ctx.user.role !== "admin") {
    throw new TRPCError({ code: "FORBIDDEN" });
  }
  return next();
});
```

## Tratamento de erros

tRPC mapeia `TRPCError` para status HTTP automaticamente:

| TRPCError code          | HTTP Status | Quando usar                          |
| ----------------------- | ----------- | ------------------------------------ |
| `BAD_REQUEST`           | 400         | Input inválido (zod falhou)          |
| `UNAUTHORIZED`          | 401         | Sessão ausente ou expirada           |
| `FORBIDDEN`             | 403         | Auth válida, sem permissão           |
| `NOT_FOUND`             | 404         | Recurso não existe para este usuário |
| `CONFLICT`              | 409         | Duplicata ou estado inválido         |
| `TOO_MANY_REQUESTS`     | 429         | Rate limit excedido                  |
| `INTERNAL_SERVER_ERROR` | 500         | Falha não tratada                    |

Nunca lance erros JavaScript brutos nos procedures — eles vazam detalhes internos.
Sempre use `TRPCError` com `message` sanitizada.

```typescript
// ❌ Vaza detalhes internos
throw new Error(dbError.message);

// ✅ Mensagem sanitizada
throw new TRPCError({
  code: "INTERNAL_SERVER_ERROR",
  message: "Erro ao processar a solicitação.",
});
```

## Integração com React Query

```typescript
// client/hooks/useWorkspace.ts
import { trpc } from "../utils/trpc";

export function useWorkspace(id: string) {
  return trpc.workspace.byId.useQuery(
    { id },
    {
      retry: false,           // não repita em 401/403
      staleTime: 30_000,      // cache por 30s
      onError: (err) => {
        if (err.data?.code === "UNAUTHORIZED") {
          redirectToLogin();
        }
      },
    }
  );
}
```

## Anti-patterns

**Aceitar `userId` no input de procedure protegida:**

```typescript
// ❌ Qualquer caller pode forjar o userId
byId: protectedProcedure
  .input(z.object({ id: z.string(), userId: z.string() }))
  .query(({ input }) => db.workspace.findFirst({
    where: { id: input.id, ownerId: input.userId },
  }));

// ✅ userId vem sempre do contexto de auth
byId: protectedProcedure
  .input(z.object({ id: z.string() }))
  .query(({ ctx, input }) => db.workspace.findFirst({
    where: { id: input.id, ownerId: ctx.user.id },
  }));
```

**Router sem separação de contexto:**
Não coloque procedures públicas e protegidas no mesmo router sem middleware.
Separe em routers distintos ou use procedures diferentes (`publicProcedure` vs
`protectedProcedure`) — o middleware garante que a verificação não seja esquecida.
