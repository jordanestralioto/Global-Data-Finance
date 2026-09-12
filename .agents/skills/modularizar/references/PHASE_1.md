# Modularizar Phase 1

Use este reference apenas para **Fase 1A** e **Fase 1B**. Se o objetivo atual
já for extrair módulos depois de a limpeza ter sido concluída e aprovada, pare e
troque para `PHASE_2.md`.

## Abrir junto nesta etapa

- `references/PLAN_TEMPLATE.md` ao preencher ou atualizar `modularizar_<target-basename>.md`
- `.agents/skills/modularizar/scripts/modularizar_guard.sh` ao inicializar e validar o plano

## Objetivo da etapa

1. Diagnosticar o alvo com inventário completo e auditável.
2. Congelar riscos, migrações e promoções de símbolos no Gate 1.
3. Executar apenas o saneamento profundo aprovado.
4. Encerrar a etapa com o log da Fase 1B preenchido no mesmo plano.
5. Decidir, com evidência pós-execução, se a modularização estrutural da Fase 2 ainda é necessária.

## Sequência operacional

01. Inicialize ou atualize `modularizar_<target-basename>.md` com:
    - `bash .agents/skills/modularizar/scripts/modularizar_guard.sh init-plan --target <file-or-module> --task <task-name> --author developer-engineer`
02. Reescreva imediatamente cabeçalho, título e campos derivados do template. O guard falha se placeholders como `<target-basename>` ou `<file-or-module>` permanecerem.
03. Preencha `## 3. Contract and Migration Baseline`.
04. Preencha todas as subseções de `## 4. Phase 1A - Deep Remediation Proposal`.
05. Registre cada categoria do inventário, mesmo sem achado material:
    - duplicatas internas
    - reaproveitamento de utilitário compartilhado ou justificativa para não reaproveitar
    - otimização de complexidade e Big-O
    - limpeza de comentários
    - naming e visibilidade
    - migrações de callers e contrato
06. Nesta etapa, não preencha `## 6. Phase 2A - Modularization Proposal` nem `## 7. Phase 2B - Modularization Execution Log`. Essas seções continuam intocadas até `GATE_1_APPROVED: YES` e `PHASE_1_EXECUTED: YES`.
07. Quando não houver achado material, use os sentinelas oficiais do `PLAN_TEMPLATE.md`:
    - `Finding status: no-finding`
    - `Files affected: none`
    - `Contract/import/export impact: none`
    - `Risk: none material`
    - `Rollback: not applicable`
08. Para Python, registre explicitamente em `P1-NAME` todo símbolo privado com prefixo `_` que precise virar público por já representar superfície real de uso.
09. Peça aprovação explícita do usuário para o Gate 1 e pare antes de editar código.
10. Após a aprovação, valide com:

- `bash .agents/skills/modularizar/scripts/modularizar_guard.sh validate-plan --phase phase1 --target <file-or-module>`

11. Execute apenas o saneamento profundo aprovado na Fase 1B:

- remover duplicação interna
- trocar duplicação por utilitário compartilhado existente quando fizer sentido
- criar novo utilitário compartilhado só com justificativa e consumidores previstos
- aplicar otimizações materiais de complexidade
- limpar comentários ruins ou obsoletos
- corrigir naming e visibilidade
- promover símbolos Python privados aprovados
- migrar callers/imports/exports necessários para concluir a limpeza

12. Atualize `## 5. Phase 1B - Deep Remediation Execution Log` no mesmo plano com arquivos alterados, callers migrados, símbolos promovidos e evidência de validação.
13. Depois de preencher o log da Fase 1, complete `### 5.1 Phase 2 necessity assessment`:

- classifique `Residual condition` como `none`, `size`, `complexity` ou `both`;
- marque `Structural separation needed` como `YES` ou `NO`;
- marque `PHASE_2_NEEDED: YES` somente se o alvo ainda tiver tamanho ou complexidade material e existir uma necessidade estrutural concreta de separar responsabilidades;
- registre a evidência remanescente, o problema estrutural e o benefício esperado da extração;
- marque `PHASE_2_NEEDED: NO` quando a Fase 1 tiver resolvido o problema, o alvo estiver coeso ou a extração apenas redistribuir código mecanicamente.

14. Se `PHASE_2_NEEDED: NO`, use `Structural separation needed: NO`, registre a justificativa, não preencha `## 6` nem `## 7`, e valide o encerramento com:

- `bash .agents/skills/modularizar/scripts/modularizar_guard.sh validate-plan --phase phase1-complete --target <file-or-module>`
  Depois disso, não peça o Gate 2 nem gere o report da Fase 2.

15. Só depois de `GATE_1_APPROVED: YES`, `PHASE_1_EXECUTED: YES`, `PHASE_2_NEEDED: YES` e nova aprovação explícita do usuário para continuar, troque para `PHASE_2.md` e comece a preencher `## 6`.
16. Se o escopo crescer materialmente durante a execução, revise o plano e peça nova aprovação antes de seguir.

## Armadilhas que devem parar a etapa

- Gate 1 ainda está `NO`.
- Alguma categoria do inventário ficou implícita ou sem bloco próprio.
- O plano ainda contém placeholders do template.
- A execução começou antes do `validate-plan --phase phase1`.
- A avaliação de necessidade da Fase 2 está ausente ou não explica o estado `YES|NO`.
- `PHASE_2_NEEDED`, `Residual condition` e `Structural separation needed` estão inconsistentes.
- A Fase 2 foi iniciada com `PHASE_2_NEEDED: NO` ou sem evidência estrutural remanescente.
- A proposta já está tentando detalhar extração estrutural da Fase 2 em vez de fechar a limpeza.
- `## 6` ou `## 7` recebeu conteúdo novo antes de a Fase 1 terminar e o usuário aprovar a entrada na Fase 2.

## Exemplo: proposta de Fase 1A

```markdown
## 4. Phase 1A - Deep Remediation Proposal

### 4.2 Internal duplicates

#### Inventory item P1-INT-01
- Finding status: finding
- Location: `src/features/chat/ui/ChatContainer.tsx`
- Problem: três blocos repetem a normalização de mensagens e o cálculo de status.
- Proposed change: consolidar em uma única função interna antes da modularização.
- Files affected: `src/features/chat/ui/ChatContainer.tsx`
- Contract/import/export impact: nenhum contrato público muda nesta etapa.
- Risk: regressão em estados de loading e empty state.
- Validation: testes de render e fluxo de mensagens.
- Rollback: restaurar a função duplicada original no alvo.

### 4.6 Naming and visibility

#### Inventory item P1-NAME-01
- Finding status: finding
- Location: `src/features/chat/runtime/discovery.py`
- Problem: `_build_groups` e `_discover_entries` estão nomeados como privados, mas já são consumidos fora do arquivo e fazem parte da superfície real do módulo Python.
- Proposed change: promover os símbolos para `build_groups` e `discover_entries` já na Fase 1, migrando imports/callers necessários antes da modularização.
- Files affected: `src/features/chat/runtime/discovery.py`, `src/features/chat/runtime/service.py`
- Contract/import/export impact: atualiza imports e exports para remover o prefixo `_` dos símbolos públicos reais.
- Risk: callers indiretos podem continuar importando o nome antigo se a migração ficar incompleta.
- Validation: testes do módulo, busca por imports antigos e typecheck local.
- Rollback: restaurar os nomes anteriores e os imports associados se a promoção quebrar callers.
```

## Exemplo: execução de Fase 1B

```markdown
## 5. Phase 1B - Deep Remediation Execution Log

- PHASE_1_EXECUTED: YES
- Phase 1 execution summary: duplicações internas removidas, data label migrado para utilitário compartilhado e dois callers atualizados.
- Files changed in Phase 1: `ChatContainer.tsx`, `formatDateLabel.ts`, `ChatMessage.tsx`
- Shared utilities reused or created: reutilizado `formatDateLabel`
- Imports/exports migrated in Phase 1: export nomeado de helper interno removido
- Callers migrated in Phase 1: `ChatMessage.tsx` passou a consumir o utilitário compartilhado
- Public symbols promoted in Phase 1: `build_groups`, `discover_entries`
- Validation evidence for Phase 1: testes de chat e typecheck local
- Residual risks after Phase 1: comportamento de timezone ainda depende da fixture atual
```

## Exemplo: categoria revisada sem achado material

```markdown
### 4.5 Comment cleanup

#### Inventory item P1-COMMENT-01
- Finding status: no-finding
- Location: `src/features/chat/ui/ChatContainer.tsx`
- Problem: nenhum comentario atual esta obsoleto; a revisao encontrou apenas comentarios ainda aderentes ao fluxo.
- Proposed change: nenhuma alteracao necessaria nesta categoria nesta fase.
- Files affected: none
- Contract/import/export impact: none
- Risk: none material
- Validation: revisao manual do trecho e comparacao com o fluxo atual
- Rollback: not applicable
```

Use este padrão quando a categoria foi analisada de verdade, mas não gerou
mudança. O objetivo é tornar a ausência de alteração auditável.
