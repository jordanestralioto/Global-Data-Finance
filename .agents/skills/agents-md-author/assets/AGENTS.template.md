## System Overview

<!-- AGENTS_AUTHOR: Explain the system's mission, users, macro boundaries, inputs, outputs, downstream consumers, and non-negotiable invariants. Begin with a direct identity statement: "<Project> is ...". Link to owner documents instead of inventorying private modules or dependencies. -->

<!-- AGENTS_AUTHOR: State the design priorities in order when the project has an evidenced priority model. Do not manufacture one. -->

## Success Metrics

| Metric                                                          | Target                                                     |
| --------------------------------------------------------------- | ---------------------------------------------------------- |
| <!-- AGENTS_AUTHOR: adopted metric or Project-owned metrics --> | <!-- AGENTS_AUTHOR: evidenced target or Not documented --> |

## Pipeline Architecture

<!-- AGENTS_AUTHOR: Describe the executable runtime path from entrypoint through major roles to outputs. Preserve evidenced, stable, high-routing anchors such as the public facade, composition root, factory/registry, extension owner, and canonical validation entrypoint. Do not reproduce every private class, adapter, or internal step. If the project is not a data pipeline, explain the actual request/runtime/build flow while retaining this heading. -->

<!-- AGENTS_AUTHOR: Add an explicit navigation route: where an agent starts for architecture, which owning document or module it opens next, and where details intentionally live. Use existing relative links only. -->

## Configuration & Runtime

| Surface                                                                              | Location                              | Purpose                                   |
| ------------------------------------------------------------------------------------ | ------------------------------------- | ----------------------------------------- |
| <!-- AGENTS_AUTHOR: configuration surface, runtime, manager, or framework config --> | <!-- AGENTS_AUTHOR: existing path --> | <!-- AGENTS_AUTHOR: evidenced purpose --> |

### Commands

| Action                         | Command                                                    |
| ------------------------------ | ---------------------------------------------------------- |
| <!-- AGENTS_AUTHOR: action --> | <!-- AGENTS_AUTHOR: verified repository-native command --> |

<!-- AGENTS_AUTHOR: State configuration behavior and only the public variables that change recurring agent decisions. Link to the configuration owner for defaults and exhaustive lists. Never copy secret values. -->

## Technical Stack

<!-- AGENTS_AUTHOR: List stable languages, runtimes, dependency managers, command runners, frameworks, structural libraries, and decision-critical quality, security, build, and deployment tooling. Include concise formatter/linter policy values when they directly constrain new code. Include versions only when declared. Do not turn manifests or hook rosters into prose. -->

## Mandatory Rules

- Do not write irrelevant comments in code.
- Verify files before editing; do not assume structure or behavior.
- Plan before modifying and keep scope small, reviewable, and verifiable.
- Write well-factored code with clear single responsibility per function, class,
  or module; do not create monolithic functions that handle multiple concerns.
- Never leave duplicated logic; extract common functionality into shared
  functions or modules.
- Never introduce circular imports or mutual module dependencies.
- Deliver only what is necessary to satisfy the request end-to-end; do not
  bundle unrequested changes or mix structural refactors with bug fixes.
- Tests must prove relevant behavior, edge cases, and regressions, not merely
  nominal line coverage.
- Always act as a skeptic: verify hypotheses empirically instead of accepting
  them, whether they came from the user or from you. Never flatter the user or
  engage in sycophantic agreement.
- Do not write code files whose sole purpose is to re-export other files or
  modules without added value.
- `__init__.py` files must never contain code or implementation logic; they must
  only contain explicit exports.
- Never edit generated mirrors or generated files directly; change the source
  and re-run its generation or sync command.
- Keep `Code/Comments/Git/planning artifacts` in English. Adapt `Chat` to the
  user's preferred language.
- Follow the repository's established naming, formatting, ownership, and module
  boundaries.
- Use the dependency manager and command runner identified by this document and
  the repository; do not mix managers or regenerate another lockfile unless the
  task explicitly includes that migration.
- Preserve the current framework and its established abstractions; do not add a
  competing framework or parallel architectural path without an explicit
  decision.
- Use repository-native entrypoints and official scripts before ad hoc commands.
- Update tests, contracts, and canonical documentation when behavior or a public
  boundary changes.
- Do not leave dead code, unused compatibility paths, duplicated ownership, or
  stale documentation after a completed clean cutover unless compatibility is an
  explicit project requirement.
- Treat current runtime code and accepted decisions as current state. Treat
  proposals, plans, and unimplemented specifications as planned state.
- Start architecture, operations, testing, and governance questions at the
  owning sources listed under Related Documentation; open only the material
  needed for the task.
- Keep this file focused on durable policy, the system map, and navigation. Put
  detailed contracts in their canonical owner documents and link to them here.
- Do not silently change public contracts, persisted formats, authentication
  flows, security boundaries, runtime topology, or deployment behavior.

<!-- AGENTS_AUTHOR: Insert concrete project directives for every resolved item below, then remove this comment. Omit an item only when it is explicitly unknown and the document remains Draft.
- language: project-specific language overrides if different from the baseline;
- tooling: exact dependency manager, runner, and preferred command form;
- framework: exact framework and the project pattern new work must preserve;
- quality: exact format, lint, typecheck, test, and official validation commands;
- invariants: project-specific data, security, ownership, compatibility, or layering rules;
- navigation: exact first document for architecture and the owner of detailed contracts;
- routing and extension: concrete entrypoint, composition/dispatch owner, registration point, public export, and canonical gate when those paths are stable and recurring.
Use direct wording such as "Use `uv run` for Python commands" rather than "use the correct manager". -->

## Execution Policy

### Precedence

Rank: system constraints → repository/workspace policy and tooling → user
request. Act on the highest-ranking unambiguous, safe instruction without asking
again. If same-rank instructions conflict, prefer the more specific and safer
one.

### Secrets

Never seek, log, copy, or expand secrets. Treat `.env`, API keys, tokens,
cookies, auth sessions, certificates, and private keys as sensitive. If a secret
appears in output: stop, redact it, and report that sensitive data was found.

### Repo Alignment

Follow the repository's canonical contracts, documentation, current code,
accepted decisions, and official scripts before inventing a new workflow. Prefer
existing project patterns, entrypoints, and abstractions over ad hoc
alternatives. Do not silently change public contracts, persisted formats, auth
flows, runtime topology, or security boundaries. If code, docs, and tooling
disagree: stop, report the ambiguity, and identify the conflicting sources.

### Autonomy

Execute reversible repository/workspace changes without confirmation only when
all hold:

- Goal and success criteria are unambiguous.
- Change is contained inside the authorized repository/workspace scope.
- Change is fully recoverable via version control.

Stop and ask when: ambiguous scope, destructive side effects, external systems,
production impact, secrets involved, or conflict between same-rank instructions.

### Validation

Before concluding code or tooling changes, use the repository's official
validation entrypoint when applicable. Prefer repository-native commands and
scripts over custom one-off equivalents. If validation is skipped, unsupported,
or failing, report that explicitly with the reason and impact.

### Execution Safety

Before any destructive, publish, migration, deployment-like, or external-state
operation:

1. State exactly what will be affected.
2. Inspect and validate the exact target and scope.
3. Run a dry run when the command supports it.
4. Break complex operations into readable steps; do not hide behavior in opaque
   one-liners.

Before running local scripts that call the operating system, inspect the command
path. Stop and ask if the script is obfuscated, downloads executables, touches
secrets, or has unclear side effects.

### Failure Handling

If a security lock, permission denial, authentication boundary, or authorization
boundary blocks the task: stop. Do not work around it. Report the block, the
evidence, and the safest next step.

## Related Documentation

<!-- AGENTS_AUTHOR: State the progressive-disclosure order and the first source to open for architecture, onboarding, operations, testing, governance, and decisions when those sources exist. -->

| Doc                                                              | Knowledge class                                          | Purpose                                                       |
| ---------------------------------------------------------------- | -------------------------------------------------------- | ------------------------------------------------------------- |
| <!-- AGENTS_AUTHOR: existing relative path or Not documented --> | <!-- AGENTS_AUTHOR: documented class or Unclassified --> | <!-- AGENTS_AUTHOR: evidenced purpose and when to open it --> |

<!-- AGENTS_AUTHOR: Identify generated, exploratory, internal, archived, planned, or non-canonical sources when the repository documents those categories. State which ones must never govern runtime or policy. -->
