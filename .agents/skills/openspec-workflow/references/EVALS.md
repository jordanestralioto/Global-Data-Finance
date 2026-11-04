# EVALS

## Automáticos e determinísticos

Estes casos pertencem à suíte repo-native e precisam provar os dois vereditos:

- alvo explícito inexistente falha;
- schema diferente de `spec-driven` falha;
- `artifact` valida somente o artefato indicado;
- seção obrigatória vazia falha;
- cada cenário precisa de categoria e do próprio `WHEN`/`THEN`;
- happy, negative e boundary existem ou têm N/A estruturado;
- cada decisão tem path e alternativa rejeitada;
- tipo de task, path concreto, test root e comando exato são resolvidos;
- requisito, cenário e task ID da tabela de traceability existem;
- caminho de task concluída respeita criação ou remoção;
- `.handoff-exempt` sozinho não isenta;
- relatório textual ou vermelho não conta como evidência;
- alteração de bytes, HEAD, perfil ou contrato de gate invalida o fingerprint;
- archive e apply contêm os hard blocks do lifecycle;
- mirrors GitHub, OpenCode e Claude são byte-identical ao workflow canônico.

## Manuais até existir harness repo-native reproduzível

- O texto é inequívoco para um desenvolvedor júnior sem contexto.
- As decisões técnicas são semanticamente corretas.
- Os cenários cobrem o risco real, não apenas satisfazem as categorias.
- A implementação corresponde ao comportamento e às decisões documentadas.
- A seleção separa ativação para triagem de adoção do lifecycle: pedido OPSX
  explícito executa a rota formal, mas mera menção a OpenSpec/OPSX não cria uma
  change, fonte de decisão ou artefato.
- Toda rota que criará uma change ou artefato formal anuncia a primeira escrita
  e aguarda aprovação explícita; a aprovação da criação não substitui as
  autorizações próprias de `apply`, `sync` ou `archive`.
- Pedidos sem OpenSpec/OPSX de planning simples, bug isolado ou revisão de outra
  skill não acionam esta skill.

Não descreva eval LLM manual como validação automatizada.

## Evals de seleção de rota

Cada caso abaixo verifica uma decisão de rota observável. Os casos que adotam o
lifecycle precisam passar pela barreira de aprovação; os demais casos que
carregam a skill param antes de qualquer escrita OpenSpec.

### `explicit-lifecycle`

**Entrada:** "`/opsx:continue deploy`"

- [ ] seleciona `opsx-continue` e preserva a seleção explícita da change;
- [ ] aplica os guardrails de artefato da rota formal;
- [ ] anuncia a primeira escrita e aguarda aprovação explícita antes de criar o artefato;
- [ ] não reclassifica o comando por contagem de arquivos ou tasks.

### `durable-contract`

**Entrada:** "Esta mudança altera um contrato compartilhado por dois consumidores; OpenSpec é necessário?"

- [ ] classifica a fronteira duradoura como rota OpenSpec;
- [ ] recomenda a rota, mas aguarda aprovação explícita antes de criar uma
  change, fonte de decisão ou artefato;
- [ ] não executa `opsx new`, `opsx ff` ou `opsx continue` antes da aprovação.

### `approval-gate`

**Entrada:** "`/opsx:new calibrate-routing`"

- [ ] preserva a seleção explícita de `opsx-new`;
- [ ] permite apenas inspeção/preflight read-only antes da aprovação;
- [ ] não cria `openspec/changes/<name>/` nem artefato formal sem resposta
  afirmativa do usuário.

### `mention-only`

**Entrada:** "OpenSpec parece excessivo; preciso mesmo de uma change para este service isolado?"

- [ ] explica que a ativação serviu apenas para triagem;
- [ ] seleciona execução direta, Plan Mode ou plano Markdown segundo os passos e
  o handoff pedidos;
- [ ] não executa `opsx new` e não cria `openspec/changes/<name>/`, fonte de
  decisão, proposal, design, spec ou tasks.

### `plan-mode`

**Entrada:** "Tenho quatro ajustes ordenados para concluir nesta sessão, sem handoff."

- [ ] seleciona Plan Mode;
- [ ] não escreve um plano no repositório;
- [ ] não cria uma change OpenSpec ou artefato formal.

### `markdown-handoff`

**Entrada:** "Deixe os quatro ajustes ordenados em um plano para a próxima sessão."

- [ ] seleciona um único plano Markdown pertencente ao repositório;
- [ ] explica que não existe contrato compartilhado, rollout, rollback ou
  lifecycle auditável;
- [ ] não cria `openspec/changes/<name>/`, fonte de decisão ou artefatos formais.

## Transcrição comportamental normalizada

O rollout do lifecycle exige uma transcrição JSON versionada por execução
supervisionada. O registro deve conter `schemaVersion`, `changeName`,
`sourceDigest`, `events`, `bypassCount`, `protectedDiff`, `blockers`,
`rollback`, `knowledgePreserved` e `verdict`. Cada evento identifica a
fronteira (`new`, `continue`, `ff`, `apply`, `verify`, `sync` ou `archive`), a
ação, o resultado, os IDs de decisão, os paths escritos e a autorização
específica do change. O transcript não pode depender de texto conversacional
para provar um gate.

O registro elegível também traz uma atestação de operador e revisor, um artefato
de sessão preservado com SHA-256 e recibos observados. Um script pode validar a
estrutura ou inicializar um template bloqueado, mas não pode escrever a change,
o transcript e a promoção e depois chamar esse resultado de supervisão real.

### Casos obrigatórios do lifecycle

- `full-traversal`: preflight confirmado, autoria, apply autorizado, verify
  com relatório semântico, sync autorizado e archive somente após gates
  verdes; cada etapa registra sua evidência concreta;
- `semantic-divergence`: uma divergência de requisito, cenário ou decisão de
  design aparece em `blockers`, com `verdict: blocked`, e nunca como warning;
- `authorized-sync`: o resumo inclui todas as capacidades e a autorização do
  nome exato; MODIFIED substitui o bloco inteiro, REMOVED prova ausencia,
  RENAMED troca o heading, e a segunda execução preserva todos os bytes;
- `apply-exit`: tarefas, paths e gate-report atuais permitem sucesso de apply,
  mas nao satisfazem completion sem relatorio semantico e sync;
- `archived-owner`: uma dependencia ativa continua resolvendo seu owner
  arquivado, e o ID arquivado continua exclusivo;
- `archive-block`: delta não sincronizado, task aberta, gate mecânico vermelho
  ou relatório stale encerra a execução sem mover o diretório e sem opção de
  override;
- `rollback-preservation`: uma reversão pode retirar a enforcement code, mas
  mantém fonte confirmada, manifests, reports, transcripts e conhecimento da
  causa;
- `clean-checkout-list`: clones limpos no mesmo commit produzem o mesmo JSON
  de listagem, sem identidade derivada de mtime.
- `operator-attestation`: uma sessão real preserva autorizações distintas,
  artefato de sessão, recibos e snapshots dos seis limites; o validador verifica
  apenas essa estrutura, sem alegar ter observado o agente;
- `self-generating-recorder`: qualquer transcript que carregue metadado de
  gerador ou seja criado pelo mesmo script que altera a change termina como
  bloqueado, mesmo com recibos sintaticamente verdes.

Cada caso registra `bypassCount: 0` quando aprovado. Um único bypass, uma
autorização reutilizada por outro change, escrita antes da autorização ou
evidência sem digest/fingerprint correspondente impede a promoção para
workflow padrão.
