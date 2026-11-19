---
name: testing-patterns
description: >-
  Use para planejar ou escrever testes unitários e de integração que comprovem
  regras, limites, transições de estado, falhas externas, concorrência e
  isolamento de segurança. Ative com "que teste cobre essa regressão?",
  "escreva testes para esta regra", "como testo casos de limite?", "mocko esse
  provider como?", "como testo auth expirada?" ou "essa assertion prova o bug?".
  Oriente nível de teste, fixtures, mocks e asserções observáveis. Não use
  apenas para executar checagens (`lint-and-validate`), coordenar E2E no
  navegador (`webapp-testing`) ou conduzir TDD explícito com teste falhando
  antes da correção.
---

# Testing Patterns

## Fundamentos

Teste de alta fidelidade prova comportamento protegido no menor nível confiável,
cobrindo regras de negócio, limites numéricos, transições de ciclo de vida,
resiliência a falhas de dependências externas, efeitos colaterais observáveis,
concorrência e isolamento.

O erro caro é mockar a própria lógica sob teste ou criar testes ponta a ponta
pesados para mascarar a falta de asserções simples no limite correto. Use mocks
para dependências externas lentas, caras ou instáveis: rede HTTP, gateways de
pagamento, provedores de email/SMS, filas assíncronas em nuvem, storage e clock.
Não use mock para substituir a regra de negócio sob teste, máquina de estados,
validador, serializador, predicate de tenant, política de autorização ou
transação de banco.

## Procedimento

1. Nomeie o contrato e os riscos.

   - Escreva o teste em termos de comportamento protegido: "rejects subtotal
     below minimum order threshold" ou "tenant B cannot read tenant A invoice",
     em vez de apenas citar o nome da função.
   - Identifique entradas, saídas esperadas, pré-condições, pós-condições e
     invariantes de integridade.

2. Escolha o menor nível confiável.

   - **Unit**: funções puras, cálculos numéricos, parsers, validadores,
     serializadores, mappers e máquinas de estado isoladas de I/O.
   - **Integration**: repositórios, persistência no banco, constraints, RLS,
     middleware de auth/sessão, concorrência de banco, transações e wiring de
     boundaries externas mockadas.
   - **E2E / Browser**: jornadas completas do usuário, wiring entre frontend e
     backend ou regressões exclusivas de navegador.

3. Derive cenários sistemáticos em dimensões essenciais.

   - **Limites e bordas**: analise off-by-one (`n - 1`, `n`, `n + 1`), extremos
     (zero, negativos, capacidade máxima), coleções vazias/unitárias e strings
     vazias ou com caracteres especiais.
   - **Transições de estado**: valide a sequência permitida do ciclo de vida,
     rejeição com erro tipado em transições proibidas e idempotência em ações
     repetidas.
   - **Falhas de dependência**: simule timeout de rede, erro 5xx upstream,
     esgotamento de retries e certifique-se de que não ocorrem mutações
     parciais no banco (rollback limpo).
   - **Efeitos colaterais**: valide o estado persistido no repositório, mensagens
     emitidas no broker com payload exato e chamadas a terceiros com argumentos
     precisos.
   - **Concorrência e condição de corrida**: teste requisições simultâneas para
     prevenir double-spend, validar locks otimistas e checar deduplicação via
     chave de idempotência.
   - **Segurança e isolamento**: crie fixtures com dois tenants/usuários e dois
     recursos; cubra tokens ausentes, expirados e malformados; valide ausência
     de segredos em logs e respostas de erro.

4. Desenhe fixtures e mocks.

   - Mantenha fixtures minimalistas e autocontidas, gerando apenas os dados
     estritamente necessários para o teste.
   - Mocke só as boundaries externas descritas em Fundamentos; a regra sob teste
     e a persistência local ficam reais.

5. Formule assertions concretas, com Arrange, Act e Assert explícitos. Valide
   valores exatos, códigos de status, payloads estruturados, efeitos persistidos
   no banco e chamadas externas esperadas. Asserts apenas `truthy`,
   `assert res is not None` ou snapshots cegos passam mesmo quando a regra
   quebra.

6. Valide contra tautologia e exija evidência real.

   - O teste deve falhar se o controle ou a regra for removida (RED/GREEN).
   - Não considere aprovada uma execução que coletou zero testes ou pulou todos:
     ela não exercitou a regra e passa por engano.

## Formato de saída

Proporcione a saída ao pedido. Para um teste pontual, entregue o código do teste
e uma linha com o comportamento protegido, o comando executado e a prova
RED/GREEN. Quando o pedido for uma estratégia, com várias regras, níveis ou
riscos, entregue antes do código o bloco abaixo, omitindo as dimensões que não
se aplicam em vez de preenchê-las:

```yaml
test_strategy:
  behavior: <comportamento protegido ou contrato sob teste>
  level: <unit|integration|e2e|manual-gate>
  fixtures:
    - <entidades, dados e principals mínimos>
  mocks:
    - <boundary externa isolada e motivo>
  test_cases:
    boundaries:
      - <caso de borda, off-by-one ou extremo numérico>
    state_transitions:
      - <transição válida ou rejeição de estado ilegal>
    dependency_failures:
      - <timeout, erro 5xx ou retry simulado>
    concurrency_or_side_effects:
      - <concorrência, idempotência ou emissão de evento>
    security_negatives:
      - <vetor de isolamento de tenant ou auth inválida>
  validation:
    command: <comando repo-native verificado>
    red_green_proof: <como provar que a asserção não é tautológica>
```

Em seguida, entregue o código executável dos testes.

## Scripts

- `scripts/test_runner.py`: helper opcional para detectar e executar comandos
  proporcionais (`pytest`, `vitest`, `jest`, `npm test`). Exige evidência de
  testes descobertos e aprovados (`total > 0` e `passed > 0`), rejeitando
  aprovações com zero testes executados ou quando todos são pulados. Use
  `--dry-run` para apenas inspecionar o comando detectado:
  `python3 <skill-dir>/scripts/test_runner.py <repo> --dry-run --output json`.
- O JSON traz `status`, `framework`, `command` e `result`. `planned` só
  descreve o comando e sai com `0`; `not_configured` indica que nenhum runner
  foi detectado e sai com `2`. Sem `--dry-run`, o runner nativo precisa estar
  instalado: `result` traz `status`, `counts` e `error`, e o script sai com `0`
  só em `passed`. `failed`, `timeout`, `blocked` (comando ausente),
  `no_tests_collected`, `all_skipped`, `no_passing_tests` e caminho
  inexistente saem com `1`.

## Referencias

Consulte o arquivo relevante para o tipo de teste necessário:

| Tópico                                                              | Arquivo                   |
| :------------------------------------------------------------------ | :------------------------ |
| Heurísticas de limites, estados, dependências, concorrência e mocks | `references/reference.md` |
| Exemplos de contrato → casos → assertions concretas                 | `references/examples.md`  |

## Exemplos

### Caso positivo 1: Regra de negócio com limites e transição de estado

**Entrada:** "Escreva testes para a função `calculate_discount(subtotal, coupon)`
com 15% de desconto, que exige subtotal mínimo de 100.00, tem teto de 50.00 e
esgota o cupom no décimo uso."

**Saída esperada:** Desenhar estratégia `unit`, derivar casos de limite (99.99,
100.00, 1000.00), ciclo de vida do cupom (`ACTIVE`, `EXHAUSTED`) e fornecer
código de teste executável com asserções numéricas exatas (`Decimal('15.00')` e
`Decimal('50.00')`).

### Caso positivo 2: Isolamento multi-tenant e segurança negativa

**Entrada:** "Desenhe testes para garantir que o usuário do Workspace B não leia
documentos confidenciais do Workspace A."

**Saída esperada:** Desenhar estratégia `integration`, criar fixture com dois
workspaces e faturas reais, incluir controle positivo com o dono acessando a
fatura com sucesso (HTTP 200), validar rejeição com status codes exatos (HTTP 404
para sigilo de existência e HTTP 403 para rota de outro workspace) sem vazamento
de dados em corpo ou headers, e testes de credenciais ausentes ou expiradas
retornando HTTP 401.

### Caso negativo

**Entrada:** "Execute `npm test` e me diga se passou."

**Por quê não:** Isso é execução operacional de suíte existente; utilize
`lint-and-validate` ou invoque o comando nativo diretamente.
