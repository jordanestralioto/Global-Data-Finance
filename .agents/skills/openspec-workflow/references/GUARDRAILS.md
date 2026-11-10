# GUARDRAILS

## Globais

- Os prompts do lifecycle são canônicos; execute os comandos oficiais do harness (`opsx`, `opsx-handoff`, `opsx-sync`).
- Confirme schema e estado com `opsx status`/`opsx instructions`.
- Após a criação da change, valide a proveniência com `opsx preflight --change "<name>" --json` antes de avançar nas escritas do lifecycle.
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
- `review`: gate `bundle` e auditoria dos artefatos e da fonte de decisão,
  sem editar código ou artefatos.
- `apply`: bundle verde antes de editar; ao terminar, produzir
  `evidence/gate-report.json` com o verifier repo-native (`--evidence-path`) e
  exigir o gate `opsx-handoff --mode apply <change>` verde. Completion continua
  reservado a verify/sync/archive.
- `verify`: capturar `repositoryFingerprint` com `opsx fingerprint`, gravar
  `evidence/verification-report.json` e exigir o completion gate verde.
- `sync`: `opsx-sync` aplica ADDED, MODIFIED, REMOVED e RENAMED; a segunda
  passagem `--check` deve indicar ausência de mudanças.
- `archive`: completion vermelho é hard block sem override.
- `explore`: read-only; persistência de artefato segue por `continue` ou `ff`.

## Fronteira da automação

O handoff gate verifica somente fatos determinísticos: seções, categorias de
cenário, paths, IDs, checkboxes, estado de arquivo e evidência vinculada ao
estado. Não atribua a ele correção semântica; essa prova pertence à
verificação repo-native e à revisão.
