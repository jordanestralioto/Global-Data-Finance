---
name: resolve-open-questions
description: >-
  Use para conduzir uma sabatina persistente: uma interrogação estruturada em
  rodadas que leva um plano, design ou ideia a zero decisões pendentes, com
  registro retomável. Ative somente quando o usuário deixar claro a intenção de
  persistir as decisões ou retomar a discussão, por exemplo: "me sabatina sobre
  isso", "registra as decisões", "quero fechar todas as decisões antes de
  implementar", "continua a sabatina de ontem" ou "quero poder retomar essa
  discussão depois". Perguntas rápidas como "quais perguntas você tem antes de
  começar?", "me explica os riscos?", "quais são as opções?" e "esse plano está
  completo?" ou execução de um plano já
  decidido não ativam o modo persistente. Não use para exploração de alternativas
  sem direção fechada, revisar código já escrito (`review-workflow`) ou quando o
  usuário já decidiu e pediu implementação.
---

# Resolve Open Questions

## Por que interrogatórios falham

Três modos de falha, em ordem de frequência:

**Parar por cansaço.** O agente decide sozinho que "já entendeu o bastante" e
começa a executar sobre premissas nunca confirmadas. O critério de parada aqui
não é subjetivo: ou existe decisão pendente, ou não existe.

**Perguntar fora de ordem.** Perguntar "qual formato de saída?" antes de saber
se haverá saída persistida força o usuário a responder em cima de hipótese. A
resposta dada sobre premissa errada é pior que a pergunta não feita, porque
parece resolvida.

**Perguntar o que o repositório responde.** Cada pergunta cuja resposta está no
código, nos specs ou no git gasta a atenção do usuário sem entregar informação.
Investigue primeiro; traga como fato declarado, não como pergunta.

## O que esta skill decide e o que ela não toca

A sabatina descobre, pergunta e registra. Ela não implementa nada do que
decidiu — nem o ajuste "óbvio", nem a correção de uma linha que apareceu no meio
da investigação. Uma correção aplicada no meio do interrogatório vira
autorização implícita para executar antes de o grafo de decisões fechar, e é
disso que o usuário abriu mão ao pedir a sabatina.

O documento tem três status, e cada um define o que pode ser escrito:

| status                   | significado                                   | escrita permitida                                |
| ------------------------ | --------------------------------------------- | ------------------------------------------------ |
| `em andamento`           | ainda há dúvida em `fronteira` ou `bloqueada` | apenas o documento da sabatina                   |
| `aguardando confirmacao` | grafo fechado, usuário ainda não confirmou    | apenas o documento da sabatina                   |
| `fechada`                | usuário confirmou o entendimento, com data    | documento, rascunhos de ADR internos e o handoff |

Em nenhum status esta skill ganha autoridade sobre código, specs, ADRs do
catálogo canônico ou documentação do sistema. Isso é trabalho do workflow
seguinte, e ele começa só depois de uma autorização explícita (passo 11).
O schema operacional é somente o schema atual desta skill: documentos antigos
não são migrados em lugar nem recebem um modo de compatibilidade permanente.
Quando uma sabatina histórica precisar voltar ao fluxo, abra um documento novo
e preserve a procedência antiga como referência explicitamente supersedida.

## Estados e fronteira

**Fronteira** é o conjunto de dúvidas cujos pré-requisitos já estão resolvidos —
respondíveis *agora*, sem supor nada. Uma dúvida sai da fronteira e vira
bloqueada quando sua resposta depende de outra ainda aberta.

Seis estados, quatro deles terminais:

- **respondida** (terminal) — o usuário decidiu. Registre a resposta literal.
- **apurada** (terminal) — a resposta foi provada por investigação, sem decisão
  do usuário. Exige evidência: id de fato, `arquivo:linha`, comando ou URL.
- **assumida** (terminal) — ele não tem como decidir agora (falta medição,
  terceiro, um run futuro). Registre a premissa adotada, o que a validaria e o
  gatilho que a reabre. Premissa não registrada não fecha a dúvida.
- **descartada** (terminal) — a dúvida saiu de escopo por uma decisão anterior.
  Registre qual `Qn` terminal a matou.
- **fronteira** — respondível agora.
- **bloqueada** — depende de outra não terminal; volta à fronteira quando a
  outra fechar.

`apurada` e `descartada` existem separadas de propósito: uma diz que a evidência
resolveu, a outra que o escopo mudou. Colapsar as duas apaga de onde veio a
autoridade da resposta.

Um estado terminal não pode conservar `bloqueada-por` para uma dúvida em
`fronteira` ou `bloqueada`: isso é uma decisão aparentemente fechada que ainda
depende de informação aberta. A referência de `descartada-por` também precisa
apontar para uma decisão terminal existente, nunca para uma dúvida ainda aberta.

`assumida` existe para o interrogatório não travar em pergunta que o dono
genuinamente não pode responder hoje. O que não pode é a premissa entrar em
silêncio: sabatina fechada com premissas explícitas é utilizável, com premissas
ocultas é pior que não ter feito nenhuma.

O ciclo é: perguntar a fronteira inteira → registrar → recalcular quais dúvidas
foram destravadas → nova fronteira. Respostas costumam **criar** dúvidas novas;
isso é progresso, não regressão. A árvore cresce antes de fechar.

A promessa de encerramento é **zero decisões pendentes, com incerteza e
premissas explícitas** — não "zero dúvidas". Uma premissa assumida fecha a
decisão operacional sem eliminar a incerteza factual, e fingir o contrário é o
que faz a sabatina parecer mais conclusiva do que é.

## Procedimento

### 1. Confirmar que o pedido é uma sabatina

O interrogatório persistente custa várias rodadas do usuário. O modo formal só
começa quando o pedido contém uma intenção clara de persistir as decisões ou de
retomar a discussão. Reconhecer que o usuário quer fazer muitas perguntas,
fechar um plano ou evitar implementação ainda não substitui essa intenção de
persistência. Se ela não estiver presente, responda na conversa, investigue os
riscos ou encaminhe para a skill adequada, e ofereça a sabatina sem iniciá-la.

### 2. Abrir ou retomar o documento

O documento vive em `docs/internal/sabatina/<slug>.md`, onde `<slug>` descreve o
assunto em kebab-case. Use o template em
[`assets/sabatina-template.md`](assets/sabatina-template.md).

`docs/internal/` é explicitamente não-canônico (`AGENTS.md`): esse documento
registra o processo de decisão, nunca vira contrato de runtime.

Antes de qualquer escrita persistente, faça somente o preflight read-only abaixo:

1. Inspecione o caminho candidato apenas para leitura e resolva o slug sem criar
   ou atualizar arquivo.
2. Informe ao usuário que o pedido foi classificado como sabatina persistente.
3. Mostre o caminho exato que será criado ou atualizado:
   `docs/internal/sabatina/<slug>.md`.
4. Peça confirmação explícita antes da primeira escrita.

Enquanto não houver confirmação, não crie nem atualize o documento, não execute
`sabatina --phase round`, não monte a árvore completa de cobertura e não crie
ADRs, handoff, plano, OpenSpec ou código. Se o usuário recusar, faça somente
perguntas pontuais na conversa e deixe todos esses caminhos sem alteração.

A confirmação inicial autoriza apenas a persistência do documento da sabatina.
Ela não autoriza ADR, handoff, plano, OpenSpec, código ou implementação; as
permissões posteriores continuam separadas, como nos passos 9 a 12.

Depois da confirmação, inspecione o caminho candidato:

- **não existe** → crie.
- **existe e trata do mesmo assunto** → retome dele, e diga ao usuário quantas
  dúvidas continuam abertas antes de perguntar qualquer coisa.
- **existe e trata de outro assunto** → não sobrescreva. Consolide de forma
  explícita com o usuário ou use um slug desambiguado.

Documentos escritos antes deste contrato não são migrados nem validados no
lugar. Se o usuário pedir para retomar um deles, preserve o original e pergunte
se ele quer um documento novo, no formato atual, apontando para o antigo.

Retomadas entre sessões seguem o documento ativo como única fonte de estado:
leia o objetivo, status, placar e fronteira antes de perguntar; não repita uma
resposta terminal e não sobrescreva um objetivo diferente. Enquanto o status
for `em andamento` ou `aguardando confirmacao`, o diff permitido continua
limitado a esse documento.

### 3. Mapear a árvore inicial com cobertura

Antes da primeira pergunta, escreva no documento **todas** as dúvidas que você
enxerga, incluindo as bloqueadas. Cada uma recebe id (`Q1`, `Q2`, …), estado e o
campo `bloqueada-por` quando depender de outra.

Antes de declarar a árvore mapeada, percorra
[`references/decision-coverage-checklist.md`](references/decision-coverage-checklist.md)
e registre, por eixo, a dúvida ou o fato que ele gerou — ou por que ele não se
aplica. Cada resultado é `Qn`, `Fn` ou `nao se aplica: <razao concreta>`;
"coberto" sem referência não é evidência de cobertura.

Mapear tudo de saída evita a sensação de interrogatório sem fim: o usuário vê o
tamanho da árvore e o quanto cada rodada avança.

### 4. Investigar antes de perguntar

Para cada dúvida da fronteira, decida: **verificável** ou **decisão do usuário**?

- Verificável no repo, nos dados ou na web → investigue, registre como fato com
  a evidência (`arquivo:linha`, comando, URL) e feche a dúvida como `apurada`.
  Nunca vira pergunta.
- Depende de intenção, prioridade, gosto ou trade-off que só o dono resolve →
  vira pergunta.

Investigações independentes podem rodar em paralelo; não segure a rodada
esperando uma checagem que não bloqueia as outras perguntas.

### 5. Validar o documento antes de cada rodada

```bash
sabatina \
  --document docs/internal/sabatina/<slug>.md --phase round
```

O script confere ids, campos obrigatórios por estado, referências de
`bloqueada-por` e `descartada-por`, coerência entre estados terminais e grafo,
ciclos, evidência dos fatos, cobertura rastreável, ciclo de vida dos rascunhos e
a aritmética do placar. O julgamento continua seu; a contabilidade e o grafo
não. Rode-o depois de
registrar as respostas da rodada anterior e antes de formular a próxima
pergunta — um placar errado destrói a leitura de convergência que faz o usuário
continuar respondendo.

### 6. Perguntar a fronteira

Uma rodada cobre a fronteira em duas partes **sequenciais**, nunca na mesma
mensagem: uma interação estruturada devolve o turno assim que o usuário escolhe,
então pergunta em texto emitida junto com ela fica sem canal de resposta — e
seguir sem essa resposta é o modo de falha nº 1 desta skill.

**Parte A — decisões fechadas** (existem alternativas enumeráveis). Se o harness
oferecer uma capacidade de escolha estruturada com opções enumeradas, use-a;
quando ela não existir, não couber as alternativas ou não comportar a fronteira
da rodada, use texto numerado com as mesmas opções. Ordene a fronteira por
quantas dúvidas bloqueadas cada decisão destrava e, no empate, pelo id numérico.
Pergunte no máximo quatro decisões por turno do usuário — ou menos, se a
capacidade disponível comportar menos — e deixe o resto para a rodada seguinte.
Cada decisão traz de duas a quatro alternativas, a recomendada primeiro e
marcada como tal, com o trade-off real em cada uma. Decisão sem pelo menos duas
alternativas nomeáveis não é fechada: trate como aberta.

**Parte B — perguntas abertas** (a resposta é um valor, um nome, uma quantidade,
uma narrativa) vão em texto numerado, **depois** que a parte A voltou e foi
registrada, cada uma com a sua recomendação explícita. Elas encerram a mensagem:
a resposta chega no turno seguinte do usuário. Exemplo:

```text
❓ **Q7 — Retenção do histórico**: por quanto tempo os deltas ficam consultáveis?
➡️ Recomendo 5 anos: cobre o ciclo de restatement da CVM sem estourar o disco.
```

A recomendação existe para o usuário poder concordar em vez de redigir. Ela
precisa ser uma posição real e justificada — "depende do seu caso" não é
recomendação.

Nenhum nome de ferramenta, produto ou harness entra nesse protocolo. O que muda
entre ambientes é a superfície; a semântica — opções enumeradas, recomendação
explícita, resposta registrada antes da próxima pergunta — é a mesma nos dois
caminhos.

### 7. Registrar antes da rodada seguinte

Grave cada resposta no documento **antes** de fazer a próxima pergunta. Sessão
interrompida no meio é o caso normal, não a exceção; o documento é o que permite
retomar sem repetir perguntas já respondidas.

Registre a resposta como o usuário deu, e separadamente a sua leitura dela
quando houver interpretação envolvida. Se ele contradisser algo já decidido, não
escolha em silêncio: aponte o conflito e reabra a dúvida anterior.

### 8. Recalcular e repetir

Marque como destravadas as dúvidas cujo `bloqueada-por` foi resolvido, acrescente
as dúvidas novas que a resposta criou, e monte a próxima rodada. Informe o placar
a cada rodada nos mesmos seis campos do template — `respondidas / apuradas / assumidas / na fronteira / bloqueadas / descartadas` — e mantenha a mensagem e a
tabela §2 do documento com os mesmos números.

### 9. Fechar com confirmação explícita

Com fronteira e bloqueadas zeradas, escreva o entendimento consolidado, mude o
status para `aguardando confirmacao` e rode:

```bash
sabatina \
  --document docs/internal/sabatina/<slug>.md --phase pre-confirmation
```

Só então peça a confirmação. Se o usuário corrigir qualquer ponto, isso reabre a
árvore: volte ao passo 6. Quando ele confirmar, mude o status para `fechada` e
registre a data da confirmação.

### 10. Emitir os rascunhos de ADR

Depois de `fechada`, classifique cada decisão contra `docs/adr/README.md` §2.
Qualificam-se apenas as que afetam arquitetura de dados ou camadas, contratos
entre múltiplas fases, estratégia de processamento/persistência, mecanismo de
governança ou dependência estrutural entre subsistemas.

As que qualificam viram **rascunhos sem número**, em
`docs/internal/sabatina/adr-draft/adr-draft-<slug-da-decisão>.md`, a partir de
[`assets/adr-draft-template.md`](assets/adr-draft-template.md). O slug é o do
tópico da decisão, no padrão `topic-slug` do catálogo, não o da sabatina: uma
sabatina costuma gerar mais de um rascunho, e reaproveitar o slug dela faz os
arquivos colidirem. Números `NNNN` do catálogo são permanentes e não
reaproveitáveis (`docs/adr/README.md` §4) — a numeração só acontece quando o
usuário promover o rascunho.

Na tabela de rascunhos, use somente
`adr-draft/adr-draft-<slug-da-decisao>.md` (ou o mesmo caminho completo sob
`docs/internal/sabatina/`). Um alias, um caminho de ADR canônico ou qualquer
nome contendo número `NNNN` não é um rascunho válido e bloqueia o fechamento.

A regra de procedência do passo 2 vale aqui: rascunho existente com a mesma
procedência é retomado, com procedência diferente exige slug desambiguado, e
nenhum é sobrescrito em silêncio.

Cada rascunho declara quais `Qn` da sabatina o sustentam. Alternativas
descartadas durante o interrogatório são material pronto para "Alternativas
consideradas" — use as razões reais que o usuário deu. As decisões que não
qualificam ficam registradas apenas no documento, e o fechamento diz quais
ficaram de fora e por quê.

### 11. Entregar o handoff e parar

Anexe ao documento o handoff com objetivo, decisões e alternativas rejeitadas,
fatos com evidência, premissas com seus gatilhos, invariantes, critérios de
aceite e links dos artefatos. Valide:

```bash
sabatina \
  --document docs/internal/sabatina/<slug>.md --phase closed
```

Proponha a rota que a matriz determinística do handoff calcular (procedimento
12\) e **pergunte se o usuário autoriza começá-la**. Não há rota padrão:
`openspec-workflow` só é recomendado quando algum critério da matriz for `sim`,
porque é ele que sustenta contrato duradouro, rollout supervisionado e rollback
próprio; a menor rota que preserva o contrato é sempre a recomendada.

Ofereça na mesma pergunta as duas outras rotas — um plano `.md` (escrito
diretamente, se o usuário preferir) e a execução direta —
dizendo qual delas a matriz calculou e por quê. Uma sabatina fechada é
entregável pelos três caminhos e a escolha final é do usuário: se ele preferir
rota diferente da calculada, registre a preferência como decisão explícita, sem
recalcular a matriz para justificá-la.

Confirmar o entendimento não é autorização para escrever mais nada: a sabatina
termina aqui, com o handoff pronto e nenhum arquivo do sistema tocado.

### 12. Recalcular a rota e decompor o trabalho

Depois do fechamento, calcule a rota a partir da matriz persistida no handoff;
nunca escolha por preferência ou por quantidade de arquivos. Se qualquer um dos
critérios `contrato duradouro`, `multiplos consumidores`, `dado persistido novo`, `rollout supervisionado`, `rollback proprio` ou `lifecycle auditavel`
for `sim`, recomende `openspec`. Se todos forem `nao` e `varios passos` for
`sim`, recomende um plano `.md`; se todos forem `nao`, recomende execução
direta. Um critério ausente é uma lacuna que deve ser reportada, não uma
permissão para inferir.

A recomendação sempre registra `autorizacao explicita: pendente` até o operador
autorizar separadamente a rota. Confirmar a sabatina não inicia plano, change
ou código.

Quando a rota for OpenSpec, particione por unidade semântica de resultado,
contrato, owner, aceite, rollout e rollback. Um número de arquivos, requisitos
ou tasks é apenas sinal de revisão e nunca um limiar de divisão. Uma fonte pode
gerar zero, uma ou várias changes; cada unidade precisa de IDs exclusivos,
objetivo, aceite, rollout, rollback e dependências no DAG. Não crie uma change
guarda-chuva sem implementação e aceite próprios. O handoff mantém o aceite
agregado e a ordem de retomada entre as unidades. Uma rota OpenSpec so fecha
quando a tabela existe e cada Qn terminal pertence exatamente a uma unidade;
rotas direta e de plano podem legitimamente ter zero unidades formais.

## Anti-patterns

**Rodada de uma pergunta só.** Se três dúvidas da fronteira são independentes,
perguntar uma por mensagem triplica o número de idas e voltas sem ganhar nada.

**Pergunta com premissa embutida.** "Qual banco você quer usar?" já decidiu que
haverá banco. Se a premissa não foi confirmada, ela é a pergunta anterior.

**Recomendação covarde.** `➡️ Depende do que você preferir` devolve o trabalho
ao usuário. Se você genuinamente não tem base para recomendar, o que falta é uma
investigação do passo 4.

**Documento escrito só no final.** Perde-se tudo em qualquer interrupção, e o
usuário não consegue ver o progresso enquanto responde.

**Fechar com bloqueada em pé.** Fronteira vazia com dúvida bloqueada significa
grafo inconsistente ou dependência que ninguém resolveu — não sabatina pronta.

**Corrigir "só isso" no meio.** O patch de uma linha aplicado durante o
interrogatório é a porta pela qual a execução começa sem autorização.

**ADR para tudo.** Emitir rascunho de ADR para cada resposta transforma o
catálogo em log de conversa e destrói o valor de sinal dele.

## Exemplos

### Caso positivo

**Entrada:** "quero adicionar cache de leitura no refinement; me sabatina,
registra as decisões e quero poder retomar isso depois"

**Saída esperada:** anuncia que classificou o pedido como sabatina persistente,
mostra `docs/internal/sabatina/cache-leitura-refinement.md` e pede aprovação
antes de criar o documento. Depois da aprovação, cria o documento com a árvore
inicial (Q1 invalidação, Q2 chave, Q3 limite de memória bloqueada por Q2, Q4
persistência entre runs…) depois de percorrer a checklist de cobertura; investiga
sozinho o que o código já responde (onde as leituras acontecem hoje, tamanho
real dos frames) e fecha essas como `apurada` com evidência; valida o documento,
abre a rodada 1 com as decisões fechadas e depois as abertas; itera até
fronteira e bloqueadas zerarem; pede confirmação; só então emite o rascunho de
ADR da decisão de invalidação, que é contrato entre fases, monta o handoff e
pergunta se pode começar a implementação.

### Caso negativo

**Entrada:** "implementa o cache de leitura no refinement conforme o plano que
te passei"

**Por quê não:** o usuário já decidiu e pediu execução. Interrogar aqui atrasa
trabalho aprovado. Se durante a implementação aparecer uma dúvida genuína, ela
se resolve pontualmente — não por uma sabatina completa.

### Caso negativo

**Entrada:** "estou em dúvida entre cache em memória e materializar em parquet,
o que você acha?"

**Por quê não:** o usuário quer explorar alternativas, não fechar uma árvore de
decisão sobre uma direção já escolhida. Trate como ideação aberta.

### Caso negativo

**Entrada:** "esse plano está completo?"

**Por quê não:** completude é uma pergunta de revisão, e a resposta cabe em uma
mensagem. Responda o que falta e ofereça a sabatina; iniciar um interrogatório
persistente sem o usuário ter pedido gasta rodadas que ele não autorizou.

## Evals de trigger

Deve acionar:

- "me sabatina sobre esse plano"
- "registra as decisões enquanto me sabatina"
- "quero fechar todas as decisões antes de implementar"
- "continua a sabatina da segregação"
- "quero poder retomar essa discussão depois"

Não deve acionar:

- "quais perguntas você tem antes de começar?" — pergunta rápida; responda na
  conversa sem criar ou atualizar documento
- "me explica os riscos" — investigação pontual, sem persistência pedida
- "quais são as opções?" — exploração sem direção fechada
- "esse plano está completo?" — pergunta de revisão, sem pedido de
  interrogatório (`review-workflow`)
- "escreve o plano de implementação" — plano direto, sem interrogatório
- "implementa conforme o plano que já decidimos" — execução de decisão existente
- "cria a proposal OpenSpec dessa change" — workflow próprio
  (`openspec-workflow`)
- "revisa esse código e me diz o que está errado" — código já escrito
  (`review-workflow`)
- "cria um ADR sobre a decisão que a gente tomou" — ADR isolado, sem
  interrogatório

Os cenários de aceite comportamental e os critérios de cada um estão em
[`references/EVALS.md`](references/EVALS.md).
