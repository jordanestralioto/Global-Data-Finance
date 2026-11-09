---
name: openspec-workflow
description: >-
  Use para executar workflows OpenSpec/OPSX pedidos pelo usuário ou decidir se
  uma mudança exige artefatos formais. Ative com "cria uma change", "faz
  proposal/design/tasks", "revisa uma change", "valida spec", "sincroniza specs"
  ou "preciso mesmo de OpenSpec?". Mencionar OpenSpec sem pedir o workflow aciona
  apenas triagem. Sem pedido explícito, escolha o workflow só para contrato duradouro compartilhado,
  múltiplos consumidores ou responsáveis independentes, rollout, rollback ou
  auditoria. Não use para bugs locais, planos simples ou revisão de skills sem
  contrato compartilhado.
---

# OpenSpec Workflow

## Contrato

- Os comandos e prompts do lifecycle OPSX são a fonte canônica do fluxo. Esta skill existe para roteamento e guardrails, não para duplicar o workflow inteiro.
- O formato ativo padrão de uma change é `openspec/changes/<name>/` com `.openspec.yaml`, `proposal.md`, `specs/<capability>/spec.md`, `design.md` e `tasks.md`.
- Changes novas exigem `decision_source` confirmado no manifesto. O envelope e os relatórios mecânico e semântico estão em `references/HANDOFF_STANDARD.md`.
- Arquivos soltos como `openspec/changes/*.md` são artefatos legados ou especiais do consumidor, não o modelo principal do workflow ativo.
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

Escreva para um desenvolvedor júnior no repositório consumidor, que
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
- Quando o consumidor configura `context` e `rules` em `openspec/config.yaml`,
  `opsx instructions` injeta esses campos. Trate as regras retornadas como
  obrigatórias; a ausência do arquivo não injeta o contrato automaticamente.
- Escreva os artefatos integralmente em inglês.
- Em `continue`, rode `opsx-handoff --mode artifact --artifact <id> <change>` sobre o único artefato criado. Em `ff` e antes de `apply`, rode
  `opsx-handoff --mode bundle <change>` sobre o bundle completo.

## Roteamento

A tabela abaixo vale somente depois que a decisão de rota adota OpenSpec.

| Intenção do usuário                                                                      | Workflow canônico | Primeira ação                                                                                                                                            |
| ---------------------------------------------------------------------------------------- | ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Criar uma nova change, iniciar OPSX, pedir `/opsx:new`                                   | `opsx-new`        | Executar preflight spec check, pedir aprovação explícita e só então criar a change, mostrar o primeiro artefato `ready` e parar antes de gerar artefatos |
| Continuar uma change, criar `proposal.md`, `design.md`, `tasks.md` ou o próximo artefato | `opsx-continue`   | Se o nome da change não vier no pedido, selecionar explicitamente a change, pedir aprovação e só então criar um único artefato `ready`                   |
| Fast-forward, gerar artefatos até ficar apply-ready, pedir `/opsx:ff`                    | `opsx-ff`         | Executar preflight spec check, pedir aprovação explícita e só então criar a change e avançar até satisfazer `apply.requires`                             |
| Revisar artefatos antes da implementação, pedir `/opsx:review`                           | `opsx-review`     | Selecionar explicitamente a change, executar o gate `bundle` e revisar artefatos e fonte de decisão em modo read-only                                    |
| Implementar tarefas de uma change, pedir `/opsx:apply`                                   | `opsx-apply`      | Exigir bundle verde, ler `status` e `instructions apply`; `apply` é a única exceção que pode inferir ou auto-selecionar a change quando isso for seguro  |
| Verificar implementação antes de arquivar, pedir `/opsx:verify`                          | `opsx-verify`     | Selecionar explicitamente a change e comparar implementação com tarefas, specs, cenários e decisões de design                                            |
| Sincronizar delta specs com `openspec/specs`, pedir `/opsx:sync`                         | `opsx-sync`       | Selecionar explicitamente a change e executar o owner deterministico por operacao                                                                        |
| Arquivar uma change, pedir `/opsx:archive`                                               | `opsx-archive`    | Selecionar explicitamente a change, exigir completion verde sem override, avaliar sync e só então mover                                                  |
| Explorar ideias, trade-offs ou contexto de uma change, pedir `/opsx:explore`             | `opsx-explore`    | Investigar em modo read-only; persistência de artefato segue por `continue` ou `ff`                                                                      |

## Guardrails

- Nunca instrua o agente a aplicar código a partir de um arquivo flat em `openspec/changes/*.md`; esse não é o modelo ativo principal.
- O runtime instalado suporta `spec-driven`, e o `status` é a fonte de verdade sobre qual artefato está `ready`. Não deduza a ordem de cabeça: um artefato pode existir fora da sequência esperada.
- `new` e `ff` devem sempre executar o *Preflight Spec Consistency Check* para garantir que a proposta seja desenhada contra `openspec/specs/` atualizadas e avisar sobre delta specs ativos em andamento.
- Após criar a change e antes de escrever artefatos, aplicar, sincronizar ou arquivar, execute `opsx preflight --change "<name>" --json`. Qualquer finding ou exit code não zero bloqueia a operação; esse check de proveniência é distinto do preflight de consistência de specs.
- `continue`, `review`, `sync`, `archive` e `verify` devem pedir seleção explícita da change quando o nome não vier no pedido. `apply` é a única exceção que pode inferir ou auto-selecionar quando isso for seguro, mas deve anunciar a escolha e como sobrescrevê-la.
- `continue` cria exatamente um artefato `ready` por invocação.
- `review` audita o bundle antes de `apply`, sem editar código ou artefatos.
- `sync` deve ler delta spec e main spec antes da autorização; use somente
  `opsx-sync` para editar main specs, por operação completa e idempotente.
- Artefato escrito para leitor especialista é artefato incompleto. Use o gate
  `artifact` no `continue` e o gate `bundle` no `ff` e antes do `apply`.
- `apply` só reporta sucesso depois de gerar evidência com o comando de
  validação declarado em `openspec/handoff.json` (`validationCommand`) e o
  gate `opsx-handoff --mode apply <change>` confirmar tarefas, paths e
  fingerprint. Ele não reivindica verify, sync, completion ou archive.
- `verify` compara implementação com tasks, requisitos, cenários e design,
  captura `opsx fingerprint --change "<name>" --json`, grava
  `evidence/verification-report.json` e exige o gate
  `opsx-handoff --mode completion <change>` verde.
- `archive` trata completion vermelho como hard block sem confirmação
  interativa.
- `explore` não escreve código nem artefatos.

## Procedimento

1. Aplique a tabela de **Decisão de rota** e anuncie a rota e o motivo.
2. Na rota OpenSpec, use **Roteamento** para abrir o workflow canônico e
   resolver change, schema e próximo artefato por consultas read-only.
3. Antes de escrever, cumpra a barreira de aprovação da **Decisão de rota** e
   as autorizações específicas do workflow selecionado.
4. Execute somente esse workflow, observe sua condição de parada e reporte
   os gates realmente executados. Consulte as referências conforme o artefato.

## Exemplos

### Caso positivo

**Entrada:** "sincroniza os delta specs dessa change OpenSpec"
**Saída esperada:** Anuncia a rota `opsx-sync`, pede aprovação explícita antes da primeira escrita, exige seleção explícita da change se o nome não vier no pedido e preserva conteúdo não tocado do main spec.

### Caso positivo

**Entrada:** "/opsx:review deploy"
**Saída esperada:** Roteia para `opsx-review`, executa o gate `bundle`, revisa os
artefatos e a fonte de decisão e apresenta achados sem editar arquivos.

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
- "revisa a change OpenSpec antes de implementar"
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

Casos propostos em `references/EVALS.md`. Registre execução e transcrição antes
de afirmar eficácia comportamental; os validadores estáticos não a demonstram.

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
- `opsx new change`: cria o manifesto com os argumentos obrigatórios de proveniência descritos em `references/HANDOFF_STANDARD.md`.
- `opsx preflight --change "<name>" --json`: valida fonte de decisão, digest, IDs, dependências e ownership.
- `opsx fingerprint --change "<name>" --json`: captura `repositoryFingerprint` para o relatório semântico.
- `opsx-sync --change "<name>" --json`: aplica delta specs; repita com `--check` para conferir idempotência sem escrita.
- `opsx-handoff --mode <artifact|bundle|apply|completion>`: gate determinístico para o schema `spec-driven`. O modo `completion` aceita somente evidência estruturada atual, validada pelo verificador que o projeto declara em `openspec/handoff.json`.
