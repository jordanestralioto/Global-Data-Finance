# ADR-DRAFT: <titulo da decisao>

> Owner: <responsavel>
> Last reviewed: AAAA-MM-DD
> Status: draft
> Knowledge class: Decisions (rascunho nao promovido)

> Arquivo: `adr-draft-<slug-da-decisao>.md`, onde o slug e o topico da decisao
> no padrao `topic-slug` do catalogo — uma sabatina pode gerar varios rascunhos.
> `draft` nao pertence ao modelo de status de `docs/adr/README.md` §3: vale
> apenas enquanto o arquivo estiver fora do catalogo.

> Rascunho gerado pela sabatina `docs/internal/sabatina/<slug-da-sabatina>.md`,
> emitido apenas depois de ela atingir o status `fechada`. Sem numero `NNNN` por
> decisao explicita: a numeracao do catalogo e permanente e nao reaproveitavel
> (`docs/adr/README.md` §4), entao so e atribuida quando o operador promover
> este rascunho para `docs/adr/`.

## 0. Procedencia

- **sabatina**: `docs/internal/sabatina/<slug-da-sabatina>.md`
- **duvidas que sustentam esta decisao**: Q3, Q7
- **criterio do §2 atendido**: \<qual dos criterios de `docs/adr/README.md` §2>
- **premissas assumidas que a decisao carrega**: Q4 (<gatilho que reabre>) | —

Antes de escrever num caminho que ja existe, compare esta secao com a do arquivo
presente: mesma sabatina e mesmas duvidas permitem retomar; procedencia
diferente exige slug desambiguado. Sobrescrever em silencio nao e uma opcao.

## 1. Contexto

Descreva o problema, o momento arquitetural e o escopo impactado.

## 2. Drivers da decisao

- driver 1
- driver 2

## 3. Decisao

Descreva objetivamente a decisao adotada.

## 4. Alternativas consideradas

Use as alternativas realmente descartadas durante a sabatina e a razao que o
operador deu para descarta-las.

### Alternativa A

- pro:
- contra:

### Alternativa B

- pro:
- contra:

## 5. Consequencias

### Beneficios

- beneficio 1

### Custos e trade-offs

- trade-off 1

## 6. Guardrails de implementacao

- guardrail 1

## 7. Migracao, rollback e irreversibilidades

- como migrar sem big bang:
- como fazer rollback:
- o que e caro ou impossivel desfazer:

## 8. Gatilhos de revisao

- gatilho 1

## 9. Referencias relacionadas

- documento 1

## 10. Promocao

Ao promover: atribuir o proximo `NNNN` livre, remover as secoes 0 e 10, mudar
`Status` para `proposed` e registrar no `docs/adr/README.md`.
