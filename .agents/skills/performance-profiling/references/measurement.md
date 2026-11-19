# Coleta executável de evidência

Leia somente a seção da camada escolhida. Use comandos e dependências existentes
no consumidor; a falta de uma ferramenta não autoriza inventar medições.

## Sumário

- [Request HTTP sem instrumentação da aplicação](#request-http-sem-instrumenta%C3%A7%C3%A3o-da-aplica%C3%A7%C3%A3o)
- [Navegação e interação no browser](#navega%C3%A7%C3%A3o-e-intera%C3%A7%C3%A3o-no-browser)
- [CPU Python após isolar o processo suspeito](#cpu-python-ap%C3%B3s-isolar-o-processo-suspeito)
- [Event loop Node após isolar o processo](#event-loop-node-ap%C3%B3s-isolar-o-processo)
- [Query identificada em Postgres](#query-identificada-em-postgres)

## Request HTTP sem instrumentação da aplicação

Para um GET reproduzível, substitua a URL e mantenha os mesmos parâmetros em
todas as amostras:

```bash
curl --silent --show-error --location --output /dev/null \
  --write-out 'status=%{http_code} dns=%{time_namelookup} connect=%{time_connect} tls=%{time_appconnect} first_byte=%{time_starttransfer} total=%{time_total} redirects=%{time_redirect}\n' \
  'http://localhost:8000/example'
```

Os tempos são em segundos e cumulativos. Para uma conexão nova sem redirect,
`connect - dns` aproxima o TCP, `tls - connect` aproxima o handshake HTTPS e
`total - first_byte` aproxima a transferência após o primeiro byte. Não
trate `tls=0` em HTTP como duração negativa. Com redirects ou conexão
reutilizada, não atribua essas diferenças a uma etapa sem examinar o percurso.

TTFB inclui rede e processamento até o primeiro byte. Um valor alto não prova
que a query esteja lenta. Correlacione o mesmo request com logs ou spans de
handler, chamadas externas, serialização e banco, evitando somar spans aninhados.
Registre também status HTTP e quantidade de queries: uma página de erro rápida
não é um baseline válido da jornada esperada.

## Navegação e interação no browser

```bash
python3 .agents/skills/performance-profiling/scripts/lighthouse_audit.py \
  'http://localhost:3000/example'
```

Compare valores e unidades, não apenas o score. Registre a versão e
`configSettings` devolvidos pelo helper; mantenha dispositivo, throttling,
entrada, cache e carga equivalentes. Faça amostras repetidas e relate a variação,
sem escolher apenas a melhor execução. Use build representativo do ambiente
afetado, pois servidor de desenvolvimento e extensões podem distorcer o resultado.

O helper resume até cinco audits que falharam, ordenados pela maior economia
estimada de tempo e depois pelo score. `estimatedSavingsMs=null` significa que
não havia estimativa; economias de audits distintos podem se sobrepor.

Para uma interação lenta, use as ferramentas de navegador disponíveis para
reproduzir a mesma ação e salvar trace de Performance e requests. Relacione o
input com long tasks, renderização e rede. Se a integração só expõe requests,
ela não prova o custo da thread principal: registre essa limitação e indique
o trace faltante. Não presuma que Chrome DevTools MCP ou Playwright estão instalados.

INP exige interações; uma navegação sem ações normalmente não o produz. TBT é
um sinal de bloqueio durante o carregamento e não um valor substituto de INP.
Dados de laboratório não representam automaticamente os percentis de usuários reais.

IDs variam por versão. Lighthouse 13 introduziu a substituição de audits antigos
por insights como `document-latency-insight`; sua configuração ainda lista
`server-response-time` e `interactive` como ocultos, apesar do anúncio de remoção
dos audits antigos do JSON. Consuma os campos presentes, sem exigir os legados.
TTI deixou de ser métrica principal desde Lighthouse 10. O helper preserva esses
valores apenas quando disponíveis e representa ausências com `null`.

Fontes: [migração no Lighthouse 13](https://developer.chrome.com/blog/lighthouse-13-0),
[configuração da versão 13.0.0](https://github.com/GoogleChrome/lighthouse/blob/v13.0.0/core/config/default-config.js),
[limites de TTI](https://developer.chrome.com/docs/lighthouse/performance/interactive)
e [diferenças entre laboratório e campo](https://web.dev/articles/lab-and-field-data-differences).

## CPU Python após isolar o processo suspeito

```bash
python -m cProfile -o /tmp/request-profile.pstats path/to/reproducer.py
python -m pstats /tmp/request-profile.pstats
```

No prompt de `pstats`, use `sort cumulative` e `stats 20` para localizar custo
acumulado, depois `sort time` para custo próprio. Perfis incluem overhead;
compare a latência sem profiler antes/depois. `cProfile` não substitui um trace
de I/O concorrente nem mede automaticamente uma aplicação não escrita em Python.

## Event loop Node após isolar o processo

Meça durante a reprodução do sintoma, com o processo real em uso. Os valores do
histograma estão em nanossegundos; divida por `1e6` para milissegundos. O trecho
abaixo é ESM (`.mjs`), que aceita `await` no nível superior:

```js
import { monitorEventLoopDelay } from 'node:perf_hooks';

const histogram = monitorEventLoopDelay({ resolution: 10 });
histogram.enable();
// Aquecimento: sem esta espera, um bloqueio imediato pode não aparecer no histograma.
await new Promise((resolve) => setTimeout(resolve, 50));
// ... dispare a operação suspeita aqui e aguarde sua conclusão ...
await new Promise((resolve) => setTimeout(resolve, 50));
histogram.disable();
console.log(JSON.stringify({ p99_ms: histogram.percentile(99) / 1e6, max_ms: histogram.max / 1e6 }));
```

Em teste local com um bloqueio síncrono de 300 ms, o histograma reportou 11 ms
sem o aquecimento e cerca de 310 ms com ele. Um `max_ms` alto ligado à operação
suspeita é evidência de bloqueio do event loop. Nesta janela curta há poucas
amostras e `p99_ms` tende a igualar `max_ms`; para distinguir bloqueios
recorrentes, meça em uma janela longa com o processo sob carga. Para localizar a
função, gere um perfil com
`node --cpu-prof --cpu-prof-dir=<dir> <script>` e importe o `.cpuprofile` no painel
Performance do Chrome DevTools. Perfis incluem overhead; compare a latência sem o
profiler antes de concluir.

## Query identificada em Postgres

Use os mesmos parâmetros e volume representativo em ambiente de diagnóstico.
Para uma query de leitura cujo custo real possa ser executado nesse ambiente:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT id FROM example WHERE status = 'pending';
```

`ANALYZE` executa a query. Confirme o comando e o ambiente antes de medir;
comandos de escrita e funções com efeitos exigem fixture ou ambiente descartável.
Sem condição de executar, obtenha apenas o plano com `EXPLAIN` e declare que
o tempo real não foi medido. Examine estimativas versus linhas reais, loops e
buffers; um scan sequencial pode ser adequado a uma tabela pequena.

Se `pg_stat_statements` já estiver disponível, use suas estatísticas para
localizar queries frequentes e custo agregado. Não instale extensões nem zere
estatísticas compartilhadas para obter baseline. Preserve SQL, parâmetros e
plano para o encaminhamento à skill de banco.
