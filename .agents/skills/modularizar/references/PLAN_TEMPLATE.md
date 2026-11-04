# Modularizar Plan Template (`modularizar_<target-basename>.md`)

Use este template para criar ou atualizar `modularizar_<target-basename>.md` na raiz do repositório.

## Sumário

- `1-3`: metadata, estado dos gates e baseline de contrato.
- `4-5`: proposta, aprovação, execução da Fase 1 e decisão sobre a Fase 2.
- `6-7`: proposta e execução da modularização estrutural, somente quando necessária.
- `8-10`: validação final, rollback e readiness.

Regra de naming:

- Prefixe o basename final do alvo com `modularizar_`.
- Preserve o case do basename.
- Exemplo: `ChatContainer.tsx` -> `modularizar_ChatContainer.md`

Fluxo:

- O agent prepara e atualiza este arquivo ao longo das duas fases.
- O usuário aprova ou pede revisão em cada gate.
- Nenhuma execução de código é permitida antes da aprovação do gate correspondente.

Comando recomendado:

- `bash .agents/skills/modularizar/scripts/modularizar_guard.sh init-plan --target <file-or-module> --task <task-name> --author developer-engineer`

> [!IMPORTANT]
>
> - Preencha todas as linhas abaixo com informação explícita. Não deixe placeholder em aberto.
> - Cada categoria do inventário da Fase 1 é obrigatória. Se não houver achado material em uma categoria, registre isso de forma explícita com a justificativa local.
> - Registre impactos em callers, imports, exports, símbolos públicos e utilitários compartilhados sempre que existirem.
> - Se o escopo mudar materialmente após qualquer aprovação, revise este plano e peça nova aprovação antes de continuar.
> - Use o formato oficial abaixo quando uma categoria foi revisada de verdade, mas não gerou achado material:
>   - `Finding status: no-finding`
>   - `Files affected: none`
>   - `Contract/import/export impact: none`
>   - `Risk: none material`
>   - `Rollback: not applicable`
>   - Em `Problem`, registre que a inspeção explícita não encontrou issue material.
>   - Em `Proposed change`, registre que não haverá code change nessa categoria nesta fase.

## 1. Metadata

- Task name:
- Date:
- Author agent:
- Target module/file:
- Branch:
- Related ticket/issue (if any):
- Workflow type: deep-cleanup-plus-modularization

## 2. Gate State Snapshot

- PLAN_FILE_EXISTS: true
- GATE_1_APPROVED: NO
- PHASE_1_EXECUTED: NO
- GATE_2_APPROVED: NO
- PHASE_2_EXECUTED: NO
- FINAL_VALIDATION_READY: NO

## 3. Contract and Migration Baseline

- Current public imports/exports:
- Callers that must be updated:
- Compatibility/migration strategy:
- Symbols that may become public:

## 4. Phase 1A - Deep Remediation Proposal

### 4.1 Target baseline

- Current responsibilities mixed in the target:
- Main pain points:
- Expected outcome after cleanup:

### 4.2 Internal duplicates

For each finding, copy the block below:

#### Inventory item P1-INT-01

- Finding status: finding/no-finding
- Location:
- Problem:
- Proposed change:
- Files affected:
- Contract/import/export impact:
- Risk:
- Validation:
- Rollback:

### 4.3 Shared utility reuse or justified new shared utility

For each finding, copy the block below:

#### Inventory item P1-SHARED-01

- Finding status: finding/no-finding
- Location:
- Existing utility or abstraction to reuse, or why none is sufficient:
- Future consumers after extraction:
- Problem:
- Proposed change:
- Files affected:
- Contract/import/export impact:
- Risk:
- Validation:
- Rollback:

### 4.4 Complexity and Big-O optimization

For each finding, copy the block below:

#### Inventory item P1-BIGO-01

- Finding status: finding/no-finding
- Location:
- Current complexity problem:
- Expected gain:
- Proposed change:
- Files affected:
- Contract/import/export impact:
- Risk:
- Validation:
- Rollback:

### 4.5 Comment cleanup

For each finding, copy the block below:

#### Inventory item P1-COMMENT-01

- Finding status: finding/no-finding
- Location:
- Problem:
- Proposed change:
- Files affected:
- Contract/import/export impact:
- Risk:
- Validation:
- Rollback:

### 4.6 Naming and visibility

For each finding, copy the block below:

> Para Python, registre explicitamente aqui símbolos privados com prefixo `_`
> que precisem virar públicos na Fase 1. Não deixe essa promoção implícita
> nem adie para a Fase 2 quando a superfície real de uso já estiver clara.

#### Inventory item P1-NAME-01

- Finding status: finding/no-finding
- Location:
- Problem:
- Proposed change:
- Files affected:
- Contract/import/export impact:
- Risk:
- Validation:
- Rollback:

### 4.7 Caller and contract migrations

For each finding, copy the block below:

#### Inventory item P1-CALLER-01

- Finding status: finding/no-finding
- Location:
- Problem:
- Proposed change:
- Files affected:
- Contract/import/export impact:
- Risk:
- Validation:
- Rollback:

### 4.8 Phase 1 change summary

- What will change in the target:
- What will change outside the target:
- Public symbol changes expected:
- Validation gates for Phase 1:

### 4.9 Gate 1 approval

- GATE_1_APPROVED: NO
- Approved at:
- User notes:

## 5. Phase 1B - Deep Remediation Execution Log

- PHASE_1_EXECUTED: NO
- Phase 1 execution summary:
- Files changed in Phase 1:
- Shared utilities reused or created:
- Imports/exports migrated in Phase 1:
- Callers migrated in Phase 1:
- Public symbols promoted in Phase 1:
- Validation evidence for Phase 1:
- Residual risks after Phase 1:

### 5.1 Phase 2 necessity assessment

- PHASE_2_NEEDED: NO
- Residual condition: none|size|complexity|both
- Structural separation needed: NO
- Post-Phase 1 size or complexity evidence:
- Residual structural problem:
- Phase 2 necessity rationale:

> [!IMPORTANT]
>
> Marque `PHASE_2_NEEDED: YES` somente quando o alvo ainda tiver tamanho ou
> complexidade material e existir uma necessidade estrutural concreta de separar
> responsabilidades. Tamanho isolado ou redistribuição mecânica não bastam.
> Para `YES`, use `Residual condition: size`, `complexity` ou `both` e
> `Structural separation needed: YES`. Para `NO`, use `Structural separation needed: NO`, inclusive quando ainda houver tamanho ou complexidade, mas o alvo
> estiver coeso.
> Quando a decisão for `NO`, registre a justificativa e mantenha `## 6` e `## 7`
> sem conteúdo novo.

> [!IMPORTANT]
>
> Não preencha `## 6` nem `## 7` durante a Fase 1. Essas seções só devem ser
> atualizadas depois de `GATE_1_APPROVED: YES`, `PHASE_1_EXECUTED: YES`,
> `PHASE_2_NEEDED: YES` e nova aprovação explícita do usuário para iniciar a Fase 2.

## 6. Phase 2A - Modularization Proposal

### 6.1 Final module map

- Final public entrypoints:
- Public entrypoint justification:
- File naming policy for extracted modules:
- Canonical compatibility entrypoint:
- Internal modules and responsibilities:
- Symbols promoted to public:
- Promotion justification:
- Symbols kept internal:
- Why symbols stay internal:

### 6.2 Import and caller migration plan

- Imports/exports to update:
- Callers to migrate:
- Breakages expected after legacy file removal:
- Legacy files to remove:

### 6.3 Step-by-step extraction sequence

#### Planned step P2-STEP-01

- Extraction order:
- Files touched:
- Extracted module files:
- Responsibility moved:
- Public/private symbol impact:
- Validation checkpoint:
- Why this step comes now:

#### Planned step P2-STEP-02

- Extraction order:
- Files touched:
- Extracted module files:
- Responsibility moved:
- Public/private symbol impact:
- Validation checkpoint:
- Why this step comes now:

### 6.4 Gate 2 approval

- GATE_2_APPROVED: NO
- Approved at:
- User notes:

## 7. Phase 2B - Modularization Execution Log

- PHASE_2_EXECUTED: NO
- Phase 2 execution summary:
- Files changed in Phase 2:
- Modules extracted:
- Canonical compatibility entrypoint used:
- Imports/exports migrated in Phase 2:
- Callers migrated in Phase 2:
- Breakages fixed after legacy file removal:
- Public symbols promoted in Phase 2:
- Legacy files removed:
- Validation evidence for Phase 2:
- Residual risks after Phase 2:

## 8. Final Validation Plan

- Lint/static analysis:
- Type/static contracts:
- Unit/integration tests:
- Build/package checks:
- Repo-native validation command:

## 9. Rollback Plan

- Phase 1 rollback:
- Phase 2 rollback:
- Full abort trigger:

## 10. Final Readiness

- FINAL_VALIDATION_READY: NO
- Final report file path: modularizar\_<target-basename>-output.md
- Phase 1-only lock command: `bash .agents/skills/modularizar/scripts/modularizar_guard.sh validate-plan --phase phase1-complete --target <file-or-module>`
- Final lock command (Phase 2 only): `bash .agents/skills/modularizar/scripts/modularizar_guard.sh validate-report --target <file-or-module>`
