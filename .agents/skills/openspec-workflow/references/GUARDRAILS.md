# GUARDRAILS

## Globais

- Os prompts do lifecycle são canônicos; execute os comandos oficiais do harness (`opsx`, `opsx-handoff`).
- Confirme schema e estado com `opsx status`/`opsx instructions`.
- O gate suporta apenas `spec-driven`; schema não suportado falha.
- Artefatos OpenSpec são integralmente em inglês e têm um desenvolvedor júnior
  sem contexto prévio como leitor.
- Exceção legada existe somente no allowlist `openspec/handoff.json`, sempre com
  motivo e gatilho de remoção. `.handoff-exempt` não concede bypass, e a
  allowlist nunca isenta o completion gate.

## Lifecycle obrigatório

- `continue`: exatamente um artefato, seguido de
  `opsx-handoff --mode artifact --artifact <id> <change>`.
- `ff`: bundle completo e `opsx-handoff --mode bundle <change>` verde.
- `apply`: bundle verde antes de editar; ao terminar, produzir
  `evidence/gate-report.json` com o verifier repo-native (`--evidence-path`) e
  exigir o gate `opsx-handoff --mode apply <change>` verde. Completion continua
  reservado a verify/sync/archive.
- `verify`: combinar análise semântica com o completion gate.
- `sync`: somente o owner programatico aplica ADDED, MODIFIED, REMOVED e
  RENAMED; a segunda passagem `--check` deve ser vazia.
- `archive`: completion vermelho é hard block sem override.
- `explore`: read-only; persistência de artefato segue por `continue` ou `ff`.

## Fronteira da automação

O handoff gate verifica somente fatos determinísticos: seções, categorias de
cenário, paths, IDs, checkboxes, estado de arquivo e evidência vinculada ao
estado. Não atribua a ele correção semântica; essa prova pertence à
verificação repo-native e à revisão.
