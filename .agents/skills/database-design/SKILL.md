---
name: database-design
description: >-
  Use para modelar ou revisar schema, constraints, índices e migrations em
  qualquer linguagem. Ative com "como modelo esse banco?", "essa query precisa
  de índice?", "como renomeio sem quebrar o deploy?", "dois jobs duplicam esse
  registro" ou "como garanto ownership nessa relação?". Cobre integridade,
  concorrência, isolamento e evolução de dados. Para RLS, grants, pooling ou
  operação específica de Supabase/Postgres, prefira `supabase`; para lentidão
  sem origem isolada, `performance-profiling`; para contratos de endpoint,
  `api-patterns`.
---

# Database Design

## Decisões que precisam de evidência

Parta do banco, dos acessos e das versões já usados pelo projeto. Não troque
engine ou ORM para acomodar um exemplo da skill. Separe o schema declarado, o
SQL gerado e o estado efetivamente aplicado: nenhum deles prova os outros.

Uma consulta prévia não garante unicidade sob concorrência. Uma FK não prova
autorização. Uma migration que compila não prova compatibilidade com callers
antigos. Um índice declarado não prova melhora de uma query. Exija a evidência
correspondente antes de afirmar cada garantia.

## Procedimento

1. **Delimite o problema e o banco operado.** Localize configurações, schemas,
   migrations e acessos reais no repositório. Registre engine/versão, ORM/driver,
   fronteira do banco, volume relevante e estratégia de deploy apenas quando
   mudarem a decisão. Em monorepos, separe bancos e serviços antes de combinar
   evidências. Se a origem da latência ainda for desconhecida, encaminhe para
   `performance-profiling`, quando disponível.

2. **Extraia invariantes dos caminhos de acesso.** Para cada leitura/escrita
   crítica, identifique filtros, ordenação, cardinalidade, owner e escritores
   concorrentes. Formule a regra que precisa sobreviver a retries, jobs e
   scripts. Leia `references/integrity-and-isolation.md` para constraints,
   concorrência, tipos de domínio e relações entre tenants.

3. **Escolha onde cada garantia será aplicada.** Ligue invariantes a constraints,
   transações, controle de versão ou locks com política de conflito/retry.
   Confirme as FKs e ações referenciais no SQL efetivo do ORM. Prove o escopo
   dos filhos pelo caminho de acesso; não exija `tenant_id` duplicado sem motivo
   nem aceite a coluna como prova de isolamento.

4. **Desenhe índices e acesso juntos.** Justifique cada índice por uma query,
   prefixo, seletividade, ordenação e custo de escrita. Confira índices já
   existentes e mecanismos automáticos da engine. Para paginação, N+1, outbox,
   payloads semiestruturados e busca vetorial, leia
   `references/queries-and-access.md`.

5. **Planeje compatibilidade antes do DDL.** Identifique callers antigos,
   workers, versões simultâneas e dados existentes. Defina expansão, transição
   de leitura/escrita, backfill concorrente, validação e remoção tardia conforme
   o contexto. Explicite orçamento de locks, retomada e recuperação. Leia
   `references/migrations.md`; não imponha múltiplos deploys a um banco novo ou
   a uma operação comprovadamente compatível.

6. **Resolva detalhes pela ferramenta e versão reais.** Leia
   `references/native-tooling.md` quando o ORM, driver ou engine mudar a
   garantia. Reuse comandos nativos declarados pelo repositório e ambientes
   descartáveis apropriados; não invente um validador por linguagem. RLS,
   grants e tuning operacional de Supabase/Postgres seguem para `supabase`,
   quando disponível. Sem essa skill, use documentação oficial e explicite a
   evidência que falta, sem bloquear o trabalho independente.

7. **Use triagem estática como evidência limitada.** Quando houver artefatos de
   schema/migration, execute o helper Python sobre arquivos ou diretórios
   concretos. Ele não importa nem executa o código da aplicação:

   ```bash
   python .agents/skills/database-design/scripts/check_schema.py caminho/do/schema.sql
   ```

   Leia `references/triage-contract.md` para cobertura, formatos e códigos de
   saída. SQL suportado e Prisma recebem análise de declarações; modelos e
   migrations em outras linguagens recebem inventário e indicação de análise
   nativa pendente. Resultado incompleto não vira aprovação por inferência.

8. **Valide as garantias modificadas.** Escolha testes que distingam a solução
   da falha: dois escritores simultâneos, retry do mesmo evento, acesso de outro
   tenant, backfill com escrita concorrente ou duas versões da aplicação.
   Compare planos e custo real quando a mudança for de query/índice. Se a
   validação não puder rodar, registre precisamente a garantia ainda não provada.

## Entrega

Ajuste a resposta ao pedido. Em implementação, altere os arquivos e apresente
a decisão, a invariante protegida, o rollout e a evidência obtida. Em revisão,
ligue cada achado a um acesso ou estado inválido reproduzível e à ação necessária.

Diferencie evidência observada, hipótese e validação pendente. Informe os
artefatos analisados e suas limitações. Evite um template extenso preenchido
com campos irrelevantes para uma alteração pequena.

## Referências por decisão

| Decisão pendente                                               | Recurso                                 |
| -------------------------------------------------------------- | --------------------------------------- |
| Invariantes, retries, tipos de domínio e ownership de relações | `references/integrity-and-isolation.md` |
| Compatibilidade, backfill, cutover e recuperação               | `references/migrations.md`              |
| Índices, paginação, N+1, outbox, JSON e vetores                | `references/queries-and-access.md`      |
| Garantias reais de ORM/driver/engine e ferramentas nativas     | `references/native-tooling.md`          |
| Executar e interpretar o helper portátil                       | `references/triage-contract.md`         |
| Exercitar a skill com critérios de aceitação observáveis       | `references/evals.md`                   |

## Exemplos

### Caso positivo — retries e concorrência

**Entrada:** "O handler e dois workers podem criar a mesma cobrança externa."
**Saída esperada:** descobrir a identidade do evento e seu escopo, proteger a
invariante no banco, definir o resultado do conflito/retry e testar escritores
simultâneos. `SELECT` seguido de `INSERT` não fecha a garantia.

### Caso positivo — rename em aplicação existente

**Entrada:** "Renomeia esta coluna; versões antigas do worker continuam rodando."
**Saída esperada:** localizar os callers, manter a compatibilidade durante a
transição, tratar escritas durante o backfill e adiar a remoção até provar o
abandono da coluna antiga.

### Caso negativo — origem da lentidão desconhecida

**Entrada:** "A tela ficou lenta; não sei se é React, rede ou banco."
**Por quê não:** falta localizar o gargalo; use `performance-profiling`.

### Caso negativo — policy de produto específico

**Entrada:** "A policy RLS do Supabase aceita o tenant errado."
**Por quê não:** a implementação e a prova da policy pertencem a `supabase`.

## Evals de trigger

Deve acionar:

- "Dois jobs podem inserir a mesma conciliação; onde garanto unicidade?"
- "Esse índice atende o filtro e a ordenação desta query?"
- "Nossa migration roda com duas versões da aplicação; revisa o rollout."
- "A FK entre pedido e item preserva o workspace correto?"
- "Esse valor representa dinheiro, taxa aproximada ou identificador opaco?"

Não deve acionar:

- "Qual status HTTP uso quando a cobrança já existe?" (`api-patterns`)
- "A API ficou lenta e não localizei o gargalo." (`performance-profiling`)
- "Revisa grants e service role no Supabase." (`supabase`)
- "Escreve um SELECT trivial sem decisão de schema ou acesso."

## Evals de workflow

Use `references/evals.md` para cenários de migração concorrente, isolamento
herdado, paginação e triagem em projetos de linguagens diferentes. As assertions
avaliam decisões e evidências; passar na estrutura da skill não prova seu ganho
em relação a um agente sem ela.
