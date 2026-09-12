---
name: openspec-workflow
description: >-
  Use para executar workflows OpenSpec/OPSX explicitamente pedidos e para
  classificar se uma mudança precisa de artefatos formais. Ative com "cria uma change", "faz proposal/design/tasks",
  "valida spec", "sincroniza specs", ou quando o usuário pede para decidir se
  OpenSpec é necessário. Uma mera menção a OpenSpec/OPSX aciona somente a
  triagem: não crie uma change sem comando explícito ou uma fronteira formal
  comprovada. Sem pedido explícito, selecione OpenSpec apenas para contrato
  compartilhado duradouro, múltiplos consumidores ou owners independentes,
  rollout, rollback ou lifecycle auditável. Não use para planos simples,
  bugs isolados, ajustes rápidos, revisões de skills sem contrato compartilhado
  ou refatorações delimitadas sem rastreabilidade formal.
---

# OpenSpec Workflow

## Contrato

- Os comandos e prompts do lifecycle OPSX são a fonte canônica do fluxo. Esta skill existe para roteamento e guardrails, não para duplicar o workflow inteiro.
- O formato ativo padrão de uma change é `openspec/changes/<name>/` com `proposal.md`, `specs/<capability>/spec.md`, `design.md`, `tasks.md` e, quando existir, `.openspec.yaml`.
- Arquivos soltos como `openspec/changes/*.md` devem ser tratados como artefatos legados ou especiais deste repositório, não como o modelo principal do workflow ativo.
- Para validação estrutural de specs do consumidor, use sempre `opsx validate --specs --strict`.
- Quando o schema, o próximo artefato ou a ordem de execução não estiverem óbvios, consulte `opsx status --change "<name>" --json` e `opsx instructions <artifact-or-action> --change "<name>" --json` antes de orientar o usuário.
- O bundle e lifecycle são validados com `opsx-handoff`, apenas quando a change estiver no estágio aplicável.
- O workflow é executado pelos CLIs instalados pela distribuição da central (`opsx`, `opsx-handoff`, `opsx-sync`). Nada aqui exige o pacote npm `openspec` instalado.

## Decisão de rota

Ativação para triagem não autoriza adoção do lifecycle. A skill pode ser lida
porque um pedido menciona OpenSpec ou OPSX, mas essa leitura não cria
`openspec/changes/<name>/`, uma fonte de decisão, nem qualquer artefato formal.
Antes de escrever, escolha e anuncie a menor rota que preserva o contrato:

| Evidência observável                                                                                                                                                          | Rota                                         | Limite de escrita                            |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------- | -------------------------------------------- |
| Um ajuste local, entendido e reversível, sem contrato duradouro                                                                                                               | Execução direta                              | Não cria plano formal apenas por organização |
| Passos ordenados que terminam nesta sessão, sem handoff persistente                                                                                                           | Plan Mode                                    | Não cria arquivo no repositório              |
| Passos ordenados que precisam sobreviver a outra sessão, sem contrato formal                                                                                                  | Um plano Markdown pertencente ao repositório | Não cria `openspec/changes/<name>/`          |
| Comando `/opsx:*`, pedido explícito de lifecycle, contrato compartilhado duradouro, múltiplos consumidores ou owners independentes, rollout, rollback, ou evidência auditável | OpenSpec                                     | Usa o workflow canônico correspondente       |

Contagem de arquivos, tasks, linhas, ou a impressão de que o trabalho parece
grande não prova uma fronteira formal. Se a evidência não satisfizer uma rota,
declare o campo faltante em vez de escolher OpenSpec por preferência.

A classificação da rota não é aprovação para escrever. Depois de selecionar
OpenSpec, anuncie a rota, a change (quando já existir) e a primeira operação
que escreverá; então aguarde uma aprovação explícita do usuário. Essa barreira
também vale quando o usuário enviou `/opsx:*`: o comando preserva a rota e seus
guardrails, mas não autoriza silenciosamente a primeira escrita formal. Até a
aprovação, limite-se a consultas read-only e não execute `opsx new`, `opsx ff`,
`opsx continue` ou qualquer operação que crie `openspec/changes/<name>/`, fonte
de decisão, proposal, spec, design ou tasks. A aprovação da criação não
substitui as autorizações próprias de `apply`, `sync` ou `archive`.

## Audiência dos artefatos

Quem implementa uma change deste repositório é um desenvolvedor júnior que
tem `AGENTS.md` e os documentos linkados a partir dele — e mais nada. Sem
contato prévio com o código e sem conhecimento do domínio no negócio. Ele
não infere intenção, não distingue restrição deliberada de acidente
histórico e não questiona instrução ambígua — ele chuta, e o chute sai
errado.

Isso muda o critério de "artefato pronto": o documento está pronto quando
esse leitor executa a change de ponta a ponta sem fazer uma única pergunta.
Não quando está tecnicamente correto para quem já conhece o sistema.

Como ele já lê `AGENTS.md`, o artefato não reescreve stack, comandos, fases
da pipeline, regras obrigatórias nem rotas de documentação. Repetir cria uma
segunda fonte que envelhece sozinha e passa a contradizer a primeira. O
artefato carrega o que `AGENTS.md` não tem: o problema desta change, o
vocabulário do domínio, as decisões com alternativas rejeitadas, o recorte
do que não tocar e os passos com âncora.

Consequências operacionais em toda rota que escreve artefato (`new`,
`continue`, `ff`):

- O padrão de autoria completo está em `references/HANDOFF_STANDARD.md`. Abra
  antes de escrever `proposal.md`, `spec.md`, `design.md` ou `tasks.md`.
- `openspec/config.yaml` já injeta esse contrato nos campos `context` e
  `rules` de toda chamada `opsx instructions`. Trate o que vier em
  `rules` como obrigatório, não como sugestão de estilo.
- Escreva os artefatos integralmente em inglês. Essa é a exceção canônica à
  regra geral de documentação em português.
- Em `continue`, rode `opsx-handoff --mode artifact --artifact <id> <change>` sobre o único artefato criado. Em `ff` e antes de `apply`, rode
  `opsx-handoff --mode bundle <change>` sobre o bundle completo.

## Roteamento

A tabela abaixo vale somente depois que a decisão de rota adota OpenSpec.

| Intenção do usuário                                                                      | Workflow canônico | Primeira ação                                                                                                                                            |
| ---------------------------------------------------------------------------------------- | ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Criar uma nova change, iniciar OPSX, pedir `/opsx:new`                                   | `opsx-new`        | Executar preflight spec check, pedir aprovação explícita e só então criar a change, mostrar o primeiro artefato `ready` e parar antes de gerar artefatos |
| Continuar uma change, criar `proposal.md`, `design.md`, `tasks.md` ou o próximo artefato | `opsx-continue`   | Se o nome da change não vier no pedido, selecionar explicitamente a change, pedir aprovação e só então criar um único artefato `ready`                   |
| Fast-forward, gerar artefatos até ficar apply-ready, pedir `/opsx:ff`                    | `opsx-ff`         | Executar preflight spec check, pedir aprovação explícita e só então criar a change e avançar até satisfazer `apply.requires`                             |
| Implementar tarefas de uma change, pedir `/opsx:apply`                                   | `opsx-apply`      | Exigir bundle verde, ler `status` e `instructions apply`; `apply` é a única exceção que pode inferir ou auto-selecionar a change quando isso for seguro  |
| Verificar implementação antes de arquivar, pedir `/opsx:verify`                          | `opsx-verify`     | Selecionar explicitamente a change e comparar implementação com tarefas, specs, cenários e decisões de design                                            |
| Sincronizar delta specs com `openspec/specs`, pedir `/opsx:sync`                         | `opsx-sync`       | Selecionar explicitamente a change e executar o owner deterministico por operacao                                                                        |
| Arquivar uma change, pedir `/opsx:archive`                                               | `opsx-archive`    | Selecionar explicitamente a change, exigir completion verde sem override, avaliar sync e só então mover                                                  |
| Explorar ideias, trade-offs ou contexto de uma change, pedir `/opsx:explore`             | `opsx-explore`    | Investigar em modo read-only; persistência de artefato segue por `continue` ou `ff`                                                                      |

## Guardrails

- Uma mera menção a OpenSpec ou OPSX não autoriza `opsx new`, uma fonte de
  decisão, ou a escrita de artefatos. Primeiro conclua a decisão de rota.
- Selecionar uma rota OpenSpec também não autoriza sua primeira escrita. Anuncie
  a rota e aguarde aprovação explícita antes de `opsx new`, `opsx ff`,
  `opsx continue` ou da criação de qualquer change, fonte de decisão ou
  artefato formal, inclusive quando a rota veio de um comando `/opsx:*`.
- Não promova trabalho a OpenSpec por contagem, por adjetivos como "grande" ou
  "multifase", ou porque um plano tem mais de um passo.
- Nunca instrua o agente a aplicar código a partir de um arquivo flat em `openspec/changes/*.md`; esse não é o modelo ativo principal.
- Este repositório tem um único schema, `spec-driven`, e o `status` é a fonte de verdade sobre qual artefato está `ready`. Não deduza a ordem de cabeça: um artefato pode existir fora da sequência esperada.
- `new` e `ff` devem sempre executar o *Preflight Spec Consistency Check* para garantir que a proposta seja desenhada contra `openspec/specs/` atualizadas e avisar sobre delta specs ativos em andamento.
- `continue`, `sync`, `archive` e `verify` devem pedir seleção explícita da change quando o nome não vier no pedido. `apply` é a única exceção que pode inferir ou auto-selecionar quando isso for seguro, mas deve anunciar a escolha e como sobrescrevê-la.
- `continue` cria exatamente um artefato `ready` por invocação.
- `sync` deve ler delta spec e main spec antes da autorizacao; somente
  `sync_specs.py` edita main specs, por operacao completa e idempotente.
- Artefato escrito para leitor especialista é artefato incompleto. Use o gate
  `artifact` no `continue` e o gate `bundle` no `ff` e antes do `apply`.
- `apply` só reporta sucesso depois de gerar evidência com o comando de
  validação declarado em `openspec/handoff.json` (`validationCommand`) e o
  gate `opsx-handoff --mode apply <change>` confirmar tarefas, paths e
  fingerprint. Ele nao reivindica verify, sync, completion ou archive.
- `verify` compara implementação com tasks, requisitos, cenários e design, e
  roda `opsx-handoff --mode completion <change>`.
- `archive` trata completion vermelho como hard block sem confirmação
  interativa.
- `explore` não escreve código nem artefatos.

## Procedimento

1. Separe ativação da skill de adoção do lifecycle. Uma menção a OpenSpec/OPSX
   pode exigir triagem, mas não permite escrita formal.
2. Se o usuário deu um comando `/opsx:*` ou pediu explicitamente para criar,
   continuar, aplicar, verificar, sincronizar ou arquivar uma change, selecione
   a rota OpenSpec correspondente, anuncie a primeira escrita e peça aprovação
   antes de iniciar a operação que modifica o lifecycle; preserve seus
   guardrails.
3. Sem pedido explícito, procure uma fronteira formal: contrato compartilhado
   duradouro, múltiplos consumidores ou owners independentes, rollout, rollback,
   ou lifecycle auditável. Não use tamanho, número de arquivos ou número de
   passos como substituto dessa evidência.
4. Sem fronteira formal, escolha execução direta, Plan Mode, ou um único plano
   Markdown pertencente ao repositório conforme a necessidade de passos e
   handoff. Declare a rota e o motivo; não crie `openspec/changes/<name>/`.
5. Só na rota OpenSpec, use consultas read-only para mapear a intenção ao
   workflow canônico de OpenSpec e resolver schema, change
   ou próximo artefato quando não estiverem óbvios. Anuncie a primeira escrita,
   aguarde aprovação explícita e só então execute o workflow, preservando os
   guardrails sem misturar `continue`, `apply`, `sync`, `verify` ou `archive`.

## Exemplos

### Caso positivo

**Entrada:** "sincroniza os delta specs dessa change OpenSpec"
**Saída esperada:** Anuncia a rota `opsx-sync`, pede aprovação explícita antes da primeira escrita, exige seleção explícita da change se o nome não vier no pedido e preserva conteúdo não tocado do main spec.

### Caso positivo

**Entrada:** "/opsx:apply deploy"
**Saída esperada:** Roteia para `opsx-apply`, lê `opsx status` e `opsx instructions apply`, confirma a autorização própria de `apply` e implementa apenas as tasks pendentes da change `deploy`.

### Caso positivo

**Entrada:** "Preciso refatorar auth, permissões e onboarding em varias fases, com proposal, design, tasks e verificação rastreável antes de aplicar."
**Saída esperada:** Tratar como pedido de lifecycle formal, anunciar a rota OpenSpec e aguardar aprovação antes de produzir ou continuar os artifacts formais da change.

### Caso de aprovação obrigatória

**Entrada:** "/opsx:new calibrate-routing"
**Saída esperada:** Seleciona `opsx-new`, pode executar apenas o preflight
read-only, pede aprovação explícita e não cria a change até receber resposta
afirmativa.

### Caso de triagem

**Entrada:** "OpenSpec parece excessivo; deixe um único plano Markdown para este service isolado."
**Saída esperada:** Classifica como um plano Markdown pertencente ao repositório,
explica que não há contrato formal, e não cria `openspec/changes/<name>/`,
fonte de decisão, proposal, design, spec ou tasks.

### Caso de triagem

**Entrada:** "Tenho quatro ajustes ordenados para terminar nesta sessão, sem handoff."
**Saída esperada:** Usa Plan Mode; não cria plano no repositório nem artefatos
OpenSpec.

### Caso negativo

**Entrada:** "Monte um plano em checklist para refatorar um service isolado e ajustar os testes desse modulo."
**Por quê não:** Isso cabe em Plan Mode ou, se o handoff precisar persistir, em
um único plano Markdown; não precisa de `openspec-workflow` formal.

### Caso negativo

**Entrada:** "essa skill está fraca"
**Por quê não:** Isso é trabalho de governança ou autoria de skill; use `skill-governance`.

### Caso negativo

**Entrada:** "bug de CSS"
**Por quê não:** Não há workflow OpenSpec explícito nem lifecycle OPSX no pedido.

### Caso negativo

**Entrada:** "redesenha a arquitetura dessa feature"
**Por quê não:** Isso é arquitetura ou ideação, não roteamento OpenSpec.

## Evals de trigger

Deve acionar o lifecycle:

- "cria uma change OpenSpec"
- "/opsx:continue deploy"
- "sincroniza delta specs da minha change"
- "verifica essa implementação antes de arquivar"
- "quero fazer fast-forward de uma change OPSX"

Deve acionar apenas para triagem:

- "OpenSpec parece excessivo; faça um plano simples"
- "Mencionei OpenSpec, mas preciso mesmo de uma change?"
- "Quero um plano Markdown, não artefatos OpenSpec"

Não deve acionar:

- "plano simples sem openspec"
- "essa skill está fraca"
- "bug de CSS"
- "define a arquitetura dessa feature"
- "me ajuda a escrever uma proposal comercial"

## Evals de workflow

Detalhe completo em `references/EVALS.md`.

### Cenário 0: menção que exige somente triagem

**Entrada:** "OpenSpec parece excessivo; faça um plano Markdown para este módulo isolado."

- [ ] anuncia a rota de plano Markdown e o motivo
- [ ] não executa `opsx new` nem cria `openspec/changes/<name>/`
- [ ] não escreve fonte de decisão, proposal, design, spec ou tasks

### Cenário 1: `continue` sem nome de change

**Entrada:** "/opsx:continue"

- [ ] consulta `opsx list --json`
- [ ] pede seleção explícita da change
- [ ] anuncia a primeira escrita e pede aprovação explícita
- [ ] cria no máximo um artefato `ready`, somente após aprovação

### Cenário 2: `apply` sem nome de change

**Entrada:** "/opsx:apply"

- [ ] documenta que `apply` pode inferir ou auto-selecionar quando seguro
- [ ] anuncia a change escolhida e como sobrescrever a seleção
- [ ] exige a autorização própria de `apply` antes da primeira escrita de código
- [ ] para se `state` for `blocked` ou `all_done`

### Cenário 3: autoria de `tasks.md`

**Entrada:** "/opsx:continue add-x" com `tasks` no estado `ready`

- [ ] lê `references/HANDOFF_STANDARD.md` antes de escrever
- [ ] aplica o que veio em `rules` de `opsx instructions`
- [ ] escreve `## 0. Traceability` ligando requisitos e cenários a IDs reais
- [ ] tipa cada task e usa paths concretos, testes por cenário e comando exato
- [ ] aguarda aprovação explícita antes de escrever o artefato
- [ ] roda o gate `artifact` antes de declarar o único artefato pronto

## Referências

Leia apenas o arquivo necessário para o pedido atual:

| Situação                                                                          | Arquivo                          |
| --------------------------------------------------------------------------------- | -------------------------------- |
| Escrever ou revisar qualquer artefato de change                                   | `references/HANDOFF_STANDARD.md` |
| Confirmar roteamento comando -> workflow, inclusive exceções de seleção           | `references/COMMAND_MAP.md`      |
| Relembrar guardrails operacionais e diferenças entre `apply` e os outros comandos | `references/GUARDRAILS.md`       |
| Revisar trigger evals e workflow evals detalhados                                 | `references/EVALS.md`            |

## Scripts e Comandos

- `opsx validate --specs --strict`: validação estrutural e sintática de todas as especificações OpenSpec do consumidor.
- `opsx status` e `opsx instructions`: consulta de estado e regras operacionais de artefatos.
- `opsx-handoff --mode <artifact|bundle|apply|completion>`: gate determinístico para o schema `spec-driven`. O modo `completion` aceita somente evidência estruturada atual, validada pelo verificador que o projeto declara em `openspec/handoff.json`.
