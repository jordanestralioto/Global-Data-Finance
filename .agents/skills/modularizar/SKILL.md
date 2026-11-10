---
name: modularizar
description: >-
  Use para sanear god files, god components e módulos monolíticos com migração
  auditável. Ative quando o usuário pedir "quebra esse arquivo gigante", "esse
  componente virou monstro", "separa em módulos", "extrai utilitários" ou invocar
  `[$modularizar]`. Aplique quando imports, exports, callers e contratos precisarem
  ser rastreados. Não use para ajustes locais simples, pequenos renames, funções
  isoladas grandes ou decisões de arquitetura sem alvo delimitado; nesse caso,
  prefira `architecture`.
---

# Modularizar

## Engineering constraints

- Clean up before extraction: remove duplication, reuse existing abstractions,
  clarify naming and comments, and address demonstrated complexity problems.
  Splitting first spreads the same problems across more files.
- Split by responsibility. Remaining size alone does not justify extraction;
  stop after cleanup when the target is cohesive.
- During cleanup, promote Python names whose actual public use contradicts
  their private naming, and migrate their callers. Keep implementation details
  internal; sharing within a package does not automatically create a public API.
- This workflow requires public basenames for extracted responsibility modules.
  A canonical `__init__.py` is allowed with explicit exports and no implementation.
- Preserve the supported import through the final canonical entrypoint. Remove
  the legacy file during extraction and fix callers, exports and tests together;
  do not leave a forwarding shim.
- Respect the consumer's validation and line-limit policies. The helper defaults
  to 400 lines for each production file; use the consumer's limit when different.

## Procedimento

1. Read the target, its callers and local instructions. Establish the supported
   interface and baseline checks before proposing changes.
2. Create or reuse **one** short refactoring record in a consumer-owned evidence
   directory outside generated projections. Choose its path explicitly using
   repository conventions; do not drop new files in the repository root.
   Use `references/PLAN_TEMPLATE.md` through the initializer below if useful.
3. Record the existing authorization for the work. An explicit request covering
   cleanup and extraction authorizes both phases within that scope. Ask before
   execution only when authorization is missing, scope expands materially, or
   the user requested approval at each phase. Do not invent approval evidence.
4. Follow `references/PHASE_1.md` for diagnosis and cleanup. Record only material
   findings; an empty category needs one short reason, not a sentinel block.
5. After cleanup and its checks, record `PHASE_2_NEEDED: YES` or `NO`, supported
   by remaining responsibilities and complexity. If `NO`, close the same record
   with validation and remaining risks. Do not prepare extraction paperwork.
6. Only for `YES`, read `references/PHASE_2.md`, map responsibilities and migrate
   the approved scope. Update the original record with outcomes and evidence;
   do not create a second report that repeats its plan.
7. Run the structural checker after extraction and the consumer's native checks.
   Inspect the diff for undeclared modules, stale callers and behavior changes.
   Report exactly which checks ran and what remains unverified.

## Helper

The standard-library-only helper works from the consumer's working directory,
with Git root discovery and a cwd fallback. `--repo` explicitly selects a root.
Assets resolve beside the script, so a projected skill needs no harness imports.

```bash
python .agents/skills/modularizar/scripts/check_modularization.py init \
  --target src/orders.py --record docs/refactors/orders.md

python .agents/skills/modularizar/scripts/check_modularization.py check \
  --target src/orders.py --entrypoint src/orders/__init__.py \
  --module src/orders
```

`--record` is required and an existing file is never overwritten. For Python,
`--python-root src --retired-import old_orders` adds a static import scan. List
only retired import names, not an import intentionally preserved by the new
package. See `references/PHASE_2.md` for coverage and exit codes.

## Exemplos

### Authorized cleanup and extraction

**Input:** "Modulariza esse service, ajusta os callers e pode executar tudo."
**Expected:** record this authorization, clean up, reassess structural need, then
extract if justified. Update one record without repeated permission requests.

### Cohesive after cleanup

**Input:** "Depois da limpeza ficou coeso; não extraia só para distribuir linhas."
**Expected:** record `PHASE_2_NEEDED: NO`, checks and remaining risks; finish Phase 1.

### Caso negativo

**Input:** "Desenha a arquitetura nova do backend sem um alvo definido."
**Reason:** use `architecture`; this skill needs a bounded refactoring target.

## Evals de trigger

Should trigger:

- "quebra esse arquivo gigante em módulos"
- "modularisa esse arquivozao e reaproveita os utils que ja existem"
- "extrai utilitários desse monólito e mantém o import público pelo pacote"
- "[$modularizar] src/service.py"

Não deve acionar:

- "só renomeia essa função"
- "mede o gargalo dessa query antes de mudar código"
- "define a arquitetura dessa feature nova"
- "organiza a legibilidade sem extrair módulos nem migrar contratos"

## Evals de workflow

These are proposed behavioral checks. Run in disposable consumers and inspect
transcripts and changed files before claiming effectiveness.

### Full implementation already authorized

Request: "Modulariza esse service, ajusta os callers e pode executar tudo."

- [ ] References the existing authorization without asking again.
- [ ] Uses one record outside generated projections and the repository root.
- [ ] Cleans up and validates before deciding whether extraction is necessary.
- [ ] Removes the legacy file, migrates callers and checks actual destinations.
- [ ] Updates outcomes in place without a duplicate report.

### Cleanup is sufficient

Request: "Só extrai se ainda houver responsabilidades misturadas após a limpeza."

- [ ] Records `PHASE_2_NEEDED: NO` with supporting evidence when cleanup suffices.
- [ ] Finishes with native checks and risks, without mechanical splitting.

### User requests approval first

Request: "Me mostra o plano; não altera código antes de eu aprovar."

- [ ] Presents a concrete proposal and waits before source edits.
- [ ] References the approval before executing the authorized scope.

### Completion claim contradicts code

Fixture: the record claims success but a legacy file or invalid module remains.

- [ ] Runs the helper on actual paths and reports the structural failure.
- [ ] Reports native checks separately, including unsupported or untested behavior.
- [ ] Preserves canonical package imports rather than listing them as retired.
