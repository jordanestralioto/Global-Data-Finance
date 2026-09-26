# Cross-Stack Hook Workflow Evals

> Summary: Three realistic prompts and binary assertions for checking whether
> an agent applies the portable method instead of copying one stack's policy.

Run each scenario in a disposable Git checkout. Inspect the config, installed
hook path, commands invoked and exit codes; a plausible final explanation is
not evidence that a hook executes. Use fixed local tool versions and fixtures
with no real credentials.

## Scenario 1: Python project with an existing runner

**Prompt:** "Este projeto já usa pre-commit, uv, Ruff e pytest. Distribua testes
rápidos e completos entre commit e push, audite dependências no push e mantenha
os checks de commit existentes."

**Fixture:** Existing `.pre-commit-config.yaml` with a Ruff hook, a locked
`uv.lock`, distinct fast/full test commands, and a pinned audit command with
local fixtures for vulnerability and service-unavailable results. Include a
partially staged Python file; use no live advisory service in this eval.

**Assertions:**

- [ ] Existing hook IDs and scopes remain present.
- [ ] The config installs pre-commit and pre-push; the new test hook declares
  `stages: [pre-push]` and runs the project's locked full-suite command.
- [ ] The fast tier runs on commit and the full tier runs on push; a failing
  test blocks its configured stage even if no test file changed.
- [ ] The audit runs read-only on pre-push, identifies the resolved graph and
  advisory source, and blocks a policy-matching vulnerability. A service outage
  is reported as unavailable, never as a clean audit.
- [ ] The report distinguishes the staged commit from an unstaged working-tree
  edit and records which snapshot the tests inspected.

## Scenario 2: Node monorepo with Lefthook and no Python runtime

**Prompt:** "Nosso monorepo pnpm já usa Lefthook. Configure lint rápido no
commit, testes e auditoria de dependências no push sem exigir Python nas
máquinas da equipe."

**Fixture:** Two workspaces, a shared lockfile, package scripts for lint,
test and a read-only audit, and no `python` command on the test `PATH`.

**Assertions:**

- [ ] Lefthook remains the runner; no Python helper is copied or invoked.
- [ ] Workspace scopes and the authoritative root lockfile are identified.
- [ ] Pre-commit and pre-push commands use pinned project dependencies.
- [ ] A lint violation blocks commit; a failing test blocks push.
- [ ] The audit uses the project's pinned tool and covers the declared
  workspace dependency graph without changing manifests or the lockfile.
- [ ] Missing local tools produce an explicit failure or an honest incomplete
  setup report, never a false `PASS`.

## Scenario 3: Go project without a hook runner

**Prompt:** "Crie hooks locais simples para este projeto Go. Quero formato e
verificação rápida no commit, testes completos no push."

**Fixture:** `go.mod`, tracked Go packages, a known `go test ./...` command,
and no installed runner or architecture checker.

**Assertions:**

- [ ] The agent chooses and pins an installable runner using project context;
  it does not infer Python helpers or a second package manager.
- [ ] The configured pre-push hook is installed and a failing `go test ./...`
  blocks push.
- [ ] The circular-dependency slot is not claimed as covered by an absent
  graph checker; any selected compiler check names its scope.
- [ ] The final gate matrix records stage, command, snapshot, runtime, cost
  and coverage for every selected gate.

## Baseline replacement check

For any scenario with legacy findings, seed baseline `{A, B}` and current
findings `{B, C}`. The gate must fail for new finding `C`; a count-only pass
fails the eval.
