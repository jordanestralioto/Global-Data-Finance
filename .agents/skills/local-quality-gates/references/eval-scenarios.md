# Cross-Stack Hook Workflow Evals

> Summary: Three realistic prompts and binary assertions for checking whether
> an agent applies the portable method instead of copying one stack's policy.

Run each scenario in a disposable Git checkout. Inspect the config, installed
hook path, commands invoked and exit codes; a plausible final explanation is
not evidence that a hook executes. Use fixed local tool versions and fixtures
with no real credentials.

Share the prompts before execution. Retain the agent's application transcript,
configuration diff, tool versions, snapshot identities, commands, diagnostics,
native and normalized exit codes, timings, and binary assertion results.
Document/template tests and manually prepared analyzer probes are separate
evidence; neither alone proves that the workflow configured an effective hook.
Apply [dead-code-policy.md](dead-code-policy.md) when extending the three
scenarios below. Exercise actual `git commit` and `git push` to a local bare
remote for installed-stage evidence. Keep tool provisioning outside hooks.

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

**Dead-code extension prompt:** "Preserve our existing pre-commit and Ruff
hooks. Enforce the selected unused-code policy, prove staged enforcement, and
distinguish local lint from broader analysis."

Provision a pinned broader analyzer alongside Ruff. Include a normal consumer,
a callback with a documented registration contract and specific reviewed
exception, and a compatibility alias used only by tests. Do not interpret
Vulture confidence as a probability or claim precise graph construction.

- [ ] Ruff passes a fixture whose unused definition the broader real analyzer
  reports; a selected reviewed finding blocks the configured stage.
- [ ] Removing the last consumer triggers analysis with the definition unchanged.
- [ ] An invalid staged snapshot remains blocked with a valid unstaged correction
  or an untracked consumer; relevant configuration divergence also blocks.
- [ ] A legitimate consumer passes; the callback retention names its contract,
  and the test-only alias receives an explicit review disposition.
- [ ] Native invalid-input/argument results and missing tools produce `ERROR`;
  analyzer findings remain distinct from infrastructure failures.
- [ ] Successful analysis preserves source, index, manifests, and lockfiles.

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

**Dead-code extension prompt:** "Keep Lefthook and our workspace dependency
contract. Detect unused files and exports across packages without Python,
and distinguish production consumers from test-only references."

Provision pinned Knip and Lefthook. Declare real production entry points and
workspace consumers; do not mark every file as an entry to hide findings.

- [ ] A cross-workspace production consumer is retained and a real unused file
  or internal export blocks the configured stage.
- [ ] Default and production runs use recorded input scopes; a test-only alias
  passes reference discovery in default mode but requires review in production.
- [ ] Last-consumer deletion, invalid staged/valid unstaged contents, untracked
  consumers, and entry/configuration changes cannot yield false staged coverage.
- [ ] Installed commit/push stages have actual accepted and blocked cases;
  analysis is read-only and no Python helper is copied or invoked.

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

**Dead-code extension prompt:** "Create simple local hooks with our native Go
tools. Enforce the requested dead-code capabilities and explicitly report
dimensions for which no adequate analyzer is available."

Preserve the runner-selection and Go-test assertions above. Request a dimension
that the provisioned native compiler cannot establish, such as obsolete external
compatibility contracts. Do not pretend a simulated analyzer covers it.

- [ ] The requested unavailable automatic capability is `UNSUPPORTED` with
  explicit setup requirements; other gates still execute and block violations.
- [ ] The skill evaluation passes for honest reporting while requested consumer
  enforcement remains incomplete. No automatic scanner coverage is invented.
- [ ] Each of the seven capabilities has its own coverage status and rationale;
  pending mandatory review is not an approved exception.

## Baseline replacement check

For any scenario with legacy findings, seed baseline `{A, B}` and current
findings `{B, C}`. The gate must fail for new finding `C`; a count-only pass
fails the eval.

Use real analyzer findings for a selected baseline policy. Freeze stable
identities, reject new `C`, and confirm analysis does not expand the baseline.
Simulated failures may test infrastructure handling only; label their scope.

## Existing Regression Assertions

Preserve these assertions when moving details out of `SKILL.md`:

- [ ] Diff sanity returns `ERROR` code 2 on Git failure or outside a repository.
- [ ] Compiler/linter suppression markers in executable/configuration formats
  fail with code 1 even with a reason; only declared documentation formats
  permit non-executable citations. Rule-specific noqa and allow-bypass comments
  do not authorize executable suppressions.
- [ ] A TODO throw remains blocked even with a debug comment.
- [ ] Test integrity blocks focused tests without exception, unjustified skips,
  and test-file deletions without the staged deletion policy.
- [ ] Lockfile parity recognizes workspace membership, manifests without
  dependencies, and Bun locks; it does not promise lockfile content coherence.
- [ ] Native lockfile confirmation rejects relevant working-tree/index
  divergence, reports missing tools as `ERROR` 2, and nonzero checks as `FAIL` 1.
- [ ] Lockfile validation, environment setup, and dependency updates remain
  distinct; no mutating updater/sync is inferred as a pre-commit gate.
- [ ] A stack without a native read-only coherence check retains staged parity
  and reports its limitation. `go mod verify` is not manifest/lock coherence.
- [ ] Requested update automation belongs to an explicit script/job/PR outside
  the hook and receives resolution tests and auditing.
- [ ] `[DEPENDENCY_AUDIT]` records graph, advisory policy, and unavailability;
  absence of consultation is never a clean audit.
- [ ] `[TESTS_FAST]` does not replace `[TESTS_FULL]`; evidence distinguishes
  affected tests, complete suites, and their snapshots.
- [ ] Required `[CIRCULAR_DEPENDENCIES]` blocks new cycles; missing coverage is
  `UNSUPPORTED`, not `PASS`, and legacy cycles use finding identities.
- [ ] Structural `[LINTER]` reports every selected dimension's native rule,
  metric, threshold, scope, and coverage status. Cyclomatic and cognitive
  complexity remain distinct and unsupported blocking coverage is incomplete.
- [ ] `[FILE_LINES]` selects the published tool only with compatible limits,
  classifications, exclusions, and runtime, and names the actual snapshot.
- [ ] Structural configuration never uses a generic diff regex, counts physical
  lines as executable statements, or enforces a blanket single-exit rule.
- [ ] Broad catches remain limited to explicit boundaries with a narrow scope,
  defined handling, and preserved cause.
- [ ] Assertion vacuum and tautologies remain under `[TEST_INTEGRITY]` and
  `testing-patterns`, not `[LINTER]`.
- [ ] Both templates retain the pre-push scaffold and require selection,
  replacement, installation, and actual failure testing of the selected stage.
- [ ] Existing Python, Node, and Go scenarios record stage, snapshot, runtime,
  cost, and coverage and prove blocking for every configured stage.
- [ ] Baseline replacement `{A, B}` with `{B, C}` fails for new finding `C`.
