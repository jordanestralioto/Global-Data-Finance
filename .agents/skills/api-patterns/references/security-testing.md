# API Security Testing

> Teste APIs por caller, trust boundary, recurso protegido e exposição de resposta.
> Prefira testes negativos que provam o controle — não apenas que o happy path funciona.

## OWASP API Security Top 10

| Vulnerabilidade                | Foco do teste                                                                  |
| ------------------------------ | ------------------------------------------------------------------------------ |
| **API1: BOLA**                 | Acessar recurso de outro usuário ou tenant mudando IDs                         |
| **API2: Broken Auth**          | Credenciais ausentes, malformadas, expiradas, de tenant errado ou scope errado |
| **API3: Property Auth**        | Mass assignment, campos ocultos, propriedades excessivas na resposta           |
| **API4: Resource Consumption** | Rate limit, duração de stream, chamadas caras a provider/backend               |
| **API5: Function Auth**        | Funções de admin/workspace alcançadas por caller de menor privilégio           |
| **API6: Business Flow**        | Mudanças de estado fora de ordem, abuso de automação, replay                   |
| **API7: SSRF**                 | URL ou proxy target controlado pelo usuário alcança sistemas internos/upstream |
| **API8: Misconfiguration**     | Debug endpoints, CORS permissivo, erros verbosos, headers ausentes             |
| **API9: Inventory**            | Rotas deprecadas ou shadow que bypassam middleware atual                       |
| **API10: Unsafe Consumption**  | Confiar em respostas de provider/backend sem validação ou sanitização          |

## Testes por superfície

| Superfície        | Cenário negativo                                                   | Evidência esperada                                                                   |
| ----------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| Bearer auth       | Token ausente, expirado, malformado ou de outro usuário            | Rejeitado antes de qualquer dado ou chamada externa                                  |
| `X-API-Key`       | Chave inválida, revogada, de workspace errado ou capability errada | Falha com erro sanitizado e sem log do segredo                                       |
| Recurso protegido | Usuário B requisita recurso, sessão ou stream do usuário A         | Ownership check ou predicate de tenant rejeita                                       |
| SSE stream        | Token torna-se inválido ou tenant mismatch antes/durante o stream  | Stream não expõe eventos anteriores ou cross-tenant                                  |
| RFC 9457 errors   | Falha de backend/provider inclui detalhes sensíveis                | Resposta inclui `code` e request id, mas sem token, key, stack ou segredo upstream   |
| Backend proxy     | Input do usuário tenta bypass de path/host/version arbitrário      | Allow-list do proxy ou route mapping rejeita targets inesperados                     |
| Rate limit        | Mesmo caller repete requisições caras ou mutações sensíveis        | Limite é escopado por user/key/workspace e não pode ser bypassado por headers comuns |
| CORS              | Origin não confiável faz chamada a rota com credenciais            | Política de origin bloqueia exposição de credenciais                                 |
| Action remota     | Invocação direta sem passar pela página protegida                  | Authn/authz e schema são verificados na action ou serviço chamado                    |
| Stream cancelado  | Cliente fecha durante chamada cara ao upstream                     | Upstream interrompido e recursos/reservas reconciliados conforme o contrato          |

## BOLA/IDOR — Passo a passo

1. Identifique IDs em path, query, body, cache key, stream channel e route state.
2. Use o recurso do usuário A com as credenciais do usuário B.
3. Replaye apenas o shape mínimo e seguro de requisição necessário para provar o comportamento de autorização.
4. Espere `403`, `404` ou erro sanitizado compatível com o estilo da API — qualquer payload protegido é um finding.
5. Verifique também a camada de dados: filtragem no handler é mais fraca do que predicate no repositório ou RLS.

## Auth e Session — Checklist

| Verificação        | O que testar                                                                                                    |
| ------------------ | --------------------------------------------------------------------------------------------------------------- |
| Validação de token | Assinatura/algoritmo, expiração, issuer, audience, subject, claim de tenant/workspace                           |
| Estado de sessão   | Bootstrap antes do carregamento de dados, expiração, refresh, invalidação no logout, comportamento de reconexão |
| API key            | Escopo, tenant binding, revogação, rotação, rate limit, redação                                                 |
| Tratamento de erro | Resposta sanitizada, código estável, request id, sem vazamento de credencial ou provider                        |

## Rate Limit — Bypass patterns

- Tente escopo por user vs workspace vs API key.
- Verifique `X-Forwarded-For`, casing, mudanças de método, aliases de rota e versões de API.
- Confirme que calls SSE/chat/provider são limitadas antes do trabalho caro começar.
- Trate limite ausente com severidade baseada no ativo protegido e impacto de custo/disponibilidade — não apenas na categoria.

## Output para revisão de segurança

```yaml
api_security_guidance:
  surface: <rota, stream, proxy, key, ou error path>
  negative_tests:
    - <cenário 1>
    - <cenário 2>
  expected_control: <authz, rate limit, sanitizer, allow-list>
  evidence_needed:
    - <handler, middleware, repo, policy, test>
  residual_risk:
    - <risco remanescente se controle falhar>
```
