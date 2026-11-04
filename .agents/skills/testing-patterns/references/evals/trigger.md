# Trigger Evals

## Deve acionar

### Caso 1

Pedido: "Essa feature precisa de unit, integration ou e2e?"

Assertions:

- [ ] aciona `testing-patterns`
- [ ] escolhe menor nível confiável
- [ ] explica trade-off de custo e confiança

### Caso 2

Pedido: "Quais mocks são aceitáveis para cobrir este serviço externo?"

Assertions:

- [ ] aciona `testing-patterns`
- [ ] diferencia boundary externa de lógica sob teste
- [ ] não recomenda mockar regra de negócio central

### Caso 3

Pedido: "Como desenho casos de limite e transições de estado para este cupom?"

Assertions:

- [ ] aciona `testing-patterns`
- [ ] deriva casos de fronteira (off-by-one, extremos numéricos)
- [ ] deriva transições válidas e rejeição de estados inválidos

### Caso 4

Pedido: "Como testo se este endpoint sofre de race condition ou double-spend?"

Assertions:

- [ ] aciona `testing-patterns`
- [ ] identifica o risco de concorrência e propõe teste com requisições simultâneas
- [ ] formula assertions para estado invariante e deduplicação

### Caso 5

Pedido: "Preciso cobrir tenant errado e auth expirada."

Assertions:

- [ ] aciona `testing-patterns`
- [ ] inclui teste negativo de segurança
- [ ] pede fixtures com dois principals quando houver isolamento

## Não deve acionar

### Caso 1

Pedido: "Rode a validação repo-native e a suíte de testes."

Assertions:

- [ ] não aciona `testing-patterns`
- [ ] direciona para validação operacional (`lint-and-validate`)

### Caso 2

Pedido: "Modele o schema do banco e as migrations desta feature."

Assertions:

- [ ] não aciona `testing-patterns`
- [ ] direciona para `database-design`

### Caso 3

Pedido: "Crie testes E2E no Playwright para validar a tela de checkout no navegador."

Assertions:

- [ ] não aciona `testing-patterns`
- [ ] direciona para `webapp-testing`

### Caso 4

Pedido: "O fluxo já está implementado e coberto; só preciso reexecutar os checks."

Assertions:

- [ ] não aciona `testing-patterns`
- [ ] trata como validação operacional direta
