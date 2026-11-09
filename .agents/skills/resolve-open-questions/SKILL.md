---
name: resolve-open-questions
description: >-
  Use para conduzir uma sabatina estruturada e retomável sobre um plano, design
  ou ideia. Ative somente com intenção clara de persistir as decisões ou de
  retomar a discussão: "me sabatina sobre esse plano", "registra as decisões"
  ou "quero poder retomar essa discussão depois". Perguntas pontuais como
  "quais perguntas você tem antes de começar?", "me explica os riscos?" e
  "quais são as opções?" não ativam o modo persistente. Não use para revisar
  código já escrito (`review-workflow`) ou executar um plano já decidido.
---

# Resolve Open Questions

Conduza uma decisão retomável: investigue o que puder provar, pergunte o que
exige escolha do usuário e registre o resultado antes de continuar. O fechamento
promete zero decisões pendentes, com incertezas e premissas explícitas.

## Limites e estados

A sabatina descobre, pergunta e registra. Ela não implementa nada do que
decidiu. O status limita a escrita:

| status                   | escrita permitida                                  |
| ------------------------ | -------------------------------------------------- |
| `em andamento`           | apenas o documento da sabatina                     |
| `aguardando confirmacao` | apenas o documento da sabatina                     |
| `fechada`                | documento, rascunhos internos declarados e handoff |

Código, specs, ADRs canônicos e documentação do sistema exigem autorização para
o workflow seguinte. Confirmar o entendimento não é autorização para executar.

Use os seis estados do template, preservando a origem de cada fechamento:

| estado       | condição                                                         |
| ------------ | ---------------------------------------------------------------- |
| `fronteira`  | respondível agora, sem dependência aberta                        |
| `bloqueada`  | depende de outra dúvida não terminal                             |
| `respondida` | decisão literal do usuário, com data                             |
| `apurada`    | resposta provada, com fato, caminho, comando ou URL de evidência |
| `assumida`   | premissa explícita, validação e gatilho de reabertura            |
| `descartada` | outra decisão terminal existente retirou a dúvida do escopo      |

Os quatro últimos estados são terminais. Nenhum pode depender de uma dúvida
aberta; `descartada-por` aponta para um `Qn` terminal existente. Não confunda
uma premissa operacional com certeza factual. Cadeias de descarte não podem
formar ciclos: precisam terminar numa resposta, apuração ou premissa completa.

## Procedimento

### 1. Classificar o pedido e conferir a autorização

O modo persistente exige intenção clara de persistir as decisões ou de retomar
a discussão. Para perguntas pontuais, investigue e responda na conversa. Não
abra uma sabatina somente porque o assunto é complexo. Uma decisão pequena
que precisa ser retomada também pode usar este workflow.

Faça um preflight read-only antes da primeira escrita:

1. Inspecione o caminho `docs/internal/sabatina/<slug>.md`, sem criar arquivo.
2. Informe a classificação como sabatina persistente e o caminho exato.
3. Obtenha confirmação explícita antes da primeira escrita. Uma autorização já
   concedida para esse documento satisfaz a condição; não a peça novamente.

Enquanto faltar autorização, não executa `sabatina --phase round`, não monta
a árvore completa e não cria documento, ADR, handoff, plano, OpenSpec ou código.
Se o usuário recusar, permaneça nas perguntas pontuais da conversa.

A autorização inicial permite apenas persistir o documento. Ela não autoriza
ADR, handoff, plano, OpenSpec, código ou implementação; as autorizações
posteriores continuam separadas.

### 2. Abrir ou retomar o registro

Use [o template](assets/sabatina-template.md). O caminho acima é uma convenção
deste workflow; o documento registra o processo de decisão, sem criar contrato
de runtime ou presumir uma política geral para `docs/internal/` no consumidor.

- Caminho novo: crie depois da autorização.
- Mesmo assunto: leia objetivo, status, placar e fronteira; informe quantas
  dúvidas continuam abertas antes de perguntar. Preserve respostas terminais.
- Outro assunto: desambigue o slug ou consolide com o usuário; não sobrescreva.
- Schema histórico: preserve o original e proponha um documento atual com
  referência explícita de supersessão. Não migre no lugar.

Enquanto o status não for `fechada`, o diff permitido continua limitado ao
documento ativo. A retomada usa esse documento como fonte do estado.

### 3. Mapear dúvidas e investigar a fronteira

Registre todas as dúvidas conhecidas, inclusive as bloqueadas, com IDs `Q1`,
`Q2`, … e `bloqueada-por` quando houver dependência. Percorra a
[checklist de cobertura](references/decision-coverage-checklist.md): cada eixo
aponta para `Qn`, `Fn` ou `nao se aplica: <razao concreta>`.

Investigue primeiro o que o repositório, os dados ou uma fonte externa podem
responder. Registre fatos com evidência e feche essas dúvidas como `apurada`.
Intenção, prioridade e trade-offs do dono viram perguntas. Investigações
independentes podem avançar sem bloquear perguntas que já são respondíveis.

### 4. Validar e perguntar

Depois de registrar uma rodada e antes de perguntar a próxima, execute:

```bash
sabatina --document docs/internal/sabatina/<slug>.md --phase round
```

Corrija erros de campos, grafo, referências, cobertura ou placar antes de seguir.
O validador confere estrutura e contabilidade; o agente responde pelo conteúdo.

Ordene a fronteira por quantas dúvidas cada resposta destrava e, no empate,
pelo ID numérico. Faça no máximo quatro decisões por turno, respeitando o
limite da superfície de interação disponível.

- Decisões fechadas: duas a quatro alternativas, recomendação primeiro e
  trade-off real em cada opção. Use escolha estruturada quando disponível,
  ou texto numerado. Registre as respostas antes de avançar.
- Perguntas abertas: envie depois das decisões fechadas, em mensagem própria,
  com recomendação explícita e justificada. Aguarde a resposta.

Exemplo: “Q7 — Por quanto tempo manter o histórico? Recomendo 30 dias para
permitir investigar falhas recentes; confirme o prazo necessário para o produto.”
Não invente uma obrigação de domínio para justificar a recomendação.

### 5. Registrar e recalcular

Grave a resposta literal antes da próxima pergunta. Separe interpretação e
resposta; se surgir contradição com decisão anterior, exponha o conflito e
reabra a dúvida em vez de escolher em silêncio.

Destrave dependências resolvidas e acrescente as dúvidas novas. Mostre em cada
rodada o mesmo placar do documento:
`respondidas / apuradas / assumidas / na fronteira / bloqueadas / descartadas`.
Uma fronteira vazia com dúvida bloqueada ainda exige investigação.

### 6. Confirmar o entendimento

Com fronteira e bloqueadas zeradas, escreva o entendimento consolidado e as
premissas com seus gatilhos. Mude para `aguardando confirmacao` e valide:

```bash
sabatina --document docs/internal/sabatina/<slug>.md --phase pre-confirmation
```

Peça a confirmação. Correções reabrem a árvore; confirmação explícita permite
marcar `fechada` e registrar a data. Rascunhos de ADR só aparecem depois disso.

### 7. Preparar o handoff e encerrar

Leia [fechamento e handoff](references/closure-and-handoff.md) neste momento:
a referência contém os critérios autossuficientes de ADR, a matriz determinística
do handoff e as regras de decomposição. Use o
[template de rascunho](assets/adr-draft-template.md) somente para decisões
estruturais que atendam aos critérios; registre por que as demais ficaram fora.

Não há rota padrão. A matriz pode recomendar execução direta, plano `.md` ou
OpenSpec. Apresente a recomendação e as alternativas, sem alterar a matriz para
acomodar uma preferência. É necessário autorizar separadamente a rota:
confirmar a sabatina não inicia plano, change ou código.

Valide o entregável e encerre com a solicitação de autorização, se ela ainda
estiver pendente:

```bash
sabatina --document docs/internal/sabatina/<slug>.md --phase closed
```

## Anti-patterns

- Perguntar o que a investigação já responde, ou embutir uma premissa ainda aberta.
- Fazer uma pergunta por turno quando decisões independentes podem ser agrupadas.
- Registrar somente no final, fechar com dependência aberta ou ocultar premissas.
- Aplicar uma correção descoberta durante a investigação sem autorização.
- Gerar ADR para escolhas locais sem impacto estrutural.

## Exemplos

### Caso positivo

**Entrada:** “quero importar arquivos; me sabatina, registra as decisões e
quero poder retomar isso depois”.

**Saída esperada:** anuncia `docs/internal/sabatina/importacao-arquivos.md`,
confere a autorização e abre o registro. Mapeia formato, identificação de
registros e política de falhas; investiga formatos já aceitos antes de perguntar.
Registra rodadas, valida, confirma o entendimento e entrega o handoff sem
iniciar implementação.

### Caso negativo

**Entrada:** “implementa a importação conforme o plano que já decidimos”.

**Por quê não:** execução já autorizada; resolva dúvidas novas pontualmente.

### Caso negativo

**Entrada:** “esse plano está completo?” ou “CSV ou JSON, o que você acha?”.

**Por quê não:** revisão ou exploração pontual, sem intenção de persistência.

## Evals de trigger

Deve acionar:

- “me sabatina sobre esse plano”
- “registra as decisões enquanto me sabatina”
- “quero registrar e fechar todas as decisões antes de implementar”
- “continua a sabatina da importação”
- “quero poder retomar essa discussão depois”

Não deve acionar:

- “quais perguntas você tem antes de começar?” — pergunta rápida; responda na
  conversa sem criar ou atualizar documento
- “me explica os riscos?” ou “quais são as opções?” — exploração pontual
- “esse plano está completo?” — revisão
- “escreve o plano de implementação” — plano direto
- “implementa conforme o plano que já decidimos” — execução
- “cria a proposal OpenSpec dessa change” — workflow próprio
- “revisa esse código” ou “cria um ADR da decisão tomada” — outro entregável

Os cenários de comportamento e os limites da evidência estão em
[references/EVALS.md](references/EVALS.md). Testes do validador não comprovam
que um agente segue o procedimento; essa conclusão exige transcrições avaliadas.
