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

Para evitar aprovações enganosas, um teste só é considerado aprovado quando há
evidência concreta de testes descobertos e executados com sucesso; zero testes
descobertos ou suítes onde todos os testes foram pulados constituem falha de
evidência.

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
   - Posicione mocks exclusivamente nas boundaries externas instáveis. Mantenha
     a regra sob teste e a persistência local reais.

5. Formule assertions concretas (Arrange, Act, Assert).

   - **Arrange** cria dados e configura o estado inicial de forma explícita.
   - **Act** dispara a ação observável sob teste.
   - **Assert** valida valores exatos, códigos de status, payloads estruturados,
     efeitos persistidos no banco e chamadas externas esperadas. Evite asserts
     apenas `truthy`, `assert res is not None` ou snapshots cegos.

6. Valide contra tautologia e exija evidência real.

   - O teste deve falhar se o controle ou a regra for removida (RED/GREEN).
   - Nunca considere aprovada uma execução de teste que reportou zero testes
     coletados ou onde todos os testes foram pulados.

## Formato de saída

Ao desenhar estratégias e escrever testes para o usuário, entregue:

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

Complemente com o bloco executável de implementação (`test_implementation`)
contendo o código concreto do teste com Arrange, Act e Assert estruturados.

## Scripts

- `scripts/test_runner.py`: helper opcional para detectar e executar comandos
  proporcionais (`pytest`, `vitest`, `jest`, `npm test`). Exige evidência de
  testes descobertos e aprovados (`total > 0` e `passed > 0`), rejeitando
  aprovações com zero testes executados ou quando todos são pulados. Use
  `--dry-run` para apenas inspecionar o comando detectado.

## Referencias

Consulte o arquivo relevante para o tipo de teste necessário:

| Tópico                                                              | Arquivo                        |
| :------------------------------------------------------------------ | :----------------------------- |
| Heurísticas de limites, estados, dependências, concorrência e mocks | `references/reference.md`      |
| Exemplos de contrato → casos → assertions concretas                 | `references/examples.md`       |
| Exemplos de triggers e near-misses                                  | `references/evals/trigger.md`  |
| Cenários de workflow com critérios binários verificáveis            | `references/evals/workflow.md` |

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

## Evals de trigger

Deve acionar:

- "qual teste cobre essa regressão?"
- "escreva testes para esta regra de negócio"
- "como testo casos de limite e transições de estado?"
- "como testo concorrência e race condition neste endpoint?"
- "como testo falha de timeout da API externa?"
- "essa assertion prova o bug ou é tautológica?"
- "mocko esse provider como?"
- "escreva testes para garantir que o tenant B não acesse dado do tenant A"

Não deve acionar:

- "coordena a suíte inteira de validação"
- "roda a validação repo-native e testes"
- "modele o schema do banco desta feature"
- "crie testes E2E com Playwright gravando vídeo no navegador"
- "audita a acessibilidade visual da tela"

## Evals de workflow

### Cenário 1: Regra de negócio com limiares e transição de cupom

Assertions:

- [ ] define nível de teste como 'unit' com justificativa de cálculo puro sem I/O
- [ ] deriva casos de limite inferior (`subtotal = 99.99`), exato (`100.00`) e teto (`1000.00`)
- [ ] testa transição de estado de `ACTIVE` para `EXHAUSTED` no último uso permitido
- [ ] código fornecido utiliza asserções numéricas exatas sem asserts apenas truthy
- [ ] não utiliza mocks para a lógica de cálculo ou entidade de cupom

### Cenário 2: Falha de dependência externa e side effects

Assertions:

- [ ] escolhe nível 'integration' com mocks restritos às boundaries externas instáveis
- [ ] não mocka o repositório sob teste nem a lógica de orquestração interna
- [ ] simula timeout da dependência externa verificando retries configurados
- [ ] assert verifica que status no banco é gravado como `PAYMENT_PENDING`
- [ ] assert verifica ausência de publicação indevida de evento no broker em caso de falha

### Cenário 3: Concorrência e idempotência

Assertions:

- [ ] propõe teste concorrente simulando duas requisições paralelas sobre saldo finito
- [ ] valida pré-condição de leitura isolada com sessões independentes e version_id inicial
- [ ] sincroniza as threads no ponto crítico de gravação (OCC) e valida retornos de espera
- [ ] assert comprova que exatamente uma requisição conclui e a outra falha por conflito de versão
- [ ] assert verifica que o saldo final é debitado exatamente uma vez (20.00), nunca negativo
- [ ] assert comprova política de idempotência: rejeição concorrente in-flight e cache após conclusão

### Cenário 4: Isolamento multi-tenant

Assertions:

- [ ] cria fixture explícita com dois workspaces distintos e recursos associados
- [ ] inclui controle positivo duplo comprovando que ambos os donos acessam seus recursos com HTTP 200
- [ ] assert verifica rejeição bidirecional com status codes exatos contratados (404 para sigilo e 403 para workspace)
- [ ] assert valida ausência de dados do recurso em corpo e headers da resposta
- [ ] inclui casos de teste para token ausente e expirado retornando HTTP 401
- [ ] não substitui a regra de autorização ou filtro de workspace por mocks
