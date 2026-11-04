# reference.md

## Matriz operacional

| Sintoma dominante                                                                                  | O que medir primeiro                                         | Ferramenta minima                                  | Handoff quando confirmar                                                                                              |
| -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ | -------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Pagina carrega lento e ainda nao esta claro se o custo e frontend ou backend                       | LCP, waterfall de requests, ordem de inicio do trabalho      | Lighthouse, Network tab, timing de request         | `react-performance` se virar bundle, waterfall ou custo de JS; `webapp-testing` se o gargalo depender de jornada real |
| Interacao no cliente esta lenta, mas ainda nao se sabe se e render, request ou main thread         | INP, custo de render, requests disparados por interacao      | Performance tab, React Profiler, painel de rede    | `react-performance` assim que re-render, boundary ou cache forem a causa dominante                                    |
| API esta lenta e ainda nao se sabe se o tempo esta no handler, serializacao ou banco               | tempo total por request, tempo do handler, numero de queries | logs de duracao, cProfile, tracing simples         | `database-design` ou `supabase` se a causa dominante cair na query ou no acesso ao banco                              |
| Banco parece suspeito, mas ainda nao esta claro se o problema e plano, indice ou desenho de acesso | tempo real de query, plano de execucao, seletividade         | `EXPLAIN ANALYZE`, `pg_stat_statements`            | `database-design` ou `supabase`                                                                                       |
| Sintoma parece performance, mas a reproducao e instavel ou a causa raiz ainda e nebulosa           | sinal minimo observavel e reproducao estavel                 | logs, assertions, roteiro minimo de reproducao     | `systematic-debugging` assim que a dor dominante virar root cause e nao comparacao de performance                     |
| Pedido principal e apenas validar o repositorio depois das mudancas                                | gates e comandos oficiais                                    | comandos do handoff/pre-commit ou harness-validate | `lint-and-validate`                                                                                                   |

## Limites desta skill

- Esta skill localiza o gargalo dominante e decide o proximo owner. Ela nao substitui skills especialistas quando o problema deixa de ser difuso.
- Se nao houver baseline viavel, a resposta correta e declarar o bloqueio e destravar medicao.
- Quando houver implementacao, uma mudanca por vez preserva a capacidade de comparar antes e depois.
