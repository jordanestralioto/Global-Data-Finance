# Testing Patterns - Exemplos de Referência

Exemplos completos demonstrando a derivação de **contrato → casos de teste →
assertions concretas** para regras de negócio, limites, transições de estado,
falhas de dependência, efeitos colaterais, concorrência e isolamento.

## Sumário

- [Exemplo 1: Regra de Negócio com Limites e Transições de Estado](#exemplo-1-regra-de-negocio-com-limites-e-transicoes-de-estado)
- [Exemplo 2: Integração com Falha de Dependência e Efeitos Colaterais](#exemplo-2-integracao-com-falha-de-dependencia-e-efeitos-colaterais)
- [Exemplo 3: Concorrência e Idempotência](#exemplo-3-concorrencia-e-idempotencia)
- [Exemplo 4: Isolamento Multi-Tenant e Negativos de Segurança](#exemplo-4-isolamento-multi-tenant-e-negativos-de-seguranca)
- [Exemplo 5: Caso Negativo (Quando NÃO usar testing-patterns)](#exemplo-5-caso-negativo-quando-nao-usar-testing-patterns)

______________________________________________________________________

## Exemplo 1: Regra de Negócio com Limites e Transições de Estado

### Contrato

```python
# calculate_discount(subtotal: Decimal, coupon: Coupon) -> Decimal
# Regras:
# 1. Rejeita subtotal <= 0 com InvalidAmountError.
# 2. Rejeita se coupon.status != CouponStatus.ACTIVE com CouponInactiveError.
# 3. Rejeita se subtotal < coupon.min_order_value com MinimumOrderValueError.
# 4. Aplica percentual de 15% (coupon.percentage = Decimal('0.15')).
# 5. Desconto não pode exceder coupon.max_discount_amount (teto de 50.00).
# 6. Se coupon.used_count + 1 >= coupon.max_uses, incrementa used_count e transiciona para CouponStatus.EXHAUSTED.
```

### Derivação de Casos

- **Limites de subtotal**:
  - `subtotal = 0.00` e `-1.00` → `InvalidAmountError`
  - `subtotal = 99.99` (limiar min = 100.00) → `MinimumOrderValueError`
  - `subtotal = 100.00` (exatamente o limiar, 15%) → desconto exato de `15.00`
  - `subtotal = 1000.00` (15% de 1000 seria 150.00, mas teto = 50.00) → desconto exato de `50.00`
- **Transições de estado do cupom (`max_uses = 10`)**:
  - Status `DRAFT` ou `EXPIRED` → `CouponInactiveError`
  - Status `EXHAUSTED` → `CouponInactiveError`
  - Status `ACTIVE` com `used_count = 8` (8 de 10 usos) → ao aplicar (9º uso), `used_count` vai para 9 e status permanece `ACTIVE` (`9 < 10`).
  - Status `ACTIVE` com `used_count = 9` (9 de 10 usos) → ao aplicar (10º e último uso permitido), `used_count` vai para 10 e status transiciona para `EXHAUSTED` (`10 >= 10`).

### Implementação Concreta de Testes

```python
from decimal import Decimal
from typing import Any
import pytest


def make_coupon(**kwargs: Any) -> Coupon:
    defaults = {
        'code': 'PROMO15',
        'percentage': Decimal('0.15'),
        'min_order_value': Decimal('100.00'),
        'max_discount_amount': Decimal('50.00'),
        'status': CouponStatus.ACTIVE,
        'max_uses': 10,
        'used_count': 0,
    }
    return Coupon(**(defaults | kwargs))


def test_discount_rejects_subtotal_below_minimum_threshold() -> None:
    coupon = make_coupon()
    with pytest.raises(MinimumOrderValueError) as exc:
        calculate_discount(Decimal('99.99'), coupon)
    assert 'Subtotal abaixo do valor mínimo de 100.00' in str(exc.value)


def test_discount_applies_exact_percentage_at_minimum_boundary() -> None:
    coupon = make_coupon()
    assert calculate_discount(Decimal('100.00'), coupon) == Decimal('15.00')


def test_discount_caps_at_maximum_discount_ceiling() -> None:
    coupon = make_coupon()
    assert calculate_discount(Decimal('1000.00'), coupon) == Decimal('50.00')


def test_coupon_remains_active_before_final_use() -> None:
    coupon = make_coupon(used_count=8)  # 8º uso; próximo será o 9º
    calculate_discount(Decimal('100.00'), coupon)
    assert coupon.used_count == 9 and coupon.status == CouponStatus.ACTIVE


def test_coupon_transitions_to_exhausted_on_final_allowed_use() -> None:
    coupon = make_coupon(used_count=9)  # 9º uso; próximo será o 10º (último)
    calculate_discount(Decimal('100.00'), coupon)
    assert coupon.used_count == 10 and coupon.status == CouponStatus.EXHAUSTED


def test_coupon_in_draft_or_expired_or_exhausted_state_is_rejected() -> None:
    for invalid_status in (
        CouponStatus.DRAFT,
        CouponStatus.EXPIRED,
        CouponStatus.EXHAUSTED,
    ):
        coupon = make_coupon(status=invalid_status)
        with pytest.raises(CouponInactiveError) as exc:
            calculate_discount(Decimal('100.00'), coupon)
        assert exc.value.status == invalid_status
```

______________________________________________________________________

## Exemplo 2: Integração com Falha de Dependência e Efeitos Colaterais

### Contrato

```python
# OrderFulfillmentService.fulfill_order(order_id: str) -> None
# Dependências:
# - order_repo: OrderRepository (banco local/in-memory)
# - payment_client: PaymentGatewayClient (boundary HTTP externo: charge(order_id, amount))
# - event_bus: EventBus (mensageria externa)
```

### Regras de Negócio e Falhas

- **Caminho Feliz**: cobra o cartão via `payment_client` → atualiza `order.status = PAID` no `order_repo` → publica evento `order.paid` com `{order_id, amount}` no `event_bus`.
- **Falha de Timeout**: se `payment_client` lançar `GatewayTimeoutException`, efetua até 2 retries; se esgotar, marca `order.status = PAYMENT_PENDING` e **NÃO** publica evento de pedido pago.
- **Falha Permanente**: se `payment_client` lançar `CardDeclinedException`, marca `order.status = FAILED`, reverte reservas e emite `order.payment_failed`.

### Implementação Concreta de Testes

```python
from decimal import Decimal
from unittest.mock import MagicMock
import pytest


def test_fulfill_order_success_persists_paid_status_and_emits_event() -> None:
    order_repo = InMemoryOrderRepository()
    order_repo.create(
        id='ord_123', amount=Decimal('150.00'), status=OrderStatus.PENDING
    )

    mock_payment = MagicMock()
    mock_payment.charge.return_value = {'transaction_id': 'tx_999'}

    mock_event_bus = MagicMock()

    service = OrderFulfillmentService(
        order_repo=order_repo,
        payment_client=mock_payment,
        event_bus=mock_event_bus,
    )
    service.fulfill_order('ord_123')

    # 1. Verifica efeito no banco
    updated = order_repo.get_by_id('ord_123')
    assert updated.status == OrderStatus.PAID
    assert updated.transaction_id == 'tx_999'

    # 2. Verifica chamada exata ao mock externo
    mock_payment.charge.assert_called_once_with(
        order_id='ord_123', amount=Decimal('150.00')
    )

    # 3. Verifica emissão de evento com payload exato
    mock_event_bus.publish.assert_called_once_with(
        topic='order.paid',
        payload={'order_id': 'ord_123', 'amount': '150.00', 'tx': 'tx_999'},
    )


def test_fulfill_order_on_timeout_retries_twice_and_does_not_emit_paid_event() -> (
    None
):
    order_repo = InMemoryOrderRepository()
    order_repo.create(
        id='ord_timeout', amount=Decimal('50.00'), status=OrderStatus.PENDING
    )

    mock_payment = MagicMock()
    mock_payment.charge.side_effect = GatewayTimeoutException(
        'Connection timed out'
    )

    mock_event_bus = MagicMock()

    service = OrderFulfillmentService(
        order_repo=order_repo,
        payment_client=mock_payment,
        event_bus=mock_event_bus,
    )

    with pytest.raises(GatewayTimeoutException):
        service.fulfill_order('ord_timeout')

    # 1. Verifica política de retry: tentativa inicial + 2 retries = 3 chamadas
    assert mock_payment.charge.call_count == 3

    # 2. Verifica estado no banco: marcado como PENDING para conciliação
    updated = order_repo.get_by_id('ord_timeout')
    assert updated.status == OrderStatus.PAYMENT_PENDING

    # 3. Assegura ausência de efeito colateral indevido no broker
    mock_event_bus.publish.assert_not_called()
```

______________________________________________________________________

## Exemplo 3: Concorrência e Idempotência

### Contrato

```python
# WalletService.debit(wallet_id: str, amount: Decimal, idempotency_key: str) -> DebitReceipt
# Invariantes:
# 1. Requisições paralelas disputando saldo limitado não podem gerar saldo negativo (prevenção de double-spend via OCC com version_id).
# 2. Política de Idempotência:
#    - Chamadas concorrentes com a mesma chave enquanto uma operação está em andamento (in-flight) são rejeitadas com DuplicateIdempotencyKeyError (conflito 409).
#    - Chamadas posteriores com a mesma chave após a conclusão retornam o mesmo recibo original do cache sem novo débito (saldo debitado 1x).
```

### Coordenação no Ponto Crítico

- **Sessões Isoladas e Pré-condição OCC**: Cada thread opera sobre uma sessão independente (`db.create_session()`), comprovando antes da mutação que ambas leem snapshot próprio com `version_id = 1` e `balance = 100.00`. A sincronização com `threading.Barrier(2)` ocorre no save da sessão antes da gravação, simulando o commit concorrente no banco.
- **Validação de Timeouts em `Event.wait`**: O teste asserte explicitamente os retornos de `wait(timeout=5)`, impedindo que uma espera expirada passe despercebida.
- **Restauração de Mocks**: Toda interceptação temporária é restaurada antes de finalizações ou scoped por sessão.

### Implementação Concreta de Testes

```python
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import threading
import pytest


def test_concurrent_debits_prevent_double_spend_under_occ() -> None:
    db = DatabaseWalletRepository()
    db.create(id='w_race', balance=Decimal('100.00'), version_id=1)

    save_barrier = threading.Barrier(2)
    results, errors, lock = [], [], threading.Lock()

    def perform_debit_in_session(key: str) -> None:
        session_repo = db.create_session()
        service = WalletService(wallet_repo=session_repo)

        # Pré-condição comprovada: cada sessão lê seu snapshot próprio (version_id=1)
        snapshot = session_repo.get_by_id('w_race')
        assert snapshot.version_id == 1
        assert snapshot.balance == Decimal('100.00')

        orig_save = session_repo.save

        def synchronized_save(w: Wallet) -> None:
            assert save_barrier.wait(timeout=5) >= 0
            orig_save(w)

        session_repo.save = synchronized_save
        try:
            receipt = service.debit('w_race', Decimal('80.00'), key)
            with lock:
                results.append(receipt)
        except (InsufficientFundsError, ConcurrencyConflictError) as exc:
            with lock:
                errors.append(exc)

    with ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(perform_debit_in_session, 'user_a_key')
        f2 = executor.submit(perform_debit_in_session, 'user_b_key')
        f1.result()
        f2.result()

    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], ConcurrencyConflictError)

    final_wallet = db.create_session().get_by_id('w_race')
    assert final_wallet.balance == Decimal('20.00')
    assert final_wallet.version_id == 2


def test_concurrent_idempotency_key_guarantees_single_execution() -> None:
    db = DatabaseWalletRepository()
    db.create(id='w_shared', balance=Decimal('100.00'), version_id=1)
    idempotency_repo = IdempotencyRepository()
    service = WalletService(
        wallet_repo=db.create_session(), idempotency_repo=idempotency_repo
    )

    in_flight_event, can_complete_event = threading.Event(), threading.Event()
    original_reserve = idempotency_repo.reserve_or_get

    def coordinated_reserve(key: str) -> tuple[bool, DebitReceipt | None]:
        acquired, receipt = original_reserve(key)
        if acquired:
            in_flight_event.set()
            assert can_complete_event.wait(timeout=5), (
                'Timeout aguardando colisão da thread 2'
            )
        return acquired, receipt

    idempotency_repo.reserve_or_get = coordinated_reserve
    results, errors, lock = [], [], threading.Lock()

    def perform_call(is_primary: bool) -> None:
        if not is_primary:
            assert in_flight_event.wait(timeout=5), (
                'Timeout aguardando thread 1 in-flight'
            )
        try:
            receipt = service.debit('w_shared', Decimal('30.00'), 'key_123')
            with lock:
                results.append(receipt)
        except DuplicateIdempotencyKeyError as exc:
            with lock:
                errors.append(exc)
        finally:
            if not is_primary:
                can_complete_event.set()

    try:
        with ThreadPoolExecutor(max_workers=2) as executor:
            f1 = executor.submit(perform_call, True)
            f2 = executor.submit(perform_call, False)
            f1.result()
            f2.result()
    finally:
        idempotency_repo.reserve_or_get = original_reserve

    assert len(results) == 1
    assert len(errors) == 1
    assert isinstance(errors[0], DuplicateIdempotencyKeyError)
    assert db.get_by_id('w_shared').balance == Decimal('70.00')

    subsequent = service.debit('w_shared', Decimal('30.00'), 'key_123')
    assert subsequent.transaction_id == results[0].transaction_id
    assert db.get_by_id('w_shared').balance == Decimal('70.00')
```

______________________________________________________________________

## Exemplo 4: Isolamento Multi-Tenant e Negativos de Segurança

### Contrato

```http
GET /api/v1/workspaces/{workspace_id}/invoices/{invoice_id}
Authorization: Bearer <jwt_token>

Política de Sigilo de Existência:
- Fatura de outro tenant no próprio workspace: estritamente HTTP 404 Not Found (não revela existência de dados alheios).
- Acesso à rota de workspace alheio sem permissão: estritamente HTTP 403 Forbidden.
- Requisições sem credenciais ou com token expirado: estritamente HTTP 401 Unauthorized.
```

### Derivação de Casos e Controle Positivo

1. **Criação de Workspaces e Recursos**: Cria os tenants `ws_alfa` e `ws_beta` no repositório e faturas reais em cada um.
2. **Controle Positivo Duplo**: Comprova com HTTP 200 que Alfa lê sua fatura e Beta lê sua fatura, validando credenciais, rotas e existência de dados.
3. **Teste de Acesso Cruzado Bidirecional**:
   - Beta requisita fatura de Alfa na rota de Beta: espera estritamente HTTP 404 Not Found (sigilo de existência).
   - Beta requisita na rota do workspace Alfa: espera estritamente HTTP 403 Forbidden.
   - Alfa requisita fatura de Beta na rota de Alfa: espera estritamente HTTP 404 Not Found (sigilo de existência).
   - Alfa requisita na rota do workspace Beta: espera estritamente HTTP 403 Forbidden.
4. **Sanitização de Payload e Headers**:
   - Valida que identificadores, títulos e valores nunca constam em `resp.text` nem em valores de headers.
   - Valida ausência de headers de metadados (`x-resource-id`, `location`).
5. **Controles de Autenticação**: Valida token ausente (HTTP 401) e token expirado (HTTP 401).

### Implementação Concreta de Testes

```python
from decimal import Decimal
from httpx import AsyncClient
import pytest


@pytest.mark.asyncio
async def test_bidirectional_tenant_isolation_and_header_sanitization(
    test_client: AsyncClient,
    workspace_repo: WorkspaceRepository,
    invoice_repo: InvoiceRepository,
) -> None:
    ws_alfa = workspace_repo.create(name='Workspace Alfa')
    ws_beta = workspace_repo.create(name='Workspace Beta')

    headers_alfa = create_auth_headers('user_alfa', ws_alfa.id)
    headers_beta = create_auth_headers('user_beta', ws_beta.id)

    inv_alfa = invoice_repo.create(
        workspace_id=ws_alfa.id,
        amount=Decimal('1000.00'),
        title='Consultoria Alfa Confidencial',
    )
    inv_beta = invoice_repo.create(
        workspace_id=ws_beta.id,
        amount=Decimal('250.00'),
        title='Licença Beta',
    )

    # 1. Controles Positivos Duplos
    resp_alfa = await test_client.get(
        f'/api/v1/workspaces/{ws_alfa.id}/invoices/{inv_alfa.id}',
        headers=headers_alfa,
    )
    assert resp_alfa.status_code == 200
    assert resp_alfa.json()['id'] == inv_alfa.id
    assert resp_alfa.json()['amount'] == '1000.00'

    resp_beta = await test_client.get(
        f'/api/v1/workspaces/{ws_beta.id}/invoices/{inv_beta.id}',
        headers=headers_beta,
    )
    assert resp_beta.status_code == 200
    assert resp_beta.json()['id'] == inv_beta.id
    assert resp_beta.json()['amount'] == '250.00'

    # 2. Acesso Cruzado Bidirecional com status codes exatos contratados
    alfa_secrets = (inv_alfa.id, 'Consultoria Alfa Confidencial', '1000.00')
    beta_secrets = (inv_beta.id, 'Licença Beta', '250.00')
    cross_matrix = [
        (
            headers_beta,
            f'/api/v1/workspaces/{ws_beta.id}/invoices/{inv_alfa.id}',
            alfa_secrets,
            404,
        ),
        (
            headers_beta,
            f'/api/v1/workspaces/{ws_alfa.id}/invoices/{inv_alfa.id}',
            alfa_secrets,
            403,
        ),
        (
            headers_alfa,
            f'/api/v1/workspaces/{ws_alfa.id}/invoices/{inv_beta.id}',
            beta_secrets,
            404,
        ),
        (
            headers_alfa,
            f'/api/v1/workspaces/{ws_beta.id}/invoices/{inv_beta.id}',
            beta_secrets,
            403,
        ),
    ]

    for (
        client_hdrs,
        cross_url,
        protected_strings,
        expected_status,
    ) in cross_matrix:
        resp_cross = await test_client.get(cross_url, headers=client_hdrs)
        assert resp_cross.status_code == expected_status
        for secret_str in protected_strings:
            assert secret_str not in resp_cross.text
            for h_val in resp_cross.headers.values():
                assert secret_str not in h_val
        assert 'x-resource-id' not in resp_cross.headers
        assert 'location' not in resp_cross.headers


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'headers,expected_error',
    [
        ({}, 'unauthorized'),
        (create_expired_auth_headers('user_expired'), 'token_expired'),
    ],
)
async def test_invalid_auth_token_rejected_at_middleware_boundary(
    test_client: AsyncClient, headers: dict[str, str], expected_error: str
) -> None:
    response = await test_client.get(
        '/api/v1/workspaces/ws_any/invoices/any',
        headers=headers,
    )
    assert response.status_code == 401
    assert response.json()['error'] == expected_error
```

______________________________________________________________________

## Exemplo 5: Caso Negativo (Quando NÃO usar testing-patterns)

**Entrada:** Usuário solicita: *"Execute `uv run pytest` no projeto e me diga se passou."*

**Por quê NÃO acionar:** Essa é uma tarefa puramente operacional de execução e
verificação de gates. A skill `testing-patterns` serve para planejar a
estratégia, derivar cenários e escrever testes robustos. Para apenas rodar a
suíte existente, use `lint-and-validate` ou execute o comando nativo
diretamente no terminal.
