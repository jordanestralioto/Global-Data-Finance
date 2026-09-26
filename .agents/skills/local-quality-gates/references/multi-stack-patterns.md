# Multi-Stack and Monorepo Isolation Patterns

> Summary: Best practices for scoping quality gates and pre-commit hooks in multi-stack and monorepo repositories so changes in one directory do not trigger unrelated tools.

## 1. Directory and Path Scoping

In a repository with multiple stacks (e.g. `backend/` in Python and `frontend/` in TypeScript), each hook must declare explicit path filtering:

The `--fix` examples below assume that the project explicitly permits safe
lint fixes and requires review before staging. Use read-only lint commands
when that policy is absent.

### 1.1 Pre-commit Framework Regex Scoping

```yaml
# Backend Python hooks only execute on files inside backend/
- repo: local
  hooks:
    - id: backend-ruff
      name: Backend Lint (Ruff)
      entry: uv run ruff check --fix
      language: system
      files: ^backend/.*\.py$

# Frontend TypeScript hooks only execute on files inside frontend/
- repo: local
  hooks:
    - id: frontend-eslint
      name: Frontend Lint (ESLint)
      entry: pnpm --dir frontend eslint --fix
      language: system
      files: ^frontend/.*\.(ts|tsx|js|jsx)$
```

### 1.2 Lefthook Glob Scoping

```yaml
pre-commit:
  parallel: true
  commands:
    backend-ruff:
      root: "backend/"
      glob: "*.py"
      run: uv run ruff check --fix {staged_files}

    frontend-eslint:
      root: "frontend/"
      glob: "*.{ts,tsx,js,jsx}"
      run: pnpm eslint --fix {staged_files}
```

## 2. Shared Config and Root Hygiene

Selected repository-wide checks (whitespace, EOF, secrets and lockfile sync)
must cover their declared scope regardless of subdirectory. When
`[CIRCULAR_DEPENDENCIES]` is required, inspect each affected package graph and
include cross-package edges when a workspace shares imports; do not silently
skip a stack because another package was unchanged.
