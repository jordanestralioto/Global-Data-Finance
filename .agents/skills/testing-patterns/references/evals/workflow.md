# Workflow Evals

Cenários de workflow para validar se a skill produz planos de teste e código no
nível de engenharia sênior, com contratos concretos, derivação sistemática e
critérios binários verificáveis.

______________________________________________________________________

## Cenário 1: Regra de Negócio com Limiares e Transição de Estado

### Contrato

```python
# calculate_discount(subtotal: Decimal, coupon: Coupon) -> Decimal
# - Subtotal mínimo de 100.00 para ativar cupom de 15%.
# - Teto máximo de desconto de 50.00.
# - Subtotal <= 0 levanta InvalidAmountError.
# - Subtotal < 100.00 levanta MinimumOrderValueError.
# - Cupom com status != ACTIVE levanta CouponInactiveError.
# - Limite de 10 usos (max_uses = 10): ao atingir o 10º uso, transiciona status para EXHAUSTED.
```

### Entrada do Usuário

"Escreva a estratégia e os testes unitários para a regra de desconto de cupom
com 15% de desconto descrita no contrato, cobrindo limites de valor e transição
de estado."

### Resposta Esperada

- Nível especificado: `unit` (lógica pura sem dependências externas).
- Casos de limite derivados: `subtotal = 99.99` (rejeição), `100.00` (desconto
  exato 15.00), `1000.00` (teto de 50.00).
- Casos de estado: rejeição para `DRAFT`, `EXPIRED`, `EXHAUSTED`.
- Transição de estado: cupom no 9º uso mantém `ACTIVE` (9 < 10); no 10º e último
  uso permitido transiciona para `EXHAUSTED` (10 >= 10).
- Código executável em pytest com assertions numéricas exatas.

### Assertions Verificáveis

- [ ] especifica o nível de teste como 'unit' com justificativa de cálculo puro sem I/O
- [ ] inclui caso de teste para o limiar inferior imediato (`subtotal = 99.99` com `MinimumOrderValueError`)
- [ ] inclui caso de teste para o limiar exato (`subtotal = 100.00` com assert exato de `Decimal('15.00')`)
- [ ] inclui caso de teste para o teto de desconto (`subtotal = 1000.00` com assert exato de `Decimal('50.00')`)
- [ ] inclui teste para o ciclo de vida do cupom rejeitando `DRAFT`, `EXPIRED` e `EXHAUSTED`
- [ ] inclui teste provando que no último uso permitido o status do cupom transiciona para `EXHAUSTED`
- [ ] não utiliza mocks para a lógica de cálculo ou para o objeto de cupom
- [ ] asserções verificam valores numéricos exatos, sem asserts genéricos como `assert res is not None`

______________________________________________________________________

## Cenário 2: Integração com Falha de Dependência Externa e Efeitos Colaterais

### Contrato

```python
# OrderFulfillmentService.fulfill_order(order_id: str)
# - Busca pedido no OrderRepository (banco).
# - Chama PaymentGatewayClient.charge(order_id, amount) (API externa).
# - Sucesso: persiste OrderStatus.PAID no repositório e emite evento 'order.paid' via EventBus.
# - Timeout no Gateway: efetua 2 retries; se esgotar, persiste OrderStatus.PAYMENT_PENDING e NÃO emite 'order.paid'.
```

### Entrada do Usuário

"Preciso de testes para o `OrderFulfillmentService`. Como testo o caminho feliz
e a resiliência a falhas de timeout do gateway de pagamento?"

### Resposta Esperada

- Nível especificado: `integration` com boundary mocking.
- Mock estritamente delimitado a `PaymentGatewayClient` e `EventBus`.
- Repositório operando com banco real ou repositório in-memory confiável (sem
  mockar a persistência).
- Cenário de timeout simula `GatewayTimeoutException` com asserção do número de
  retries e verificação de que nenhum evento de pedido pago foi publicado.

### Assertions Verificáveis

- [ ] especifica o nível de teste como 'integration'
- [ ] isola exclusivamente as boundaries externas instáveis (`PaymentGatewayClient` e `EventBus`) com mocks
- [ ] não mocka o `OrderRepository` sob teste nem a orquestração do serviço
- [ ] assert no caminho feliz verifica persistência de `OrderStatus.PAID` no repositório
- [ ] assert no caminho feliz verifica `EventBus.publish` chamado com tópico 'order.paid' e payload estruturado
- [ ] assert de timeout simula `GatewayTimeoutException` e verifica exatamente 3 tentativas (1 inicial + 2 retries)
- [ ] assert de timeout verifica que o status no repositório é gravado como `PAYMENT_PENDING`
- [ ] assert de timeout verifica que `EventBus.publish` não foi chamado

______________________________________________________________________

## Cenário 3: Concorrência e Deduplicação por Chave de Idempotência

### Contrato

```python
# WalletService.debit(wallet_id: str, amount: Decimal, idempotency_key: str) -> DebitReceipt
# Invariantes:
# 1. Saldo inicial 100.00. Duas chamadas simultâneas tentam debitar 80.00 cada.
# 2. Apenas uma operação deve suceder; a outra deve falhar com erro de saldo insuficiente ou conflito.
# 3. Saldo final não pode ficar negativo.
# 4. Reenvio com a mesma idempotency_key retorna o recibo original sem debitar novamente.
```

### Entrada do Usuário

"Como testo race condition e idempotência no serviço de débito de carteira para
evitar double-spend quando há requisições simultâneas?"

### Resposta Esperada

- Teste concorrente simulando requisições paralelas sobre sessões
  independentes, comprovando leitura prévia de `version_id = 1` e coordenando
  colisão atômica com `threading.Barrier(2)` no commit (OCC).
- Asserção de que exatamente um débito conclui e o outro falha por
  conflito de versão (`ConcurrencyConflictError`).
- Asserção de que o saldo final é exatamente 20.00 e `version_id` é 2.
- Teste de idempotência provando que disputa in-flight com a mesma chave é
  rejeitada com `DuplicateIdempotencyKeyError` e chamada subsequente retorna o
  mesmo recibo sem novo débito.
- Validação estrita dos retornos de espera (`Event.wait(timeout=5)`).

### Assertions Verificáveis

- [ ] desenha teste concorrente simulando duas requisições paralelas com sessões independentes
- [ ] comprova pré-condição de leitura com snapshot inicial de `version_id` e saldo
- [ ] sincroniza as threads no commit do OCC e valida retornos de espera da barreira e eventos
- [ ] assert comprova que exatamente uma requisição sucede e a outra falha por conflito de versão
- [ ] assert verifica que o saldo final é exatamente `Decimal('20.00')` e `version_id == 2`
- [ ] desenha teste de idempotência provando rejeição in-flight com `DuplicateIdempotencyKeyError`
- [ ] assert verifica retorno subsequente do recibo em cache e saldo debitado exatamente uma vez

______________________________________________________________________

## Cenário 4: Isolamento Multi-Tenant e Negativo de Segurança

### Contrato

```http
GET /api/v1/workspaces/{workspace_id}/invoices/{invoice_id}
Header: Authorization: Bearer <jwt>

Política de Sigilo de Existência:
- Fatura de outro tenant no próprio workspace: estritamente HTTP 404 Not Found (não revela existência de dados alheios).
- Acesso à rota de workspace alheio sem permissão: estritamente HTTP 403 Forbidden.
- Requisições sem credenciais ou com token expirado: estritamente HTTP 401 Unauthorized.
```

### Entrada do Usuário

"Desenhe testes de segurança para garantir que um usuário do Workspace Beta não
consiga ler uma fatura confidencial do Workspace Alfa."

### Resposta Esperada

- Fixture configurada com dois workspaces (`ws_alfa` e `ws_beta`) e recursos em
  cada um.
- Controle positivo duplo confirmando que Alfa lê fatura Alfa e Beta lê fatura
  Beta com HTTP 200.
- Teste de acesso cruzado bidirecional com status codes exatos contratados (404
  para sigilo de existência, 403 para workspace alheio).
- Verificação de ausência de vazamento de dados do recurso protegido no corpo e
  nos headers da resposta.
- Testes negativos complementares de token ausente e expirado (HTTP 401).

### Assertions Verificáveis

- [ ] fixture cria explicitamente dois workspaces distintos com recursos associados
- [ ] inclui controle positivo duplo comprovando que ambos os donos acessam seus recursos com HTTP 200
- [ ] assert verifica código exato HTTP 404 para sigilo de existência e HTTP 403 para workspace alheio
- [ ] assert verifica que o corpo e os headers da resposta de erro não contêm identificadores, títulos ou valores
- [ ] inclui teste negativo para token ausente retornando HTTP 401 Unauthorized
- [ ] inclui teste negativo para token com expiração vencida retornando HTTP 401 Unauthorized
- [ ] não mocka a política de segurança, o middleware de autorização ou a constraint de workspace
