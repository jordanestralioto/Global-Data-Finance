# Native Tooling And Engine Boundaries

## Descubra a fonte antes do comando

Localize os manifests/configurações do consumidor, scripts de validação,
diretórios de schema/migrations e versões fixadas. Use a ferramenta já declarada
pelo projeto; não instale uma CLI global ou um ORM diferente para satisfazer
um exemplo desta skill.

Distinga validar o arquivo, gerar SQL, comparar com o banco e aplicar migration.
Um comando chamado `check`, `diff` ou `dry-run` pode acessar um banco ou gerar
arquivos; confira sua configuração e o destino. Para provar comportamento de
engine/concorrência, use o ambiente descartável/teste adequado ao repositório.
O helper Python apenas lê arquivos e não faz conexão com o banco.

Em qualquer linguagem, encontre o artefato que a ferramenta realmente consome:
SQL versionado, schema declarativo ou modelo/migration em código. Aponte caminhos
explícitos ao helper para convenções personalizadas. Quando ele só inventariar
código, revise os acessos e obtenha SQL/validação nativa; não gere parsers ad hoc
para Ruby, Go, Java, C#, PHP ou cada novo framework.

## ORM: contrato declarado e contrato efetivo

Confira nulidade, unicidade, FKs, ações referenciais, índices, transações e
conversões nos artefatos gerados e no estado aplicado. Uma relação declarada no
ORM pode existir apenas no cliente; um índice na FK não é uma garantia universal
fornecida pela engine.

### Prisma

- Leia o provider, a versão e `relationMode`. No modo `prisma`, a integridade é
  emulada pelo cliente e não substitui FKs para escritores externos. Verifique
  quais operações são cobertas pela versão e pelo caminho de escrita.
- Decida `onDelete`/`onUpdate` pelo lifecycle e confirme os defaults ou valores
  explícitos no SQL; não aplique `Cascade` por conveniência.
- Para relações carregadas, confira `relationLoadStrategy` e as opções realmente
  habilitadas. Na documentação v7, `join` e `query` têm estratégias diferentes;
  um `include` aninhado não demonstra N+1 sozinho.
- Schemas podem ser distribuídos em vários arquivos e caminhos configurados.
  O helper interpreta chaves/relações locais; a CLI nativa valida a composição.

Fontes: [relation mode](https://www.prisma.io/docs/orm/v7/prisma-schema/data-model/relations/relation-mode),
[referential actions](https://www.prisma.io/docs/orm/v7/prisma-schema/data-model/relations/referential-actions),
[relation queries](https://www.prisma.io/docs/orm/v7/prisma-client/queries/relation-queries).

### SQLAlchemy async

Considere I/O implícito ao acessar relações ou atributos expirados.
`MissingGreenlet` pode indicar uma consulta disparada fora do contexto async
apropriado. Avalie carregamento explícito/eager, `selectinload`, política de
expiração, `AsyncAttrs` e sessões independentes por tarefa conforme o caso.
Não trate a presença de `joinedload` como prova de que não haverá I/O implícito.
[SQLAlchemy: preventing implicit I/O](https://docs.sqlalchemy.org/en/20/orm/extensions/asyncio.html#preventing-implicit-io-when-using-asyncsession).

### Outros ORMs e drivers

Faça as mesmas perguntas sobre o SQL e a transação reais. Inspecione migrations
geradas por Drizzle, Django, Rails, EF Core ou outra ferramenta sem presumir
equivalência entre seus mecanismos de relação, índice, delete e carregamento.
A linguagem do consumidor não muda a obrigação de provar a invariante.

## PostgreSQL e operação de DDL

Use estes pontos para identificar a evidência necessária, sem duplicar tuning
operacional da skill `supabase` quando ela estiver disponível:

- `lock_timeout` limita a espera para adquirir cada lock. Não limita por si só
  quanto tempo uma operação mantém um lock após adquiri-lo; distinga-o de
  `statement_timeout` e da duração da transação.
- `ADD CONSTRAINT ... NOT VALID` pode separar enforcement e varredura de legado
  nas constraints/versões suportadas. Ainda exige locks. Confira o tipo exato
  e o lock da adição; `VALIDATE CONSTRAINT` usa `SHARE UPDATE EXCLUSIVE`.
- `CREATE INDEX CONCURRENTLY` tem restrições e comportamento de falha próprios.
  Confira se o runner abre uma transação incompatível e como verificar/remediar
  um índice inválido após interrupção.

Fontes: [timeouts](https://www.postgresql.org/docs/current/runtime-config-client.html#GUC-LOCK-TIMEOUT),
[ALTER TABLE](https://www.postgresql.org/docs/current/sql-altertable.html),
[CREATE INDEX](https://www.postgresql.org/docs/current/sql-createindex.html).

Quando o centro do problema for RLS, grants, papéis privilegiados, pooling,
locks ou tuning operacional, siga o roteamento do corpo da skill. Se a skill
especializada não estiver instalada, explicite o limite e consulte fontes
oficiais da versão; não substitua a prova por uma regra genérica de SQL.
