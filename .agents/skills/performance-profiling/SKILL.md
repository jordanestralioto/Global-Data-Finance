---
name: performance-profiling
description: >-
  Use para medir e localizar o gargalo quando a lentidão ainda pode estar no
  navegador, API ou banco. Ative com "está lento e não sei onde", "mede
  antes/depois", "qual gargalo atacar primeiro?" ou "a API ficou lenta, mas não
  sei se é backend ou banco". Cobre baseline, profiling e comparação. Se o
  gargalo já aponta para renderização, waterfall ou bundle de um app React/Next,
  use `react-performance`; para query SQL identificada, use `database-design`.
  Para bloqueio comprovado do event loop Node, use `nodejs-best-practices`;
  para capacidade de processos ou workers, `server-management`. Não use para
  testes de navegador ou bugs sem sintoma de performance.
---

# Performance Profiling

## Procedimento

1. Determine se o gargalo já está localizado. Se estiver, a triagem terminou:
   React/Next no cliente vai para `react-performance`; query, para
   `database-design`; event loop Node, para
   `nodejs-best-practices`; processos ou workers, para `server-management`. Sem
   sinal claro de performance, use `systematic-debugging`; para checks
   repo-native, `lint-and-validate`; para jornada ou E2E como pedido principal,
   `webapp-testing`. Se a skill indicada não estiver instalada, descreva a
   especialidade necessária, a evidência e o próximo passo; não invente caminhos
   nem declare o handoff executado.

2. Defina o sintoma em uma métrica observável antes de propor mudança: LCP, INP,
   tempo de request, latência de handler, tempo de query, CPU, memória, bundle ou throughput.

3. Escolha a menor medição executável pela camada mais provável:

   - browser: Lighthouse para navegação; trace de Performance e rede para interações, pela ferramenta de navegador disponível (por exemplo, Chrome DevTools MCP, quando instalado)
   - API: `curl` para tempos do request e logs/traces para separar handler, serialização e banco
   - banco: tempo da query e plano de execução no ambiente de diagnóstico

   Leia `references/measurement.md` somente para montar essa coleta: ele traz
   comandos para navegação, interação, request, CPU Python, event loop Node e
   query, com condições de comparação e limites de interpretação. Use ferramentas
   existentes no consumidor antes de adicionar instrumentação.

4. Colete um baseline com comando ou roteiro, versão, entrada, estado de cache,
   concorrência e condições de CPU/rede registrados. Repita a medição para conhecer
   a variação. Sem ambiente ou artefato reproduzível, declare o bloqueio e o menor
   dado faltante; não recomende micro-otimização especulativa.

5. Isole a camada dominante com a menor evidência suficiente. Faça handoff assim
   que o gargalo estiver localizado, preservando os dados e a comparação pendente.

6. Se a triagem ainda pertencer a esta skill, escolha a menor intervenção ligada
   à métrica observada. Quando houver implementação, teste uma intervenção por
   rodada. Uma intervenção pode exigir vários arquivos; o limite é a hipótese,
   não a contagem de arquivos.

7. Compare antes/depois com a mesma métrica, método e condições. Registre amostras
   e variação; uma diferença dentro do ruído não comprova melhora. Sem delta
   mensurável, registre a ausência de ganho e prefira reverter a empilhar otimizações.

## Heurísticas

- Um score agregado ajuda a detectar regressão, mas não localiza a causa.
- Tempo de resposta do documento não identifica sozinho o custo de API ou banco;
  confirme com timings dessas etapas antes de atribuir a causa.
- TBT de navegação não equivale a INP. Investigue interação com roteiro e trace,
  distinguindo evidência de laboratório de dados de usuários reais.

## Contrato de saída

### Quando o sintoma ainda é difuso e há ambiente mensurável

Entregue:

- sintoma e métrica escolhida
- baseline com comando/roteiro, condições, amostras e variação observada
- camada priorizada e evidência do gargalo dominante ou hipótese líder
- próximo passo e skill disponível de handoff, quando aplicável
- comparação esperada depois da intervenção

### Quando não existe baseline viável

Entregue:

- sintoma e impedimento concreto à medição
- menor artefato faltante e próximo passo para obtê-lo
- ausência explícita de recomendação especulativa de micro-otimização

### Quando o gargalo já está localizado

Entregue:

- por que a triagem entre camadas terminou
- especialidade responsável e disponibilidade da skill indicada
- evidência coletada e o que medir depois da intervenção

## Uso de scripts

- Execute `python3 .agents/skills/performance-profiling/scripts/lighthouse_audit.py <url>`
  quando houver URL executável e a suspeita inicial estiver na navegação do browser.
  O helper requer Lighthouse CLI e Chrome no ambiente; não instala ferramentas.
- O helper recebe apenas a URL, sem cookies nem headers. Em página que exige login,
  ele mede a tela de login ou o redirect; meça essa jornada pelo trace de Performance
  do navegador com a sessão autenticada.
- A saída JSON contém `scores.performance`, `metrics`, até cinco `diagnostics`,
  versão do Lighthouse e configurações de medição. Executa apenas a categoria performance.
  O score é arredondado para inteiro de 0 a 100; estimativas booleanas são ignoradas.
- `metrics` preserva `numericValue`, `numericUnit` e `displayValue` disponíveis.
  Métricas ausentes, sem valor ou indisponíveis na versão são `null`, nunca zero.
  TTI e tempo de resposta do servidor são diagnósticos opcionais legados.
- Os diagnósticos priorizam a maior economia estimada em ms, depois o score.
  São pistas para investigação, não prova da camada responsável nem ganhos somáveis.
- O helper faz uma navegação sem interações. INP normalmente será `null`; não
  apresente TBT como substituto de INP ou resultado de laboratório como dado de campo.
- Sucesso termina com código `0`; falha de execução, timeout, relatório inválido
  ou score indisponível termina com código `1` e JSON com `error`.
- Trate o helper como baseline opcional. Para backend ou banco, meça essas etapas
  diretamente; a nota do Lighthouse não substitui seus timings.

## Exemplos

### Caso positivo

**Entrada:** Usuário diz "a tela está lenta e não sei se o problema é bundle, request ou backend".
**Saída esperada:** Escolher métrica, coletar baseline repetível e encaminhar a camada dominante com evidência.

### Caso positivo

**Entrada:** Usuário pede "quero evidência antes/depois para decidir qual gargalo atacar primeiro".
**Saída esperada:** Registrar condições e variação, testar uma hipótese por rodada e comparar sem atribuir ganho ao ruído.

### Caso negativo

**Entrada:** Usuário pede revisão de componente React que re-renderiza após cada digitação.
**Por quê não:** O problema já está no cliente React. Use `react-performance`, se disponível.

### Caso negativo

**Entrada:** Usuário diz "essa query Postgres está lenta; qual índice eu adiciono?".
**Por quê não:** O problema já está no banco. Use `database-design`, se disponível.

### Caso negativo

**Entrada:** Usuário diz "o bug às vezes trava e às vezes não; preciso achar a causa raiz".
**Por quê não:** Sem sinal claro de performance, o trabalho dominante é reprodução e causa raiz. Use `systematic-debugging`.
