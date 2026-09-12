---
name: performance-profiling
description: >-
  Use para identificar o gargalo dominante quando a lentidão ainda não estiver
  isolada de um serviço. Ative com "está lento e não sei onde", "mede antes/depois", "qual
  gargalo atacar primeiro?", "quero prova antes de otimizar", "ficou mais lento"
  ou "onde está o bottleneck?". Cobre profiling, baseline, comparação e
  evidências de antes/depois. Não use quando a causa já for query Postgres, query
  Polars, re-render React específico, teste de navegador ou bug funcional sem
  sintoma de performance; use a skill especialista.
---

# Performance Profiling

## Procedimento

1. Descubra se o pedido ainda e de triagem cross-layer ou se o gargalo ja esta localizado:
   - se o usuario ja delimitou re-render, waterfall React, bundle ou custo de JavaScript no browser, saia cedo para `react-performance`
   - se o usuario ja delimitou query lenta, indice, schema, Postgres ou Supabase, saia cedo para `database-design` ou `supabase`
   - se o pedido dominante for bug intermitente, falha sem reproducao estavel ou causa raiz incerta sem sinal claro de performance, saia cedo para `systematic-debugging`
   - se o pedido for "roda os checks", gate-report ou validacao repo-native, saia cedo para `lint-and-validate`
   - se o pedido dominante for reproduzir fluxo real no browser, auth/session, screenshot ou E2E, saia cedo para `webapp-testing`
2. Defina o sintoma em uma metrica observavel antes de propor qualquer mudanca: LCP, INP, tempo total de request, latencia de handler, tempo de query, CPU, memoria, bundle ou throughput.
3. Escolha a trilha inicial de medicao pela camada mais provavel, sem adivinhar profundidade:
   - carregamento ou interacao no browser: Lighthouse, waterfall de rede, Performance tab, React Profiler
   - API ou backend: tempo total por request, handler timing, serializacao, cProfile ou logs de duracao
   - banco: `EXPLAIN ANALYZE`, tempo de query, seletividade, chamadas repetidas ou `pg_stat_statements`
4. Colete um baseline minimo. Se nao houver ambiente, URL, comando, fixture ou metrica minimamente confiavel, trate isso como bloqueio explicito e nao recomende micro-otimizacao especulativa.
5. Isole o gargalo dominante com a menor evidencia que permita decidir a proxima skill ou a proxima mudanca. Pare de abrir novas frentes assim que houver sinal suficiente para um handoff confiavel.
6. Se a triagem ainda for desta skill, recomende apenas a menor intervencao que tenha relacao direta com a metrica observada. Se o pedido incluir implementacao, aplique uma mudanca por vez para preservar comparacao valida.
7. Depois da mudanca, compare antes/depois com a mesma metrica e o mesmo metodo de medicao. Se nao houver delta mensuravel, registre isso e prefira reverter a insistir em otimizar no escuro.

## Heuristicas

- O trabalho principal desta skill e localizar a camada dominante, nao esgotar a otimizacao de React, banco ou runtime especifico.
- Sem baseline minimamente confiavel, a resposta correta costuma ser desbloquear medicao, nao sugerir tuning por intuicao.
- Waterfall, bundle e re-render quase sempre pertencem a `react-performance` assim que o sintoma deixa de ser difuso.
- Query lenta, indice faltando e plano ruim pertencem a skills de banco assim que a evidencia encostar na query.
- Uma unica mudanca por rodada vale mais do que varias "melhorias" impossiveis de atribuir a um delta.

## Contrato de saida

### Quando o sintoma ainda e difuso e ha ambiente mensuravel

Entregue:

- sintoma observado e a metrica escolhida
- baseline ou estado atual medido
- camada inicial escolhida e por que ela foi priorizada
- gargalo dominante ou hipotese lider apoiada por evidencia
- proximo passo recomendado
- skill de handoff, se o problema deixou de ser difuso
- evidencia esperada do delta depois da mudanca

### Quando nao existe baseline viavel

Entregue:

- sintoma observado
- o que impede a medicao agora
- o menor artefato que falta para criar baseline confiavel
- o proximo passo para desbloquear medicao
- ausencia explicita de recomendacao especulativa de micro-otimizacao

### Quando o gargalo ja esta localizado

Entregue:

- por que o caso deixou de ser triagem cross-layer
- qual skill deve assumir como owner principal
- qual evidencia ja existe para o handoff
- o que ainda precisa ser medido ou validado depois da intervencao

## Uso de scripts

- Use `python3 .agents/skills/performance-profiling/scripts/lighthouse_audit.py <url>` quando houver uma URL executavel e a suspeita inicial estiver no browser.
- Trate o script como helper opcional de baseline, nao como diagnostico completo.
- Nao exponha o script como solucao principal para backend ou banco; nesses casos ele so adiciona ruido.

## Exemplos

### Caso positivo

**Entrada:** Usuario diz "a tela esta lenta e nao sei se o problema e bundle, request ou backend".
**Saida esperada:** Tratar como triagem cross-layer, escolher uma metrica observavel, medir o baseline inicial e identificar qual camada deve receber o proximo mergulho.

### Caso positivo

**Entrada:** Usuario pede "quero evidencia antes/depois para decidir qual gargalo atacar primeiro nesta regressao".
**Saida esperada:** Definir baseline, priorizar a camada dominante, limitar a resposta a uma hipotese por vez e amarrar a recomendacao a uma comparacao objetiva.

### Caso positivo

**Entrada:** Usuario relata lentidao generica na API, mas ainda nao sabe se o tempo esta na serializacao, no handler ou na query.
**Saida esperada:** Medir por camada, localizar o gargalo dominante e fazer handoff para a skill especializada assim que a causa deixar de ser difusa.

### Caso negativo

**Entrada:** Usuario pede revisao de um componente React que re-renderiza demais apos cada digitacao.
**Por que nao:** O gargalo ja esta localizado no cliente React. Use `react-performance`.

### Caso negativo

**Entrada:** Usuario diz "essa query Postgres esta lenta; qual indice eu adiciono?".
**Por que nao:** O problema ja esta no banco. Use `database-design` ou `supabase`.

### Caso negativo

**Entrada:** Usuario diz "o bug as vezes trava e as vezes nao, preciso achar a causa raiz".
**Por que nao:** O problema dominante e reproducao e prova de causa raiz, nao triagem de performance. Use `systematic-debugging`.

## Evals de trigger

Deve acionar:

- "esta lento e nao sei onde esta o gargalo"
- "mede antes de otimizar"
- "quero comparar antes e depois dessa regressao"
- "qual gargalo atacar primeiro com evidencia"
- "a API ficou lenta mas ainda nao sei se o problema esta no backend ou no banco"

Nao deve acionar:

- "esse componente React re-renderiza demais"
- "otimiza essa query Postgres"
- "bug intermitente e as vezes trava"
- "roda os checks do repo"
- "testa o fluxo de login no navegador"

## Evals de workflow

### Cenario 1 - sintoma difuso com ambiente mensuravel

Entrada: pagina web ficou lenta depois de uma feature e ainda nao esta claro se o custo principal esta no browser, na API ou na query.

Assertions:

- [ ] output escolhe uma metrica observavel antes de sugerir mudanca
- [ ] output registra baseline ou estado atual mensuravel
- [ ] output identifica uma camada dominante ou uma hipotese lider apoiada por evidencia
- [ ] output limita o proximo passo a uma investigacao ou mudanca por vez
- [ ] output aponta a skill de handoff se o gargalo deixou de ser difuso

### Cenario 2 - sem baseline viavel

Entrada: owner pede otimizacao, mas nao existe URL executavel, fixture, comando reproduzivel nem metrica confiavel no ambiente atual.

Assertions:

- [ ] output declara explicitamente o bloqueio de medicao
- [ ] output identifica o menor artefato faltante para criar baseline
- [ ] output evita recomendar micro-otimizacao como se fosse evidente
- [ ] output define o proximo passo para desbloquear medicao

### Cenario 3 - gargalo localizado durante a triagem

Entrada: a investigacao inicial mostra que a lentidao vem de waterfall React e bundle inicial pesado.

Assertions:

- [ ] output explica por que o caso deixou de ser triagem cross-layer
- [ ] output encaminha o owner principal para `frontend-design`
- [ ] output preserva a evidencia coletada para o handoff
- [ ] output explicita o que deve ser validado depois da intervencao

### Cenario 4 - intervencao com comparacao antes/depois

Entrada: pedido inclui aplicar uma mudanca de performance depois de medir o baseline.

Assertions:

- [ ] output mantem uma mudanca por rodada
- [ ] output compara antes e depois com a mesma metrica
- [ ] output registra ausencia de delta quando a melhora nao for mensuravel
- [ ] output evita empilhar outras otimizacoes antes de concluir a comparacao

## Referencias

Leia apenas o arquivo necessario para a decisao em maos:

| Necessidade                                                        | Ler                       | Extrair                                                                |
| ------------------------------------------------------------------ | ------------------------- | ---------------------------------------------------------------------- |
| Escolher metrica, ferramenta inicial e skill de handoff por camada | `references/reference.md` | matriz de sintoma, medicao minima, ferramenta de apoio e skill vizinha |
