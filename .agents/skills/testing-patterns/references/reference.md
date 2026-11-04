# Testing Strategy Reference

Use this reference to choose test level, design fixtures and mocks, derive
comprehensive test cases (boundaries, state transitions, dependency failures,
side effects, concurrency), and formulate non-tautological assertions.

## Sumario

- [Heurísticas de Nível de Teste](#heuristicas-de-nivel-de-teste)
- [Derivação Sistemática de Casos](#derivacao-sistematica-de-casos)
- [Mocks vs Fixtures: Regras de Ouro](#mocks-vs-fixtures-regras-de-ouro)
- [Matriz de Vetores de Segurança e Isolamento](#matriz-de-vetores-de-seguranca-e-isolamento)
- [Critérios de Assertions Não-Tautológicas](#criterios-de-assertions-nao-tautologicas)
- [Validação e Evidência Confiável](#validacao-e-evidencia-confiavel)

## Heurísticas de Nível de Teste

Escolha o menor nível que comprove o comportamento protegido com total
fidelidade:

| Nível             | Alvo Ideal                                                                                                                        | Custo                                            | O que NÃO cabe aqui                                                                         |
| :---------------- | :-------------------------------------------------------------------------------------------------------------------------------- | :----------------------------------------------- | :------------------------------------------------------------------------------------------ |
| **Unit**          | Funções puras, cálculos, parsers, validadores, serializadores, mappers e máquinas de estado puras.                                | Extremamente rápido, zero I/O externo.           | Testar transações no banco, middleware HTTP ou filas reais.                                 |
| **Integration**   | Repositórios, migrações, constraints de DB, RLS, middleware de auth/sessão, concorrência no banco, chamadas de boundary mockadas. | Médio, usa banco de teste efêmero ou containers. | Regras puras de parsing sem persistência; fluxos de UI que dependem de renderização visual. |
| **E2E / Browser** | Jornadas completas ponta a ponta, wiring de frontend com backend, regressões de layout ou interações exclusivas de navegador.     | Lento, suscetível a flakiness.                   | Testar matriz combinatória de limites numéricos ou validação de campos individuais.         |

## Derivação Sistemática de Casos

Para elevar a cobertura ao nível de engenharia sênior, derive cenários em cinco
dimensões essenciais:

### 1. Casos de Limite e Fronteira (Boundary Value Analysis)

Bugs de cálculo e indexação concentram-se nas bordas:

- **Off-by-one**: teste exatamente no limiar, um valor imediatamente abaixo e um
  imediatamente acima (ex: `n - 1`, `n`, `n + 1`).
- **Extremos numéricos**: valor zero, valores negativos quando não permitidos,
  valores decimais de ponto flutuante, estouro de capacidade máxima permitida.
- **Coleções**: coleção vazia `[]`, exatamente um elemento `[x]`, coleção com o
  número máximo permitido de itens, tentativa de ultrapassar a capacidade.
- **Strings e dados textuais**: string vazia `""`, strings contendo apenas
  espaços em branco (`"   "`), caracteres especiais, quebras de linha e unicode.

### 2. Transições e Máquinas de Estado (State Transitions)

Entidades com ciclo de vida (ex: pedidos, faturas, inscrições):

- **Transições válidas**: comprove a progressão ordenada (ex: `DRAFT -> PENDING -> APPROVED -> COMPLETED`).
- **Transições proibidas**: tente forçar transições ilegais (ex: `COMPLETED -> PENDING` ou `CANCELLED -> APPROVED`); assert deve verificar erro tipado e
  permanência do estado anterior sem mutação.
- **Idempotência**: repetir uma ação de transição no mesmo estado não deve
  gerar cobranças adicionais, mutações duplicadas ou corrupção de dados.

### 3. Falhas e Resiliência de Dependências (Dependency Failures)

Sistemas reais operam sobre dependências instáveis:

- **Timeout e perda de conexão**: configure o mock da API externa para simular
  demora excessiva (`TimeoutException`); verifique se o serviço trata
  graciosamente sem travar a thread.
- **Erros HTTP upstream**: simule respostas 429 (rate limit), 500 (internal
  error) e 503 (service unavailable) da boundary externa.
- **Política de retry e fallback**: verifique se o número de tentativas
  respeita o limite configurado e se o fallback é acionado quando as
  tentativas se esgotam.
- **Rollback de transação**: se a chamada externa falhar no meio do fluxo,
  verifique se nenhuma mutação parcial no banco foi persistida indevidamente.

### 4. Efeitos Colaterais Observáveis (Side Effects)

Um teste completo valida não apenas o retorno direto da função, mas todas as
mutações causadas:

- **Persistência no banco**: consulte o repositório ou tabela para confirmar que
  o registro foi gravado com todos os campos e carimbos de data/hora corretos.
- **Emissão de eventos**: confira se o broker de mensagens recebeu exatamente o
  evento esperado com o payload estruturado correto.
- **Chamadas de terceiros**: assegure que clientes mockados (ex: Stripe, SES,
  Twilio) receberam os parâmetros precisos, usando `assert_called_with` com
  dados concretos.
- **Ausência de efeitos colaterais em erro**: se a operação foi rejeitada,
  verifique que nenhum registro novo foi inserido e nenhum evento foi emitido.

### 5. Concorrência e Condições de Corrida (Concurrency & Races)

- **Optimistic Locking**: simule duas atualizações concorrentes sobre a mesma
  versão de um registro; verifique que a primeira vence e a segunda falha com
  conflito (HTTP 409 ou StaleObjectError).
- **Deduplicação por Idempotency Key**: duas requisições idênticas enviadas
  concorrentemente devem processar a ação apenas uma única vez.
- **Prevenção de Double-Spend**: teste dois débitos concorrentes de saldo que
  superem o saldo disponível; certifique-se de que o saldo nunca fica negativo.

## Mocks vs Fixtures: Regras de Ouro

- **O que MOCKAR**: dependências externas instáveis, caras ou lentas (rede HTTP,
  gateways de pagamento, envio de email/SMS, filas em nuvem, relógio do
  sistema).
- **O que NÃO MOCKAR**: a regra de negócio central, validadores, serializadores,
  parsers, políticas de tenant, transações locais e o repositório sob teste.
  Mockar a própria lógica sob teste resulta em testes tautológicos que sempre
  passam, mesmo quando a implementação está quebrada.
- **Arrange explícito**: fixtures devem fornecer os dados mínimos necessários
  para o teste rodar, sem dependências invisíveis compartilhadas.

## Matriz de Vetores de Segurança e Isolamento

| Vetor                          | Caso Mínimo Exigido                                                       | Assertion Concreta                                                                  |
| :----------------------------- | :------------------------------------------------------------------------ | :---------------------------------------------------------------------------------- |
| **Isolamento de Tenant**       | Usuário de Workspace B tenta acessar recurso de Workspace A.              | HTTP 404 ou 403; payload sanitizado sem dados do recurso; log sem vazar segredos.   |
| **Sessão Expirada**            | Token JWT com `exp` expirado ou sessão invalidada.                        | HTTP 401 Unauthorized; rota rejeita imediatamente antes de consultar o banco.       |
| **Token Ausente / Malformado** | Header `Authorization` ausente, vazio ou com token corrompido.            | HTTP 401; nenhuma consulta a dados protegidos é executada.                          |
| **Escopo Insuficiente**        | Token válido de leitura tenta executar mutação protegida (`POST/DELETE`). | HTTP 403 Forbidden com código tipado `INSUFFICIENT_PERMISSIONS`.                    |
| **Vazamento de Segredo**       | Resposta de erro da API ou log de auditoria em cenário de exceção.        | Comprovar ausência de tokens, senhas, chaves de API e connection strings no output. |

## Critérios de Assertions Não-Tautológicas

- **Evite asserts vazios**: `assert res is not None` ou `assert res == True` não
  provam que o cálculo ou estado estão corretos. Verifique valores específicos.
- **Evite snapshots cegos**: snapshots amplos mascaram regressões sutis e geram
  fadiga de atualização. Prefira asserts explícitos em campos-chave.
- **Verifique código de erro tipado**: além do status HTTP (ex: 400 ou 422),
  valide o identificador do erro (ex: `{"code": "QUANTITY_EXCEEDED"}`).
- **Teste RED / GREEN**: modifique mentalmente ou temporariamente a lógica; se o
  teste continuar passando com a regra removida, o teste é tautológico.

## Validação e Evidência Confiável

- **Evidência de testes descobertos**: nunca considere uma suíte aprovada se o
  runner retornou código 0 com zero testes executados (`total: 0`) ou se todos
  os testes foram pulados (`all_skipped`).
- **Caminho correto**: confirme que o comando foi disparado apontando para o
  diretório ou arquivo de teste correto, não para um diretório vazio.
- **Tratamento de Skip**: skips devem ser justificados e auditados, nunca
  usados para mascarar falhas ativas de implementação.
