---
name: server-management
description: >-
  Use para subir, parar, supervisionar e diagnosticar processos de servidor,
  locais ou em produção: dev server em background, porta ocupada, health checks,
  graceful shutdown, sinais em containers, workers, logs e monitoramento. Ative
  com "servidor não sobe", "EADDRINUSE", "porta ocupada", "sobe o preview",
  "container demora para parar", "healthcheck", "PM2/systemd/docker", "quantos
  workers?" ou "ajusta graceful shutdown". Não use para rotas e contratos de API
  (`api-patterns`), modelagem de banco (`database-design`), lentidão sem gargalo
  isolado (`performance-profiling`) ou provisionamento de nuvem.
---

# Server Management

## Contexto não-óbvio

Agentes costumam errar com servidores por três atalhos: rodam o dev server em
primeiro plano e travam a sessão até o timeout; liberam a porta com `pkill node`,
`killall` ou `kill -9` por nome e derrubam processos do usuário; e declaram o
servidor parado sem conferir a porta, embora um filho (`npm` → `sh` → `node`)
continue escutando. Em produção, o erro equivalente é um graceful shutdown que
nunca roda porque o SIGTERM não chega ao processo da aplicação.

## Procedimento

1. Mapeie a topologia antes de mudar algo: comando real de entrada (incluindo
   wrappers `npm`, `sh -c` e o `CMD` do Docker), host e porta de bind, modelo
   de workers, supervisor, health checks e destino dos logs.
2. Diagnostique pela evidência: leia o erro real no log ou no supervisor
   (`EADDRINUSE`, variável ausente, bind em `127.0.0.1` dentro de container,
   migração pendente) antes de reiniciar ou trocar configuração.
3. Aplique a menor mudança que trate o mecanismo confirmado, usando as seções
   abaixo.
4. Valide a superfície alterada operando-a: start, readiness respondendo, stop
   e porta liberada. Configuração só escrita não prova que o processo funciona.

## Processos iniciados pelo agente

- Rode servidores de longa duração em background, com saída em arquivo de log.
  Prefira o mecanismo de background do próprio harness quando existir, porque
  ele rastreia e encerra o processo; sem ele, use `scripts/auto_preview.py`.
- Espere readiness por polling com timeout (health endpoint ou porta aceitando
  conexão), não com `sleep` fixo. Se o processo encerrar antes, leia o log em
  vez de repetir o start.
- Confirme a URL no log: nem todo dev server lê `PORT` (o Vite usa `--port` ou
  a config).
- Com a porta ocupada, identifique o dono antes de agir:
  `ss -ltnp 'sport = :3000'`, `lsof -nP -iTCP:3000 -sTCP:LISTEN` ou, no
  Windows, `Get-NetTCPConnection -LocalPort 3000 -State Listen`. Se for um
  servidor do usuário, reutilize-o ou use outra porta. Encerre apenas processos
  que você iniciou e cujo PID registrou.
- Ao parar, encerre a árvore do processo (o grupo, no POSIX) e confirme que a
  porta foi liberada.

## Sinais e graceful shutdown

- Garanta que o SIGTERM chegue à aplicação. `CMD` em shell form roda sob
  `/bin/sh -c`, que não repassa sinais; use exec form
  (`CMD ["node", "server.js"]`). Como PID 1, um processo sem handler ignora o
  SIGTERM e só morre no SIGKILL; use `--init` ou `init: true` no Compose, ou
  trate o sinal. Evite `npm start` e cadeias `a && b` como entrada de container.
- Se o servidor já trata o sinal (Uvicorn, Gunicorn, frameworks Node), use os
  hooks de shutdown dele (lifespan do FastAPI/Starlette, `server.close()`) em
  vez de registrar `signal.signal` ou `process.on('SIGTERM')` próprios, que
  podem substituir o handler do servidor e pular o drain.
- Ordem do drain: marque readiness como falha, pare de aceitar conexões,
  conclua requisições e jobs em andamento, feche pools e faça flush dos logs.
  Termine antes do prazo do supervisor (padrões: 10 s no `docker stop`, 30 s no
  Kubernetes, 1,6 s no PM2, que envia SIGINT), senão o SIGKILL interrompe o
  trabalho no meio.
- Em produção, todo processo de longa duração precisa de supervisor com restart
  em falha (systemd, `restart` do Docker/Compose, Kubernetes, PM2). Crash na
  inicialização vira loop de restart; leia o log antes de mexer no supervisor.

## Health checks

- Liveness responde se o processo está funcional e não consulta dependências:
  com o banco fora do ar, todas as réplicas reiniciariam em cascata.
- Readiness verifica dependências críticas e falha durante o drain, tirando a
  instância do balanceamento sem reiniciá-la.
- Inicialização lenta precisa de `startupProbe` (Kubernetes) ou `start_period`
  (Docker); sem isso, a liveness mata o processo antes de ele subir.
- Workers sem HTTP (filas, cron) usam probe de comando ou heartbeat com prazo,
  não um endpoint artificial.

## Workers e capacidade

- Evite fórmulas fixas como `(2 * núcleos) + 1`. Comece com a menor
  configuração operável e aumente quando medições mostrarem saturação de CPU,
  fila de conexões ou piora de latência p95/p99.
- Em containers, dimensione pelas cotas de cgroup (`limits.cpu`,
  `limits.memory`), não por `nproc` ou `os.cpu_count()`, que podem enxergar o
  host e provocar throttling ou OOMKilled.
- Workers síncronos bloqueiam durante I/O, e a RAM costuma ser o limite:
  `workers_max ≈ (RAM disponível − SO e serviços) / RSS p95 por worker`.
- A soma dos pools de todos os workers e réplicas precisa caber no banco:
  `réplicas × workers × pool ≤ max_connections`.
- Escalar horizontalmente exige estado fora do processo: sessões, cache,
  uploads e agendadores em memória se duplicam ou divergem a cada réplica ou
  worker. Corrija gargalos de código antes de escalar.

## Logs

Escreva em stdout/stderr com campos estruturados e um ID de correlação por
requisição; em container, arquivo local sem rotação enche o disco e some com o
container. Não registre secrets, tokens, PII, SQL ou payloads completos.

## Scripts

- `scripts/auto_preview.py start [porta]|stop|status`: sobe o script `dev` ou
  `start` do `package.json` em background, com log em `.agents/preview.log` e
  `PORT` definido. No Linux, confirma a identidade do processo registrado e
  encerra o grupo do preview só por pidfd, nunca pelo número do grupo (membro a
  membro antes do kernel 6.9); no Windows, encerra a árvore.
  Recusa operar sem handle seguro de processo (por exemplo, no macOS) e não
  espera readiness: confirme URL e porta no log.
- Cada ação imprime um objeto JSON com `action`, `status` e, quando houver,
  `pid`, `port`, `requested_url`, `log` e `diagnostic`. `start` devolve
  `started` ou `already_running`; `stop`, `stopped` ou `not_running`;
  `status`, `running` ou `stopped`. `requested_url` é a URL pedida, não a
  confirmada. `not_running` também cobre estado salvo sem identidade
  verificável ou com PID de outro processo, descartado sem sinalizar nada.
- Sai com `0` nesses status, `1` com `status: error` e `2` para argumento
  inválido. Em `error`, leia `diagnostic`; `stop` e `status` mantêm o estado
  salvo quando o processo não pôde ser inspecionado ou encerrado. Se `start`
  lança o processo mas não consegue registrá-lo, tenta encerrá-lo, descarta o
  estado parcial e informa o `pid`; quando `diagnostic` diz que o encerramento
  também falhou, esse processo pode continuar rodando.

## Exemplos

### Caso positivo

**Entrada:** "Roda o dev server para eu ver a tela; deu `EADDRINUSE :3000`."
**Saída esperada:** Identificar o dono da porta; se for servidor do usuário,
reutilizá-lo ou subir em outra porta, sem `pkill`; iniciar em background com
log, esperar readiness por polling e, ao final, parar o que iniciou e conferir
a porta livre.

### Caso positivo

**Entrada:** "Implementei handler de SIGTERM, mas o container leva 10 s para
parar e corta requisições."
**Saída esperada:** Inspecionar `CMD` e entrypoint; apontar shell form ou
`npm start` como PID 1 sem repasse de sinal; trocar para exec form ou `--init`;
reproduzir com `docker stop` e medir o tempo de parada.

### Caso negativo

**Entrada:** "A API está lenta e não sei se é código, banco ou rede."
**Por quê não:** Gargalo não localizado; use `performance-profiling` antes de
mexer em workers.

### Caso negativo

**Entrada:** "Desenha o schema das tabelas de pedidos."
**Por quê não:** Modelagem de dados pertence a `database-design`.

Se a skill indicada não estiver instalada, descreva a especialidade necessária,
a evidência e o próximo passo; não invente o resultado dela nem declare o
encaminhamento executado.
