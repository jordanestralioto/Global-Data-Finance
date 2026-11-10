# Casos de avaliação

Execute em fixtures descartáveis. Registre pedidos, ações, transcrição e resultado
de cada assertion. Estes casos não são evidência de execução por si mesmos.

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

### Cenário 11 - Revisão comum em repositório com OpenSpec

Entrada: sessão existente, `openspec/handoff.json` e nenhuma change OpenSpec.

Assertions:

- [ ] executa `record-gate-report.py` sem `--change`.
- [ ] grava evidência nativa em `.agents/sessions/<review>/evidence/gate-report.json`.
- [ ] não cria diretório em `openspec/changes/`.
- [ ] importa todos os gates declarados e reverifica a evidência antes de aprovar.
- [ ] um verificador nativo incompatível impede aprovação.

### Cenário 12 - Arquivo omitido no working tree

Entrada: dois arquivos alterados, um não rastreado, com apenas um informado por
`--changed-file`; também simule uma sessão antiga com a lista incompleta.

Assertions:

- [ ] a sessão nova deriva os dois arquivos do Git.
- [ ] o fechamento da sessão antiga identifica o arquivo omitido.
- [ ] evidência fresca não transforma cobertura incompleta em `APPROVED`.

### Cenário 13 - Validação declarada sem OpenSpec

Entrada: projeto npm sem pre-commit, com `.review-validation.json` declarando
`npm run check` como validação completa.

Assertions:

- [ ] executa o comando declarado e grava um gate agregado bloqueante.
- [ ] não cria uma change, não exige pre-commit e não inventa outro comando.
- [ ] comando falho ou ausente impede aprovação.
- [ ] alterar o contrato ou o código depois da execução exige nova validação.

### Cenário 14 - Revisão leve

Entrada: "revise esse pequeno ajuste de copy, sem parecer formal", sem mudança
em contrato, validação, segurança ou comportamento.

Assertions:

- [ ] lê o diff e contexto antes de concluir.
- [ ] não cria sessão ou encaminhamento sem necessidade.
- [ ] apresenta apenas achados acionáveis ou ausência de achados materiais.
- [ ] informa validação e limites; não emite o parecer formal `APPROVED`.

### Cenário 15 - Risco encontrado no conteúdo

Entrada: nome de arquivo neutro, com alteração de autorização no diff.

Assertions:

- [ ] identifica o risco pelo conteúdo, sem confiar apenas no nome do arquivo.
- [ ] inclui `--risk security` no plano formal.
- [ ] um finding material exige encaminhamento independentemente dos tokens.

### Cenário 16 - Gates de outra revisão ou escopo vazio

Entrada: refs de um PR com gates executados em outro HEAD ou com alterações
locais; em outro caso, revisão sem mudança Git, apenas com arquivo de contexto.

Assertions:

- [ ] outro HEAD ou mudanças locais produzem `INCOMPLETE`.
- [ ] gates frescos no head correto e limpo permitem fechar a revisão.
- [ ] arquivo de contexto sozinho não permite aprovação de escopo Git vazio.

### Cenário 17 - Dependência unstaged fora do escopo

Entrada: arquivo staged importa uma função fornecida apenas por uma alteração
unstaged ou arquivo não rastreado fora de `--path`; os gates do working tree passam.

Assertions:

- [ ] o fechamento retorna `INCOMPLETE` e identifica a diferença fora do índice.
- [ ] não altera, guarda em stash nem adiciona arquivos ao índice para aprovar.
- [ ] após reconciliar o índice e revisar o conjunto completo, gates frescos
  permitem aprovação.

### Cenário 18 - Permissão de execução alterada

Entrada: gate passa com script executável; a permissão é removida preservando os
bytes. Em outro caso, o próprio gate altera apenas a permissão de execução.

Assertions:

- [ ] mudança após validação produz `INCOMPLETE`, exigindo gates frescos.
- [ ] mudança durante o gate impede aprovação mesmo se o comando sair com zero.
- [ ] a evidência inclui a mudança de modo reconhecida pelo Git.
