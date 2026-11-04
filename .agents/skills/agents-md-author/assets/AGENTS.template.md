## Project Overview

<!-- AGENTS_AUTHOR: State what the project does, who or what uses it, its main
     inputs and outputs, and important boundaries or invariants. Use only facts
     confirmed in the target repository. Keep the description short. -->

## Architecture & Ownership

<!-- AGENTS_AUTHOR: Show where work starts in the code and how responsibility
     moves through the important components. Name stable entrypoints, owners,
     extension points, and boundaries when they help an agent choose where to
     work. Link to the architecture source for details. -->

## Development Workflow

<!-- AGENTS_AUTHOR: Give exact setup, run, test, and validation commands that
     are confirmed by target manifests, task runners, CI, or current docs. Add a
     formatter, linter, type checker, or build command only when the repository
     uses it. Keep exhaustive gate details in their owner document. -->

## Engineering Rules

- Inspect the responsible code and documentation before editing; verify behavior
  instead of assuming it from a filename or directory.
- Preserve public contracts, component ownership, and established boundaries.
- Keep each change cohesive and within the requested scope. Do not mix unrelated
  refactors into a behavior change.
- Give each function, class, and module a clear responsibility. Remove duplicated
  logic and avoid circular dependencies.
- Add or update tests for changed behavior, relevant edge cases, and regressions.
- Update affected contracts and documentation when behavior or ownership changes.
- Treat implemented behavior and accepted decisions as current; identify plans
  and unimplemented proposals as planned work.
- Use canonical sources for recurring rules. When current sources conflict,
  identify the sources and the disagreement instead of inventing a resolution.
- Protect secrets in notes, logs, and responses; do not seek or copy secret
  values into project documentation.
- Run repository-native validation that fits the change and report checks that
  failed or were not run.
- When a repository generates mirrors or projections, edit their source and use
  the owning generator instead of editing generated output directly.

<!-- AGENTS_AUTHOR: Add only durable rules confirmed for this target, such as
     language policy, dependency manager, framework conventions, data/security
     invariants, compatibility requirements, or generated-file ownership. -->

## Documentation Map

<!-- AGENTS_AUTHOR: Link to existing documents by the question they answer:
     onboarding, architecture, development, operations, testing, contracts, or
     decisions. State which document to open next instead of listing every file. -->

- <!-- AGENTS_AUTHOR: Add a verified relative path and when to read it. -->
