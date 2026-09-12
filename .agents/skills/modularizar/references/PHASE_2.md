# Modularizar Phase 2

Use este reference apenas para **Fase 2A** e **Fase 2B**. Entre aqui somente
quando o Gate 1 já estiver aprovado, a Fase 1B já tiver sido executada, a
avaliação pós-Fase 1 tiver marcado `PHASE_2_NEEDED: YES` com evidência de
necessidade estrutural e o usuário tiver autorizado seguir para a modularização
estrutural.

## Abrir junto nesta etapa

- `references/PLAN_TEMPLATE.md` ao atualizar `## 6` e `## 7` do plano
- `references/OUTPUT_TEMPLATE.md` ao montar `modularizar_<target-basename>-output.md`
- `.agents/skills/modularizar/scripts/modularizar_guard.sh` ao validar plano e report

## Pré-condições

- `GATE_1_APPROVED: YES`
- `PHASE_1_EXECUTED: YES`
- `PHASE_2_NEEDED: YES`
- baseline, inventário e log da Fase 1 já preenchidos no mesmo plano
- `Residual condition: size`, `complexity` ou `both`
- `Structural separation needed: YES`
- evidência de que o alvo continua materialmente grande ou complexo e ainda precisa de separação estrutural
- aprovação explícita do usuário para sair da Fase 1 e começar `## 6. Phase 2A - Modularization Proposal`

## Objetivo da etapa

1. Propor a modularização pós-limpeza sem misturar redesign prematuro com saneamento.
2. Garantir compatibilidade pelo entrypoint canônico final, nunca pelo arquivo legado.
3. Executar a extração por responsabilidade real e corrigir a fallout da remoção do legado.
4. Fechar a trilha de evidência no report final.

## Sequência operacional

01. Atualize `## 6. Phase 2A - Modularization Proposal` no mesmo `modularizar_<target-basename>.md`.
02. Preencha pelo menos estes pontos:
    - entrypoints públicos finais
    - justificativa de cada entrypoint público
    - policy de naming com `public-only`
    - entrypoint canônico de compatibilidade
    - módulos internos e suas responsabilidades
    - símbolos promovidos a públicos e justificativa
    - símbolos mantidos internos e justificativa
    - imports/exports a migrar
    - callers a migrar
    - fallout esperada após remover o legado
    - arquivos legados a remover
    - sequência unitária de extração com `P2-STEP-*`
03. Em cada `Planned step`, registre:
    - ordem de extração
    - arquivos tocados
    - arquivos extraídos
    - responsabilidade movida
    - impacto em símbolos públicos/privados
    - checkpoint de validação
    - motivo da ordem
04. Peça aprovação explícita do usuário para o Gate 2 e pare antes de extrair módulos.
05. Após a aprovação, valide com:
    - `bash .agents/skills/modularizar/scripts/modularizar_guard.sh validate-plan --phase phase2 --target <file-or-module>`
06. Execute a Fase 2B:
    - extraia módulos por responsabilidade real
    - preserve como público apenas o que continua com callers reais ou reuso planejado
    - promova a público apenas o que se tornou reutilizável
    - use o entrypoint canônico do módulo ou pacote como superfície de compatibilidade
    - remova o arquivo legado
    - corrija imports, exports, callers, entrypoints e testes quebrados pela remoção do legado
07. Atualize `## 7. Phase 2B - Modularization Execution Log`.
08. Gere `modularizar_<target-basename>-output.md` a partir de `references/OUTPUT_TEMPLATE.md`.
09. No report final, espelhe:
    - cada `Inventory item` aprovado da Fase 1 em `4.1`
    - cada `Planned step` aprovado da Fase 2 em `5.3`
10. Rode a validação final via `lint-and-validate` com o menor escopo útil para o diff.
11. Finalize com:

- `bash .agents/skills/modularizar/scripts/modularizar_guard.sh validate-report --target <file-or-module>`

## Regras que não podem ser violadas

- Arquivos extraídos não podem ter basename iniciado por `_`.
- `__init__.py` só é exceção quando é o entrypoint canônico do pacote, não um módulo extraído de responsabilidade.
- O entrypoint canônico de compatibilidade não pode apontar para o arquivo legado alvo.
- `Legacy files to remove` deve listar explicitamente o alvo legado.
- Gateway legado não é permitido.
- A fallout da remoção do legado precisa ser corrigida na própria Fase 2.
- O report final precisa registrar status, evidência e rollback por item e por passo.

## Armadilhas que devem parar a etapa

- Gate 2 ainda está `NO`.
- `PHASE_2_NEEDED` não está marcado como `YES` com evidência pós-Fase 1.
- A proposta usa `_helper.py` ou outro basename privado para módulo extraído.
- O plano mantém o arquivo legado como entrypoint canônico.
- `Legacy files to remove` não inclui o alvo original.
- A extração foi executada sem `validate-plan --phase phase2`.
- O report final virou resumo solto sem blocos por item e por passo.
- A avaliação pós-Fase 1 usa condição `none` ou `Structural separation needed: NO` para iniciar a Fase 2.

## Exemplo: proposta de Fase 2A

```markdown
## 6. Phase 2A - Modularization Proposal

### 6.1 Final module map
- Final public entrypoints: `src/features/chat/ui/ChatContainer/index.ts`
- Public entrypoint justification: `ChatPage.tsx` e `ChatPane.tsx` continuam consumindo esse path durante a migração.
- File naming policy for extracted modules: public-only; nenhum basename de arquivo extraído pode começar com `_`
- Canonical compatibility entrypoint: `src/features/chat/ui/ChatContainer/index.ts`
- Internal modules and responsibilities: `ChatContainer.tsx` coordena layout; `message-list.tsx` renderiza lista; `message-actions.ts` centraliza handlers
- Symbols promoted to public: `buildMessageGroups`
- Promotion justification: o helper passa a ser consumido por mais de um módulo de chat após a extração.
- Symbols kept internal: `resolveScrollAnchor`, `renderEmptyState`
- Why symbols stay internal: continuam acoplados a detalhes de renderização do container.

### 6.2 Import and caller migration plan
- Imports/exports to update: `ChatPage.tsx` e `ChatPane.tsx` passam a importar de `index.ts`
- Callers to migrate: `ChatPage.tsx`, `ChatPane.tsx`
- Breakages expected after legacy file removal: imports antigos de `ChatContainer.tsx` quebram até a migração dos callers
- Legacy files to remove: `src/features/chat/ui/ChatContainer.tsx`
```

## Exemplo: report de Fase 2B

```markdown
## 5. Phase 2B Report

### 5.2 Migration evidence
- Public symbols promoted: `buildMessageGroups`
- Symbols kept internal: `resolveScrollAnchor`, `renderEmptyState`
- Import/export migrations applied: callers do feature chat apontam para o novo entrypoint
- Caller migrations applied: `ChatPage.tsx`, `ChatPane.tsx`
- Breakages fixed after legacy file removal: imports antigos de `ChatContainer.tsx` foram migrados para `index.ts`

### 5.3 Step execution evidence

#### Executed step P2-STEP-01
- Step ID: P2-STEP-01
- Execution status: executed
- Files changed: `ChatContainer.tsx`, `message-list.tsx`
- Extracted module files: `src/features/chat/ui/ChatContainer/message-list.tsx`
- Summary: renderização da lista extraída para módulo dedicado
- Validation evidence: testes de render e smoke de chat
- Rollback note: reverter para a composição anterior do container
```

## Exemplo: compatibilidade por pacote sem gateway legado

```markdown
### 6.1 Final module map
- Final public entrypoints: `src/filters/dfp_itr/validators/__init__.py`
- Public entrypoint justification: o pacote exporta apenas validadores contabeis DFP/ITR
- File naming policy for extracted modules: public-only; nenhum basename de arquivo extraído pode começar com `_`
- Canonical compatibility entrypoint: `src/filters/dfp_itr/validators/__init__.py`
- Internal modules and responsibilities: `balance_equation.py`, `quarter_sum.py`, `temporal_overlap.py`
- Symbols promoted to public: none
- Promotion justification: not applicable
- Symbols kept internal: `build_risk_split_result`
- Why symbols stay internal: helper reaproveitado apenas dentro do pacote

### 6.2 Import and caller migration plan
- Imports/exports to update: callers apontam para `src.filters.dfp_itr.validators`
- Callers to migrate: imports diretos de modulo legado migram para o pacote publico
- Breakages expected after legacy file removal: imports diretos de arquivo legado deixam de resolver
- Legacy files to remove: nenhum arquivo legado concreto permanece neste exemplo
```

## Exemplo inválido: arquivo privado ou gateway legado

```markdown
### 6.1 Final module map
- Final public entrypoints: `src/features/foo/foo.py`
- File naming policy for extracted modules: permite `_helper.py` se ficar interno
- Canonical compatibility entrypoint: `src/features/foo/foo.py`

### 6.2 Import and caller migration plan
- Imports/exports to update: none
- Callers to migrate: none
- Breakages expected after legacy file removal: none
- Legacy files to remove: none

### 6.3 Step-by-step extraction sequence
#### Planned step P2-STEP-01
- Extracted module files: `src/features/foo/_helper.py`
```

Isso falha porque usa basename privado em arquivo extraído, preserva o legado
como entrypoint canônico e não registra a remoção do alvo legado.
