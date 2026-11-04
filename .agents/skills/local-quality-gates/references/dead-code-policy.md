# Dead Code and Obsolete Compatibility Policy

> Summary: Assess each capability separately, enforce the selected project
> policy, and distinguish analyzer results from contract review.

## 1. Capability Report

Every gate setup or review must assess `[DEAD_CODE]`, even when no new command
is selected. Inspect actual enabled rules; a generic lint command is not proof
of complete coverage. Record these seven capabilities individually:

| Capability                                             | Required assessment                                                                                       |
| ------------------------------------------------------ | --------------------------------------------------------------------------------------------------------- |
| Unused imports and local variables                     | Name native rules, enabled configuration, and file scope.                                                 |
| Unused functions, classes, and methods                 | Name analyzer support, dynamic-reference limits, and name/scope limitations.                              |
| Unused modules and files                               | Identify application entry points, project inputs, dependency graph support, and cross-package consumers. |
| Unused exports                                         | Separate internal exports from supported public APIs and external consumers.                              |
| Unreachable statements                                 | Name parser or compiler rules and effective diagnostic severity.                                          |
| Production code referenced only by tests               | Compare production and test analysis where supported; classify the difference as a review candidate.      |
| Obsolete aliases, wrappers, and compatibility branches | Review consumers and contracts; a reference does not establish continued necessity.                       |

For each capability record `status`, command/version or review control, rules,
analysis inputs and exclusions, entry points, production/test scope, snapshot,
stage, observed duration, blocking policy, limitations, and justification.

- `ENABLED`: an automatic rule is configured for its declared scope and its
  enforcement has been exercised.
- `DELEGATED`: identify the existing gate, its equivalent property, snapshot,
  and enforcement evidence. Another lint pass is insufficient.
- `MANUAL`: identify an explicit review control and residual automatic gap.
- `UNSUPPORTED`: requested automatic coverage has no adequate available tool;
  leave that requested gate incomplete and specify setup requirements.

Coverage statuses describe capabilities. `PASS`, `FAIL`, `ERROR`, and `SKIP`
describe executions. A `PASS` on enabled capabilities does not verify manual
or unsupported capabilities. When the user or repository prohibits unused
code, automatic enforcement is required for the selected blocking rules;
only `ENABLED` or equivalent `DELEGATED` coverage satisfies that requirement.
Manual contract review remains necessary for dimensions tools cannot prove.

## 2. Tool Selection

1. Inspect configured commands, enabled rules, installed analyzers, pinned
   versions, dependency contracts, and the existing runner.
2. Reuse rules that actually provide each requested capability. Record gaps.
3. Consult official documentation for uncovered dimensions and candidate tools;
   verify the behavior of the pinned version, not just the current website.
4. Adopt any necessary additional tool through explicit project setup outside
   the hook. Provision and pin it before execution; preserve other gates.
5. Report unavailable enforcement as `UNSUPPORTED`. Never substitute an
   unrelated successful check or infer permission to add a runtime.

These candidates are examples, not required harness dependencies:

| Stack                 | Candidate and limits                                                                                                                                                                                                                                                                                                                                                                                 |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Python                | Reuse local lint rules such as Ruff F401/F841. [Vulture](https://github.com/jendrikseipp/vulture) can find broader candidates and unreachable statements, but compares names while ignoring scopes. It can miss dead code and report dynamic uses as unused. Its confidence threshold is a category heuristic, not a calibrated probability of correctness or evidence of project-wide reachability. |
| JavaScript/TypeScript | [Knip](https://knip.dev/features/production-mode) can analyze files and exports with declared entries and workspaces. Default analysis includes tests. Production analysis has a different scope and does not replace the default run; inspect the actual entries and project inputs for both.                                                                                                       |
| Go                    | Reuse configured [Staticcheck](https://staticcheck.dev/docs/running-staticcheck/cli/) rules, including U1000 where appropriate. Record package patterns, build tags, exported-API limits, and whether tests participate; do not infer production coverage from a test-inclusive run.                                                                                                                 |
| Rust                  | [Compiler unused-code diagnostics](https://doc.rust-lang.org/rustc/lints/listing/warn-by-default.html#dead-code) cover documented scopes; `dead_code` targets unused unexported items and warns by default. Configure selected blocking lints as errors under project policy. Record features, targets, test participation, public-API gaps, and side-effect limitations.                            |

Analyzing the full input corpus does not imply that an analyzer constructs an
accurate dependency graph. Report graph capability separately, especially for
name-based analysis, dynamic imports, reflection, and independently built targets.

## 3. Graph, Snapshot, and Invocation

Declare the complete project or workspace scope, including cross-package
consumers. Resolve callbacks, plugins, generated inputs, CLI entry points,
package exports, and external consumers through configuration or review.
Avoid declaring every file an entry point merely to silence findings.

Run the declared scope when deletions remove the last consumer, even if the
definition is unchanged. Include changes to entry points, analyzer configuration,
manifests, workspace definitions, generated-input contracts, and exceptions.
Changed filenames alone cannot establish reachability. The pre-commit scaffold
uses `pass_filenames: false` and `always_run: true`; the Lefthook scaffold does
not use `{staged_files}` for this gate.

Required commit enforcement must analyze the staged snapshot or reject execution
when relevant analysis inputs differ from the index. A working-tree result must
be reported as partial coverage and cannot satisfy a staged enforcement
requirement. Verify the runner's isolation using an invalid staged snapshot
with a valid unstaged correction. Also exercise an untracked consumer: it must
not make a staged definition appear used. Account for untracked inputs and
generated artifacts even when the runner hides unstaged tracked changes.

Use runner-provided isolation, an isolated index export with provisioned tools,
or a read-only divergence check that rejects mismatched inputs. Do not perform
destructive checkout/stash operations in a consumer to obtain this guarantee.
Protect runner configuration and adapter bootstrap inputs loaded from the
working tree before they select or execute a gate. Exporting analyzer sources
alone does not protect an unstaged change that bypasses the invocation itself.
For pre-push, analyze the pushed commit/ref snapshot or explicitly report partial
working-tree coverage when it differs. A staged-diff helper does not verify push.

Measure latency. Place the gate in pre-commit when practical; choose pre-push
or equivalent delegated enforcement when cost and the project contract justify
it. Configure the selected stage and prove its effective installed hook.

## 4. Findings, Review, and Exceptions

Each diagnostic or enriched report must identify file, symbol or rule, reason,
analyzed scope, and reproduction command; include a line when applicable.

1. Proven violations of selected blocking rules fail the configured stage.
2. Ambiguous public APIs, callbacks, dynamic references, and test-only consumers
   require an explicit review disposition. Record the finding identity, retained
   consumer or accepted contract, rationale, reviewer/control, and the condition
   that requires reconsideration; otherwise identify the removal needed.
3. Pending required review leaves acceptance or gate setup incomplete under the
   project contract. It cannot be silently recorded as an approved exception.
4. An export or test reference alone does not justify retaining an obsolete
   compatibility API. Review deprecation commitments, supported versions,
   external consumers, migration completion, and the removal criteria. An
   accepted public contract can justify retention without an internal caller.
5. Keep exceptions specific and reviewed. Reassess them when the consumer or
   contract changes. Broad exclusions, name globs, or fabricated references
   must not conceal a requested capability. Preserve strict-profile bans;
   do not recommend executable suppressions forbidden by project policy.
6. Historical baselines require explicit project policy and stable finding
   identities, such as path, qualified symbol, and rule. A baseline acknowledges
   debt; it does not prove absence of dead code. Reject `current - baseline`
   additions: `{A, B}` becoming `{B, C}` must fail for `C`. Review baseline
   changes separately; line numbers alone are not stable identities.
7. Remove code only in a reviewed application change. Dead-code hooks run
   read-only: no installation, dependency updates, automatic exclusions,
   baseline expansion, or code deletion during execution. Cache/build effects
   require a declared contract and must not mutate source, index, manifests,
   lockfiles, configuration, or exception policy.

## 5. Native Outcomes and Evidence

Interpret documented native exit codes and diagnostic severity before mapping
to the skill outcomes. Record both `native_exit_code` and `outcome`; runner
aggregate exit codes do not replace the analyzer's result. If an integration
requires normalized process codes, use a project-native adapter and verify it;
this skill introduces no common scanner API or runtime requirement.

For Vulture, native 0 means no reported findings, 3 means findings, 1 means
invalid input, and 2 means invalid arguments. Map selected blocking findings to
`FAIL` and invalid input/arguments to `ERROR`. Native nonzero outcomes remain
blocking; an adapter must not hide crashes or unknown codes. A compiler warning
with exit 0 is not blocking enforcement; enable the agreed lint severity.

Retain commands, pinned versions, selected rules, diagnostics, raw and normalized
outcomes, timings, snapshot identity, review dispositions, and binary assertions.
Separate document/template contract tests from observed workflow evidence.
Simulated infrastructure failures cannot establish analyzer coverage.

## 6. Example Capability Report

Example project policy: reject F401/F841 and reviewed unused-definition findings;
contract review is required for public APIs and compatibility paths. This is
partial automatic coverage with explicit manual controls, not a universal scan.

| Capability                                             | Status      | Evidence and residual scope                                                                                                                                        |
| ------------------------------------------------------ | ----------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Unused imports and local variables                     | ENABLED     | Pinned Ruff, F401/F841, `ruff check src tests`; staged snapshot; pre-commit; 0.1s; actual F401 blocked.                                                            |
| Unused functions, classes, and methods                 | ENABLED     | Pinned Vulture, `vulture src review/uses.py`; staged sources; pre-commit; 0.2s; reviewed unused function blocked; name collisions/dynamic uses remain limitations. |
| Unused modules and files                               | UNSUPPORTED | No accurate entry/graph analyzer available; requested enforcement incomplete; explicit tool evaluation/setup required.                                             |
| Unused exports                                         | MANUAL      | Reviewer checks documented external API contracts; lint results do not establish absence of consumers.                                                             |
| Unreachable statements                                 | DELEGATED   | Existing Vulture invocation above covers its documented terminal-statement/condition rules; blocked fixture retained.                                              |
| Production code referenced only by tests               | MANUAL      | Compare production/test inputs and review differences; tests do not alone justify retention.                                                                       |
| Obsolete aliases, wrappers, and compatibility branches | MANUAL      | Alias `legacy_load` retained under supported CLI v1 contract; reconsider when v1 support ends; a test-only alias without that contract requires removal review.    |

Every row inherits the recorded command versions, snapshot digest, exclusions,
stage, policy, and timing from the execution record. A callback exception names
its plugin registration contract; it does not suppress a whole directory.
