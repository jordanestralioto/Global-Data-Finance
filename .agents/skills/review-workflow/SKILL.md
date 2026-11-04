---
name: review-workflow
description: >-
  Use para conduzir revisões estruturadas de changes e PRs. Ative quando a
  solicitação envolver "abrir sessão de revisão", "montar plano por risco",
  "registrar apontamento", "gerar parecer", "fechar revisão", "ler gate-report",
  "preparar encaminhamento de segurança", "rodar revisão isolada", "review de
  PR", "revisa esse diff" ou "segunda leitura", ou revisar uma mudança antes de
  encerrá-la. Não use para validação mecânica isolada de comandos; prefira
  `lint-and-validate`. Não use para auditoria de segurança no terminal;
  encaminhe para `security-engineer`.
---

# Review Workflow

## Contexto

Esta skill define um protocolo de revisão estruturada.

Classifique cada item
por tipo de risco, não por framework:

- `security`: segurança e limites de confiança.
- `interface`: APIs, contratos públicos e entradas/saídas.
- `data`: integridade, persistência, consultas e migrações.
- `behavior`: comportamento de runtime e regras de negócio.
- `tests`: cobertura, regressão e evidência de validação.
- `docs`: documentação, rastreabilidade e contratos escritos.

Use estes nomes técnicos apenas como identificadores estáveis de arquivo:

- `finding`: apontamento de revisão.
- `verdict`: parecer final.
- `gate-report`: relatório de validação automatizada.
- `security-handoff`: encaminhamento para revisão de segurança.

## Procedimento

1. Crie a sessão com `scripts/init-review-session.py`, ou retome uma sessão
   existente com `--resume`. Nunca repita a criação sobre uma sessão existente.
2. Se o plano ainda estiver em `draft`, gere-o com
   `scripts/build-review-plan.py`; caso contrário, continue o plano existente.
   Confira que cada arquivo alterado aparece em pelo menos um item. Arquivos
   sem categoria específica entram no item `behavior`.
3. Avalie se deve executar a seção `Revisão Isolada`.
4. Leia o diff e contexto adjacente de cada item planejado.
5. Registre apenas apontamentos acionáveis com `scripts/append-finding.py`.
   Evite comentários de estilo que uma validação mecânica resolveria.
6. Execute a validação repo-native por `scripts/record-gate-report.py`. O
   script seleciona o comando de `openspec/handoff.json` (com `--change`) ou,
   na ausência dele, `pre-commit run --all-files` quando há hooks declarados
   sem estágios adicionais. Hooks com estágios explícitos exigem contrato
   estruturado para evitar aprovação sem executar parte dos gates.
   Inspecione o entrypoint de scripts locais antes de executá-los. O relatório
   registra falhas, rejeita alterações no código durante a validação e vincula
   o resultado ao estado do repositório; o fechamento confere esse vínculo
   novamente. Sem contrato declarado, preserve
   `INCOMPLETE` e informe o comando ausente.
7. Crie `security-handoff` com `scripts/create-security-handoff.py` para todo
   apontamento de segurança não descartado com severidade `blocker` ou
   `warning` e confiança `high` ou `medium`. Encaminhe-o a
   `security-engineer`. Só registre `cleared` ou `waived` depois de receber e
   conferir a análise independente; inclua `--reviewed-by security-engineer`
   e `--review-summary`. O CLI registra a declaração, mas não autentica quem
   executou a revisão.
8. Marque itens concluídos e consolide o parecer final com
   `scripts/consolidate-verdict.py`.
9. Exporte o resumo legível com `scripts/export-review-summary.py`.

## Comandos Mínimos

Use os scripts como interface canônica. Estes exemplos reduzem inferência sobre
argumentos e payloads sem substituir a leitura do diff.

```bash
python3 .agents/skills/review-workflow/scripts/init-review-session.py \
  --change-type bug-fix \
  --changed-by codex \
  --changed-file src/example.py
```

Para retomar, use `--resume --session-dir .agents/sessions/review-<id>`.
O comando preserva os artefatos e recusa opções de criação.
Em revisão de PR, informe também `--base-ref` e `--head-ref` e os arquivos do
diff; o fechamento compara a lista com `git diff base...head`. Em revisão do
working tree, confira a lista contra o diff e o estado de Git antes de abrir
a sessão, pois não há refs que delimitem automaticamente a mudança.

```bash
python3 .agents/skills/review-workflow/scripts/build-review-plan.py \
  --session-dir .agents/sessions/review-<id>
```

Execute o contrato de validação do repositório e grave os gates:

```bash
python3 .agents/skills/review-workflow/scripts/record-gate-report.py \
  --session-dir .agents/sessions/review-<id>
```

Se houver `openspec/handoff.json`, acrescente `--change <nome-da-change>`.
O script deriva o comando, o caminho da evidência e o verificador desse
contrato, exige relatório recém-gerado e importa os gates individuais. Não
substitua o verificador por um comando escolhido na revisão. Se o código mudar
depois da validação, execute o script novamente antes de consolidar o parecer.

Para encaminhar segurança, crie primeiro o handoff em `pending`:

```bash
python3 .agents/skills/review-workflow/scripts/create-security-handoff.py \
  --session-dir .agents/sessions/review-<id> \
  --reason "Review the authorization finding."
```

Depois da resposta do especialista, registre o resultado com `--status cleared` ou `--status changes_required`, `--reviewed-by security-engineer` e
`--review-summary "<resultado concreto>"`. Confira a resposta recebida antes
de executar o comando: o arquivo local registra a procedência declarada, mas
não prova a identidade do revisor.

Para registrar `finding`, envie JSON pelo stdin para manter o artefato
validável pelo schema:

```bash
python3 .agents/skills/review-workflow/scripts/append-finding.py \
  --session-dir .agents/sessions/review-<id> <<'JSON'
{
  "topic": "behavior:runtime",
  "severity": "blocker",
  "confidence": "high",
  "summary": "Short actionable summary.",
  "impact": "Concrete runtime or contract impact.",
  "recommendedAction": "Specific change required before approval.",
  "evidence": {
    "file": "src/example.py",
    "line": 42,
    "snippet": "minimal relevant snippet"
  }
}
JSON
```

## Revisão Isolada

Esta etapa é recomendada, mas não obrigatória. Use quando a plataforma permitir
subagente, chamada isolada ou nova conversa com contexto limpo.

Execute revisão isolada quando pelo menos uma condição for verdadeira:

- a mesma IA implementou a mudança e também vai revisar;
- o usuário pediu revisão extra, segunda leitura ou parecer final;
- a mudança toca `security`, `interface`, `data` ou comportamento central;
- a mudança altera vários arquivos ou tem diff difícil de ler;
- `gate-report` tem gate falho, indisponível ou ainda ausente;
- existe dúvida real sobre regressão, contrato, dado ou segurança.

Não execute revisão isolada quando:

- a plataforma não oferece subagente nem contexto limpo;
- o pedido é apenas rodar validação mecânica;
- a mudança é trivial e só altera texto ou documentação sem contrato;

Preferir uma IA neutra, sem papel de implementação. Não escolha
`developer-engineer` como revisor isolado padrão: esse papel é otimizado para
implementar e remediar. Se a plataforma só oferecer `developer-engineer` como
subagente disponível, dispense a revisão isolada e registre essa limitação. Use
`security-engineer` apenas para risco material de segurança, via
`security-handoff`.

Envie para a revisão isolada somente:

- objetivo da mudança;
- arquivos alterados;
- diretório da sessão;
- plano de revisão;
- `gate-report`, se existir;
- instrução para retornar apenas apontamentos candidatos com evidência.

Use esta instrução curta para o subagente ou IA isolada:

```text
Revise esta mudança em contexto limpo.
Não edite arquivos.
Não altere artefatos.
Não gere parecer final.
Retorne apenas apontamentos candidatos.

Para cada apontamento, informe:
- item do plano relacionado;
- severidade: blocker, warning ou nit;
- confiança: high, medium ou low;
- arquivo e linha;
- evidência;
- impacto;
- ação recomendada.

Se não houver problema material, responda: "sem apontamentos materiais".
```

A IA que executa esta skill deve validar cada apontamento candidato antes de
registrar. Ignore candidato sem evidência clara. Registre os válidos com
`scripts/append-finding.py`. Se a revisão isolada não foi executada, informe o
motivo na saída final.

## Scripts

- `scripts/init-review-session.py`: cria os artefatos iniciais.
- `scripts/build-review-plan.py`: cria o plano por tipo de risco.
- `scripts/append-finding.py`: registra um apontamento estruturado.
- `scripts/record-gate-report.py`: executa gates e grava a evidência da sessão.
- `scripts/expand-review-item-context.py`: adiciona contexto relacionado.
- `scripts/mark-review-item-done.py`: conclui item do plano.
- `scripts/detect-security-touch.py`: detecta sinais de superfície sensível.
- `scripts/create-security-handoff.py`: cria ou atualiza encaminhamento de segurança.
- `scripts/consolidate-verdict.py`: consolida apontamentos, gates e segurança.
- `scripts/export-review-summary.py`: gera resumo legível e reproduzível.

## Se Algo Falhar

- Se sessão, plano ou gates estiverem ausentes, use o script correspondente.
  Nunca escreva o artefato JSON manualmente.
- Se `gate-report` estiver pendente, vazio ou contiver gate bloqueante não
  executado, preserve `INCOMPLETE` até a validação ser concluída. Uma gate
  bloqueante que já falhou produz `CHANGES_REQUIRED` e mantém as lacunas
  restantes em `blockingReasons`.
- Se a evidência estruturada mudar ou a reverificação nativa falhar, preserve
  `INCOMPLETE` e execute novamente o contrato de validação.
- Se o contexto factual não sustentar um apontamento, registre a incerteza ou
  expanda contexto antes de salvar o apontamento.
- Se segurança estiver pendente, preserve `SECURITY_REVIEW_REQUIRED` até o
  encaminhamento de segurança ficar em estado terminal.

## Condições de Saída

- Sessão, plano, `gate-report` e `verdict` existem como JSON canônico; todo
  arquivo alterado tem item de revisão e toda gate bloqueante foi executada.
- Todo apontamento tem severidade, confiança, impacto, ação recomendada e
  evidência.
- O resumo legível reflete os artefatos atuais.
- O próximo estado está claro: aprovado, mudanças necessárias, revisão de
  segurança necessária, bloqueado ou incompleto.
- A saída informa se a revisão isolada foi executada, dispensada ou indisponível.

## Saída Esperada

Informe o parecer final, bloqueios, observações, gates relevantes, status de
segurança, arquivos revisados, status da revisão isolada e limitações. Se a
revisão foi feita pela mesma IA que implementou a mudança, declare essa
limitação.

## Exemplos

### Caso positivo

**Entrada:** "fecha a revisão desse diff e gera o parecer depois da validação"
**Saída esperada:** criar ou retomar sessão, ler `gate-report`, revisar por
risco, consolidar `verdict` e exportar resumo.

### Caso negativo

**Entrada:** "só roda os testes e me diz se passou"
**Por quê não:** validação mecânica isolada pertence a `lint-and-validate`.

## Evals de trigger

Deve acionar:

- "fecha a revisão com parecer"
- "monta plano de revisão por risco"
- "registra esse apontamento"
- "prepara encaminhamento para segurança"
- "revisa antes de encerrar"
- "faz uma segunda leitura em contexto limpo"
- "review de PR antes de mergear"
- "revisa esse diff e me diz se aprova"

Não deve acionar:

- "roda validação dos gates"
- "explora esse possível IDOR"
- "corrige o bug diretamente"
- "define uma estratégia de testes ampla"

## Evals de workflow

### Cenário 1 - Gate bloqueante falhou

Entrada: sessão planejada com `gate-report` contendo gate bloqueante `failed`.

Assertions:

- [ ] consolida `verdict` como `CHANGES_REQUIRED`.
- [ ] inclui o gate bloqueante em `blockingReasons`.
- [ ] não declara aprovação parcial como sucesso.

### Cenário 2 - Segurança pendente

Entrada: sessão com `security-handoff` em `pending` ou `in_review`.

Assertions:

- [ ] consolida `verdict` como `SECURITY_REVIEW_REQUIRED`.
- [ ] preserva o status de segurança como pendente.
- [ ] não aprova risco material sem revisão própria de segurança.

### Cenário 3 - Revisão com findings não bloqueantes

Entrada: sessão com apenas findings não relacionados à segurança, `warning` ou
`nit`, abertos e gates bloqueantes aprovados.

Assertions:

- [ ] consolida `verdict` como `APPROVED`.
- [ ] lista warnings e nits como `advisories`.
- [ ] não transforma advisory em bloqueio sem evidência adicional.

### Cenário 4 - Revisão isolada indisponível

Entrada: mudança não trivial, mas a plataforma não oferece subagente nem
contexto limpo.

Assertions:

- [ ] executa a revisão principal mesmo sem revisão isolada.
- [ ] informa a ausência de revisão isolada como limitação.
- [ ] não trata essa ausência como falha automática.

### Cenário 5 - Artefatos canônicos

Entrada: pedido para registrar um apontamento ou encerrar parecer.

Assertions:

- [ ] cria artefatos por scripts, não por JSON manual.
- [ ] grava `gate-report` com `record-gate-report.py`.
- [ ] registra finding com severidade, confiança, impacto, ação e evidência.
- [ ] exporta resumo legível depois de consolidar o `verdict`.

### Cenário 6 - Evidência incompleta

Entrada: relatório pendente, vazio ou com gate bloqueante não executado.

Assertions:

- [ ] consolida `verdict` como `INCOMPLETE`.
- [ ] explica a evidência ausente em `blockingReasons`.
- [ ] não emite `APPROVED`.

### Cenário 7 - Arquivo sem categoria e retomada

Entrada: mudança em `pkg/selection.py` e sessão já iniciada.

Assertions:

- [ ] o arquivo entra em um item `behavior`.
- [ ] `--resume` mantém plano, apontamentos, gates e parecer existentes.
- [ ] repetir a criação falha sem sobrescrever a sessão.

### Cenário 8 - Segurança material sem handoff

Entrada: finding `security:` aberto, `warning/high`, sem `security-handoff`.

Assertions:

- [ ] consolida `verdict` como `SECURITY_REVIEW_REQUIRED`.
- [ ] informa que o handoff precisa ser criado.
- [ ] não aprova o risco como advisory comum.

### Cenário 9 - Evidência adulterada ou estado alterado

Entrada: gate aprovado, seguido de alteração no código ou no relatório nativo.

Assertions:

- [ ] reverifica o contrato e o estado no fechamento.
- [ ] consolida `INCOMPLETE` e pede nova validação.

### Cenário 10 - Resultado de segurança sem análise registrada

Entrada: handoff pendente e tentativa de marcar `cleared` sem o resultado do
`security-engineer`.

Assertions:

- [ ] recusa o fechamento do handoff.
- [ ] mantém `SECURITY_REVIEW_REQUIRED`.
