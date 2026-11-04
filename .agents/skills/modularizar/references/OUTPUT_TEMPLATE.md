# Modularizar Output Template

Use este template para reportar a execução das duas fases e a validação final.

> [!IMPORTANT]
>
> - Registre evidência suficiente para provar o que foi executado, o que mudou em callers/imports/exports e como o comportamento foi validado.
> - Se algum gate falhar, pare o fluxo e registre o bloqueio com clareza.
> - Cada `Inventory item` aprovado em `Phase 1A` deve aparecer exatamente uma vez em `4.1`.
> - Cada `Planned step` aprovado em `Phase 2A` deve aparecer exatamente uma vez em `5.3`.
> - Use o formato oficial abaixo quando um item aprovado terminou como revisão sem mudança de código:
>   - `Execution status: no-change`
>   - `Files changed: none`
>   - `Contract/import/export impact: none`
>   - `Caller migration impact: none`
>   - `Public symbol impact: none`
>   - `Rollback note: not applicable`
>   - Em `Summary`, registre que o item foi rechecado e não exigiu mudança de código.

## 1. Execution Metadata

- Task name:
- Date:
- Author agent:
- Target module/file:
- Branch:
- Plan file path:
- Report file path: modularizar\_<target-basename>-output.md

## 2. Gate Summary

- GATE_1_APPROVED: pass/fail
- PHASE_1_EXECUTED: pass/fail
- GATE_2_APPROVED: pass/fail
- PHASE_2_EXECUTED: pass/fail
- FINAL_VALIDATION: pass/fail

## 3. Approval Evidence

- Gate 1 approval evidence:
- Gate 2 approval evidence:
- Scope changes after approval:

## 4. Phase 1B Report

### 4.1 Remediation items executed

Para cada item aprovado na Fase 1A, crie um bloco próprio:

#### Executed item P1-INT-01

- Inventory item ID:
- Execution status: executed/no-change
- Files changed:
- Summary:
- Contract/import/export impact:
- Caller migration impact:
- Public symbol impact:
- Validation evidence:
- Rollback note:

### 4.2 Shared utility and deduplication evidence

- Existing shared utilities reused:
- New shared utilities created:
- Callers migrated:

### 4.3 Complexity, comments and naming evidence

- Complexity or Big-O optimizations applied:
- Comment cleanup applied:
- Naming and visibility changes applied:

### 4.4 Gate decision

- PHASE_1_EXECUTED: pass/fail

## 5. Phase 2B Report

### 5.1 Module map applied

- Public entrypoints:
- Extracted module files:
- Internal modules:
- Canonical compatibility entrypoint used:
- Legacy files removed:

### 5.2 Migration evidence

- Public symbols promoted:
- Symbols kept internal:
- Import/export migrations applied:
- Caller migrations applied:
- Breakages fixed after legacy file removal:

### 5.3 Step execution evidence

Para cada passo aprovado na Fase 2A, crie um bloco próprio:

#### Executed step P2-STEP-01

- Step ID:
- Execution status: executed/adjusted
- Files changed:
- Extracted module files:
- Summary:
- Validation evidence:
- Rollback note:

### 5.4 Gate decision

- PHASE_2_EXECUTED: pass/fail

## 6. Final Validation

- Lint/static analysis:
- Type/static contracts:
- Unit/integration tests:
- Build/package checks:
- Repo-native validation command:
- Key output summary:
- FINAL_VALIDATION: pass/fail

## 7. Final Verdict

- Refactor status: complete/incomplete
- Recommended next action:
- Final lock command: `bash .agents/skills/modularizar/scripts/modularizar_guard.sh validate-report --target <file-or-module>`
