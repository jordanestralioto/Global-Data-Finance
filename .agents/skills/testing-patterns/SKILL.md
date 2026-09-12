---
name: testing-patterns
description: >-
  Use para planejar ou revisar testes unitários, integração, mocks, fixtures,
  regressões e negativos de segurança. Ative com "que teste escrevo?", "isso é
  unit ou integração?", "mocko isso como?", "como testo auth expirada?", "essa assertion prova o bug?" ou "cobertura fraca".
  Cobre asserções que pegam regressões reais sem testes tautológicos. Não use
  apenas para executar checagens (`lint-and-validate`), coordenar E2E no
  navegador (`webapp-testing`), validar UI visualmente ou conduzir TDD quando o
  usuário pediu um teste falhando antes da correção.
---

# Testing Patterns

## Fundamentos

Teste bom prova comportamento protegido no menor nivel confiavel. O erro caro e
mockar a propria logica sob teste, ou criar um E2E grande para esconder que falta
um assert simples no limite certo.

Use mocks para dependencias externas caras ou instaveis: rede, provider, fila,
email, clock, storage externo e APIs pagas. Nao use mock para substituir a regra
de negocio, predicate de tenant, policy, serializer ou autorizacao que precisa
ser provada.

Em seguranca, comece pelo teste negativo que reproduz o vetor original. Admin
acessando dado permitido raramente protege o sistema; usuario B bloqueado ao
tentar acessar recurso do usuario A protege.

## Procedimento

1. Nomeie o comportamento e o risco.

   - Escreva o teste em termos de contrato: "rejects expired token" ou "tenant B
     cannot list tenant A invoices", nao apenas o nome da funcao.

2. Escolha o menor nivel confiavel.

   - Unit: regra pura, parser, serializer, validator, mapper.
   - Integration: middleware, repository, RLS, DB constraint, auth/session,
     cache, storage ou fila.
   - E2E/browser: jornada real, wiring entre frontend/backend ou regressao que
     so aparece no navegador.

3. Desenhe fixtures antes dos asserts.

   - Para isolamento, crie dois usuarios/tenants e pelo menos um recurso de cada.
   - Para auth, cubra token ausente, expirado, malformado e tenant/scope errado.
   - Para secrets/logs, injete valor marcador e prove ausencia em resposta,
     log, trace e artifact.

4. Defina Arrange, Act, Assert.

   - Arrange cria somente dados necessarios.
   - Act executa uma acao observavel.
   - Assert verifica status, payload, efeito no banco, chamada externa esperada
     ou ausencia de vazamento. Evite `truthy`, snapshots amplos e asserts que
     apenas repetem o mock.

5. Valide contra tautologia.

   - O teste deve falhar se o controle for removido.
   - Se nao for possivel rodar RED/GREEN, declare gate manual e evidencia que
     ainda falta.

## Formato de saida

```yaml
test_strategy:
  behavior: <comportamento protegido>
  level: <unit|integration|e2e|manual-gate>
  fixtures:
    - <dados/principals necessarios>
  mocks:
    - <boundary mockado e motivo>
  assertions:
    - <assert verificavel>
  negative_cases:
    - <caso que deve falhar/bloquear>
  validation:
    command: <comando repo-native ou motivo de bloqueio>
    red_green_check: <como provar que nao e tautologico>
  residual_risk:
    - <lacuna restante>
```

## Scripts

- `scripts/test_runner.py`: helper opcional para detectar e executar comando de
  teste proporcional. Use `--dry-run` quando quiser apenas descobrir o comando.
  O script nao substitui estrategia de teste e deve falhar quando o caminho alvo
  nao existir.

## Referencias

Leia apenas o arquivo relevante para o teste que precisa ser desenhado:

| Problema                                                         | Arquivo                        |
| ---------------------------------------------------------------- | ------------------------------ |
| Heuristicas de mocks, fixtures, asserts e negativos de seguranca | `references/reference.md`      |
| Exemplos de trigger e near-misses                                | `references/evals/trigger.md`  |
| Assertions de workflow                                           | `references/evals/workflow.md` |
| Exemplos compactos                                               | `references/examples.md`       |

## Exemplos

### Caso positivo

**Entrada:** Usuário quer desenhar unit/integration/security negative tests para
comportamento específico.

**Saída esperada:** escolher nível de teste, fixtures, mocks e assertions que
pegam regressão real.

### Caso negativo

**Entrada:** Usuário quer apenas rodar a suíte já definida.

**Por quê não:** isso é validação operacional; use `lint-and-validate` ou o
comando repo-native diretamente.

## Evals de trigger

Deve acionar:

- "qual teste cobre essa regressão?"
- "cria negative tests de auth"
- "essa assertion prova o bug ou e tautologica?"
- "mocko esse provider como?"
- "tenant B nao pode acessar dado do tenant A"

Não deve acionar:

- "coordena suíte inteira"
- "roda a validação de gates"
- "audita UX visual"
- "desenha o schema do banco"

## Evals de workflow

### Cenario: auth expirada

Assertions:

- [ ] escolhe integration quando middleware/session estiverem no caminho
- [ ] inclui token ausente, expirado e malformado como casos separados
- [ ] assert verifica rejeicao antes de buscar dados protegidos
- [ ] comando de validacao ou bloqueio manual fica explicito

### Cenario: tenant errado

Assertions:

- [ ] cria fixtures com dois principals e dois recursos
- [ ] teste prova que tenant B nao le ou muta dado do tenant A
- [ ] verifica resposta sanitizada e ausencia de payload protegido
- [ ] nao mocka o predicate/RLS que precisa ser provado
