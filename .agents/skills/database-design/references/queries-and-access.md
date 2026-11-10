# Queries And Access

## Índice ligado a um acesso

Capture a query real, parâmetros representativos, distribuição de dados e plano
antes de adicionar índices. Registre o que deve melhorar e o custo aceito em
escrita, armazenamento e manutenção. Não assuma que scan sequencial é defeito.

Verifique prefixos, igualdade/range, ordenação, predicado parcial e colunas de
cobertura. Um índice que contém uma coluna não necessariamente atende um lookup
por ela. Por outro lado, não crie um índice redundante quando uma PK/UNIQUE ou
um índice existente já atende o acesso.

FK e índice têm papéis diferentes. Algumas engines criam/exigem índices de FK,
outras não; confirme o comportamento real. No PostgreSQL, o índice nas colunas
que referenciam o pai não é criado automaticamente. Decida pelo custo dos joins,
lookups e ações referenciais, sem converter cada FK em índice obrigatório.
[PostgreSQL: foreign keys](https://www.postgresql.org/docs/current/ddl-constraints.html#DDL-CONSTRAINTS-FK).

Ao avaliar um plano, distinga estimativa ruim, baixa seletividade, sort,
round-trips e volume excessivo retornado. Use execução com efeitos colaterais
apenas no ambiente apropriado; `EXPLAIN ANALYZE` de uma escrita executa a escrita.

## Paginação determinística

Defina uma ordem total no conjunto filtrado. Se `created_at` pode empatar,
adicione desempate único, como `ORDER BY created_at DESC, id DESC`. O cursor
deve carregar os componentes dessa ordem; o predicado da página seguinte e o
índice precisam corresponder a ela, incluindo direção e tratamento de nulos.

Fixe os filtros e o escopo do tenant ao interpretar o cursor. Defina o efeito
de inserções, exclusões e atualizações entre páginas. Cursor por chave mutável
não equivale a um snapshot estável; exija esse contrato apenas quando o produto
precisar dele.

`OFFSET` pode atender páginas pequenas e navegação aleatória de baixo custo.
Para offsets grandes ou feeds com exigências de continuidade, avalie paginação
por chave e meça o acesso. Mesmo com `OFFSET`, a ordem deve ser previsível.
[PostgreSQL: LIMIT/OFFSET](https://www.postgresql.org/docs/current/queries-limit.html).

## ORM e volume de consultas

Inspecione SQL, número de consultas, linhas e payloads com a versão/configuração
reais. Lazy loading ou um loop de relações pode causar N+1; `include`/eager
loading também pode trazer dados demais. Não conclua que um método sempre faz
uma consulta ou que aninhamento sempre explode o número de queries.

Leia `references/native-tooling.md` quando a estratégia de carregamento ou o
runtime async alterar a decisão. Compare batch, join e projeções com evidência,
sem recomendar troca de ORM por preferência pessoal.

## Outbox, workers e retries

Se uma mudança de estado precisa gerar um evento, defina se ambos são gravados
na mesma transação. Publishing posterior pode repetir após falha: use identidade
estável do evento e consumidor idempotente conforme o efeito esperado.

Para múltiplos workers, defina aquisição, duração da posse, retomada de trabalho
abandonado e condição de conclusão. `FOR UPDATE SKIP LOCKED`, quando suportado,
ajuda na disputa por linhas; sozinho não implementa uma outbox transacional,
recuperação após crash ou entrega exatamente uma vez. Confira a semântica da
engine e os efeitos de manter a transação aberta durante o processamento.

## Payloads semiestruturados e vetores

Para JSON de integrações ou modelos de IA, separe payload bruto, campos de
domínio e versão do contrato. Valide dados extraídos antes de usá-los como
identidade, escopo, dinheiro ou estado. Decida entre coluna normalizada,
expressão/coluna gerada e índice conforme consultas, suporte e custo de evolução.
Não use JSON como substituto automático de relações ou constraints.

Na busca vetorial, preserve o predicado de autorização e avalie recall/latência
dentro do tenant real. Um filtro no `WHERE` não implica pré-filtragem física do
índice aproximado. No pgvector, o filtro é aplicado depois da varredura ANN;
seletividade pode reduzir resultados. Avalie busca exata, varreduras iterativas,
índices parciais ou particionamento com a versão e distribuição reais.
[pgvector: filtering](https://github.com/pgvector/pgvector#filtering).
