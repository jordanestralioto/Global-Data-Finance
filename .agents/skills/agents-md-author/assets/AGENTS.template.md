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

- Inspect the responsible code and documentation before editing; preserve public
  contracts, component ownership, and established boundaries.
- Keep each change cohesive; add or update tests, contracts, and documentation
  for changed behavior. Run repository-native validation and report checks that
  failed or were not run.
- Edit generated output through its canonical source and owning generator. Name
  conflicting sources instead of inventing a resolution; distinguish implemented
  behavior and accepted decisions from plans.
- Protect secrets in commands, logs, and responses.

<!-- AGENTS_AUTHOR: Add only durable rules confirmed for this target, such as
     language policy, dependency manager, framework conventions, data/security
     invariants, compatibility requirements, or generated-file ownership. -->

## Documentation Map

<!-- AGENTS_AUTHOR: Link to existing documents by the question they answer:
     onboarding, architecture, development, operations, testing, contracts, or
     decisions. State which document to open next instead of listing every file. -->

- <!-- AGENTS_AUTHOR: Add a verified relative path and when to read it. -->
