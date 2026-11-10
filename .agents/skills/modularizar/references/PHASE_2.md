# Phase 2: extract responsibilities and migrate callers

Enter after Phase 1 checks and `PHASE_2_NEEDED: YES`. Confirm that the existing
authorization covers extraction; honor any user-requested approval boundary.

## Plan and execute in the same record

1. Map each remaining responsibility to its destination and justify the boundary.
   Identify the canonical public entrypoint, symbols staying internal and caller
   migrations. List the legacy file to remove and the extraction order.
2. Extract one responsibility at a time with useful validation checkpoints.
   Reuse existing modules where appropriate; avoid new re-export-only wrappers.
3. Use public basenames for extracted modules. A package's `__init__.py` can
   contain its docstring, explicit imports and a literal `__all__` export list,
   but no implementation or wildcard imports.
4. Remove the legacy target and fix its imports, exports, callers and tests.
   A supported import may survive through a canonical package at the same import
   name. List only genuinely retired names for import scanning.
5. Update the original findings and extraction map with results, commands, exit
   codes and remaining risks. Inspect the final diff for undeclared extractions
   and indirect consumers. Run the consumer's required checks before closing.

## Structural verification

```bash
python .agents/skills/modularizar/scripts/check_modularization.py check \
  --target src/legacy_orders.py --entrypoint src/orders/__init__.py \
  --module src/orders --python-root src --retired-import legacy_orders
```

- `--module` accepts a file or source-only directory and can be repeated. Pass
  every extracted destination, including reused files that received code. A
  directory checks its files recursively, skipping caches, environments, vendor
  trees and generated harness projections. Select individual files for a tree
  containing binary assets or unrelated documents.
- The checker verifies the legacy path is absent, the entrypoint and selected
  modules exist, public basenames, line limits, Python syntax and initializer
  structure. `--max-lines` defaults to 400; match the consumer's production policy.
- `--retired-import` can be repeated. Static Python imports are resolved relative
  to `--python-root` (default: repository root). Choose the actual Python source
  root, include caller directories in that scan, and run additional scans when
  the consumer has multiple source roots.
- The import scan covers `import`, `from ... import ...` and relative imports.
  It ignores comments and ordinary strings. Dynamic imports, runtime loading,
  other languages and consumers outside the selected source root require native
  tooling and review. Parse or read errors fail the check instead of disappearing.
- No command parses Markdown approvals or certifies behavior. A structural PASS
  covers only the listed paths and selected static checks. It does not establish
  a complete inventory of the diff or substitute for tests, typecheck and build.

Output is JSON. Exit `0` means selected checks passed, `1` means structural
violations, and `2` means invalid input or an operational error. `init` requires
an explicit `--record` path inside the consumer and refuses overwrites. It works
without Git and before the first commit; the template comes from the skill.

## Existing records

The old Bash Markdown guard and separate plan/output templates are retired.
Retain old records as historical evidence; continue active work in one record
and invoke the structural checker with actual paths. No compatibility shim or
bulk rewrite of consumer documents is needed.
