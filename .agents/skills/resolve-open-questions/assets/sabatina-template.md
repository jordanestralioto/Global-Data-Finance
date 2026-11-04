# Sabatina: <assunto>

> Status: em andamento | aguardando confirmacao | fechada
> Iniciada: AAAA-MM-DD
> Ultima rodada: AAAA-MM-DD
> Confirmada em: — | AAAA-MM-DD
> Knowledge class: nao-canonico (processo de decisao)

O status controla o que pode ser escrito. Enquanto ele nao for `fechada`, este
arquivo e a unica escrita permitida. Depois de `fechada`, liberam-se os
rascunhos de ADR da secao 7 e o handoff da secao 8 — nunca codigo, specs, ADRs
do catalogo ou documentacao do sistema.

## 1. Objetivo

Uma frase: o que precisa ficar decidido para o trabalho poder comecar.

Esta secao tambem e a procedencia do documento. Antes de escrever num caminho
que ja existe, compare o objetivo: igual, retome; diferente, consolide de forma
explicita com o operador ou use um slug desambiguado. Sobrescrever em silencio
nao e uma opcao.

## 2. Placar

| respondidas | apuradas | assumidas | na fronteira | bloqueadas | descartadas |
| ----------- | -------- | --------- | ------------ | ---------- | ----------- |
| 0           | 0        | 0         | 0            | 0          | 0           |

A soma das seis colunas e o total de duvidas registradas na secao 5.

## 3. Cobertura

Eixos de `references/decision-coverage-checklist.md`. Cada linha referencia um
`Qn` ou `Fn` existente, ou declara `nao se aplica: <razao concreta>`. "Coberto"
sem uma dessas trilhas nao e evidencia de cobertura.

| eixo   | resultado                           |
| ------ | ----------------------------------- |
| escopo | \<Qn, Fn ou "nao se aplica: razao"> |

## 4. Fatos apurados

Respostas obtidas por investigacao, nunca perguntadas ao operador. Cada uma com
a evidencia que a sustenta. Uma duvida fechada por um destes fatos entra na
secao 5 como `apurada`, citando o `Fn`.

| #   | Fato                  | Evidencia        |
| --- | --------------------- | ---------------- |
| F1  | <o que ficou provado> | `arquivo.py:120` |

## 5. Duvidas

Estados terminais: `respondida`, `apurada`, `assumida`, `descartada`.
Nao terminais: `fronteira`, `bloqueada`.

Estado terminal nao pode depender, em `bloqueada-por`, de `fronteira` ou
`bloqueada`. `descartada-por` aponta somente para um `Qn` terminal existente.

### Q1 — <titulo curto>

- **estado**: fronteira | bloqueada | respondida | apurada | assumida | descartada
- **bloqueada-por**: — | Qn, Qm
- **pergunta**: <o que precisa ser decidido>
- **recomendacao**: <posicao com justificativa>
- **resposta** (AAAA-MM-DD): \<o que o operador respondeu, literal>
- **leitura**: \<sua interpretacao, quando houver ambiguidade>
- **evidencia** (se apurada): F1 | `arquivo.py:120` | comando | URL
- **premissa** (se assumida): <premissa adotada> | valida com: <o que
  confirmaria> | reabre quando: <gatilho>
- **descartada-por** (se descartada): Qn terminal que tirou esta duvida do escopo
- **gera**: Qn, Qm (duvidas novas criadas por esta resposta)

### Q2 — <titulo curto>

...

## 6. Entendimento consolidado

Preenchido quando fronteira e bloqueadas zerarem, antes de pedir a confirmacao.
Confirmado pelo operador em AAAA-MM-DD.

Premissas que entram no trabalho sem decisao explicita do dono (estado
`assumida`), cada uma com o gatilho que a reabre:

- Q4: <premissa> — reabre quando <gatilho>

## 7. Rascunhos de ADR gerados

Preenchido somente depois do status virar `fechada`.

Cada linha usa somente `adr-draft/adr-draft-<slug-da-decisao>.md` (ou o caminho
completo equivalente sob `docs/internal/sabatina/adr-draft/`). Nao use alias,
caminho de ADR canonico ou numero `NNNN` antes da promocao pelo catalogo.

| rascunho                                   | decisoes que o sustentam | criterio do §2 atendido        |
| ------------------------------------------ | ------------------------ | ------------------------------ |
| `adr-draft/adr-draft-<slug-da-decisao>.md` | Q3, Q7                   | contrato entre multiplas fases |

Decisoes fechadas que **nao** viraram ADR e o motivo:

- Q5: escolha local, sem impacto estrutural

## 8. Handoff

Preenchido somente depois do status virar `fechada`. Ele existe para o proximo
workflow executar sem reinterpretar as decisoes — e nao autoriza ninguem a
comecar: a autorizacao e uma pergunta separada ao operador.

### Objetivo

<o que a execucao precisa entregar>

### Decisoes e alternativas

\<decisao adotada e a alternativa rejeitada, com a razao real do operador>

### Fatos com evidencia

\<Fn relevantes da secao 4>

### Premissas e gatilhos

\<toda duvida `assumida`, com o gatilho que a reabre; "nenhuma" quando for o caso>

### Invariantes

<o que a execucao nao pode violar>

### Criterios de aceite

<como se prova que a execucao terminou>

### Artefatos

<links dos arquivos de entrada e dos rascunhos gerados>

### Proximo workflow proposto

Rota recomendada: a que a matriz abaixo calcular, sem padrao previo. As outras
duas rotas — plano `.md` e execucao direta — sao oferecidas na mesma pergunta.
Nenhuma delas comeca sem autorizacao explicita.

#### Matriz deterministica de rota

| criterio               | valor                                 | evidencia                               |
| ---------------------- | ------------------------------------- | --------------------------------------- |
| contrato duradouro     | <sim ou nao>                          | \<fato, Qn ou razao>                    |
| multiplos consumidores | <sim ou nao>                          | \<fato, Qn ou razao>                    |
| dado persistido novo   | <sim ou nao>                          | \<fato, Qn ou razao>                    |
| rollout supervisionado | <sim ou nao>                          | \<fato, Qn ou razao>                    |
| rollback proprio       | <sim ou nao>                          | \<fato, Qn ou razao>                    |
| lifecycle auditavel    | <sim ou nao>                          | \<fato, Qn ou razao>                    |
| varios passos          | <sim ou nao>                          | \<fato, Qn ou razao>                    |
| rota recomendada       | \<execucao direta, plano ou openspec> | <resultado do classificador>            |
| autorizacao explicita  | pendente                              | <autorizacao separada ainda necessaria> |

Se qualquer um dos seis primeiros criterios for `sim`, a rota recomendada e
`openspec`. Se todos forem `nao` e `varios passos` for `sim`, a rota e `plano`;
caso contrario, e `execucao direta`. A linha de autorizacao permanece
separada: `pendente` significa que a rota foi apenas recomendada.

#### Decomposicao em unidades

Use zero linhas quando nenhum trabalho formal for necessario. Nunca crie uma
linha guarda-chuva sem IDs, implementacao ou aceite proprio.

| change     | IDs possuidos | objetivo                 | aceite          | rollout            | rollback           | depende de |
| ---------- | ------------- | ------------------------ | --------------- | ------------------ | ------------------ | ---------- |
| `<change>` | Qn, Qm        | <resultado independente> | <prova propria> | <ordem e condicao> | <reversao propria> | nenhuma    |

- **aceite agregado**: <condicao que fecha todas as unidades e respeita o DAG>

\<caminho proposto e comando sugerido, mais a alternativa que o operador
escolheu, se ele ja tiver escolhido>
