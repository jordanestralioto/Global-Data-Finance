# Streaming Contracts

> Defina o ciclo de vida do trabalho e do transporte; abrir o canal é só o começo.

## Escolha do cliente e do transporte

| Caso                          | Contrato a definir                                                                                 |
| ----------------------------- | -------------------------------------------------------------------------------------------------- |
| EventSource nativo            | GET com `text/event-stream`; opções de credenciais do browser; reconexão e IDs de evento           |
| fetch com POST e resposta SSE | Input/body e headers explícitos; parser incremental; cancelamento e retry implementados no cliente |
| Job + canal de eventos        | POST idempotente cria trabalho durável; stream acompanha job com autorização própria               |
| WebSocket                     | Autenticação no handshake, autorização das mensagens, expiração, heartbeat e limites               |

Não prometa reconexão automática de EventSource para um `fetch`. O formato SSE
pode ser usado na resposta a POST, mas o cliente precisa implementar parsing e
retomada. Boundaries de chunks não são boundaries de eventos: aceite linhas
fragmentadas, CRLF e múltiplos eventos em um mesmo chunk.

## Antes de abrir o canal

- Valide authn/authz, input e escopo do recurso.
- Reserve quota/custo com operação atômica antes de iniciar o provider.
- Defina limite de duração, bytes/eventos, conexões simultâneas e custo upstream.
- Sanitize falhas de início usando o contrato HTTP do projeto.
- Após enviar headers, status HTTP não pode comunicar falhas posteriores:
  defina evento de erro sanitizado, evento final e comportamento de fechamento.

## Cancelamento e cleanup

Modele a cadeia explicitamente:

```text
cliente cancela/fecha -> transporte avisa servidor -> sinal de cancelamento
  -> provider/worker interrompe -> libera reader/conexão -> reconcilia reserva
```

Propague `AbortSignal` ou o mecanismo equivalente da linguagem até o upstream.
Cancelar o reader no browser não comprova que o provider parou. Use `finally`,
defer ou cleanup equivalente para liberar conexões, subscriptions e slots.
Defina como confirmar consumo parcial e devolver reservas não utilizadas.

Um job durável pode continuar após a desconexão por decisão de produto. Nesse
caso, separe acompanhar o job de cancelá-lo e autorize a operação de cancelamento.

## Reconexão e retomada

- Em EventSource, emita `id:` quando a retomada existir; `Last-Event-ID` informa
  o último ID conhecido na reconexão.
- Defina retenção, ordenação, expiração do cursor, duplicatas e reação a gaps.
- Em fetch/POST, implemente cursor e backoff explicitamente. Reenviar o POST pode
  duplicar trabalho; use chave persistida ou reconecte a um job já criado.
- Revalide auth e tenant na retomada. Encerre/rejeite após expiração ou revogação
  conforme o mecanismo de sessão e os limites do projeto.
- Não use reconexão automática infinita para repetir erros permanentes.

## Proxies e backpressure

Verifique cliente, ingress, CDN, proxy e servidor real antes de sugerir headers.
Em NGINX, `X-Accel-Buffering: no` pode desabilitar buffering quando a configuração
permite; não é uma garantia universal de flush em toda infraestrutura.

Use `Content-Type: text/event-stream`, política de cache compatível com dados
autenticados e heartbeat quando necessário para timeouts intermediários. Respeite
backpressure; limite buffers por conexão e não acumule eventos sem limite para
clientes lentos. Não force headers de conexão próprios de HTTP/1 em HTTP/2.

## Evidência de teste

- Cancelar o cliente interrompe o upstream quando esse for o contrato.
- Falha no provider após headers produz o evento de erro e cleanup esperados.
- Reconexão retoma com cursor sem vazamento entre tenants ou efeitos duplicados.
- Cliente lento e stream ocioso respeitam limites de buffer e timeout.
- Quota, expiração e revogação são exercitadas antes e durante o stream.

## Fontes primárias

- [WHATWG: Server-sent events](https://html.spec.whatwg.org/multipage/server-sent-events.html).
- [NGINX: proxy buffering](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_buffering).
