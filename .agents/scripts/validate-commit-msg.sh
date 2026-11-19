#!/usr/bin/env bash
# Validates commit messages against Conventional Commits.
#
# Allowed types match this project's actual usage:
#   feat, fix, refactor, build, chore, test, docs, ci, evidence
#
# Runs as a commit-msg hook via pre-commit (stages: [commit-msg]).
#
# Exit codes: 0 accepted, 1 rejected message, 2 unreadable message file.

set -euo pipefail

MSG_FILE="${1:-.git/COMMIT_EDITMSG}"
if ! MSG=$(head -n 1 -- "$MSG_FILE" 2>/dev/null); then
  echo "ERROR [COMMIT_MSG]: cannot read commit message file: $MSG_FILE" >&2
  exit 2
fi

# Skip merge and revert commits
if [[ "$MSG" =~ ^Merge\  ]] || [[ "$MSG" =~ ^Revert\  ]]; then
  exit 0
fi

# Regex: type(scope)!: description
# Scope: optional, lowercase with hyphens/underscores/slashes
# Breaking change: optional `!` before the colon (Conventional Commits 1.0)
# Description: required, starts lowercase, no trailing period, max 500 chars
PATTERN="^(feat|fix|refactor|build|chore|test|docs|ci|evidence)(\([a-z0-9/_-]+\))?!?: [a-z](.*[^.])?$"
MAX_DESCRIPTION_CHARS=500

# The length is counted by Bash instead of a bounded `.{0,N}` repetition,
# which GNU grep compiles for about a second in UTF-8 locales.
DESCRIPTION="${MSG#*: }"
if printf '%s\n' "$MSG" | grep -Eq "$PATTERN" &&
  ((${#DESCRIPTION} <= MAX_DESCRIPTION_CHARS)); then
  exit 0
fi

echo ""
echo "❌ Commit message rejected. Use Conventional Commits format:"
echo ""
echo "  feat(scope): description       - New feature"
echo "  fix(scope): description        - Bug fix"
echo "  refactor(scope): description   - Code change, no behavior change"
echo "  build(scope): description      - Build system, dependencies"
echo "  chore(scope): description      - Tooling, config, maintenance"
echo "  test(scope): description       - Adding or fixing tests"
echo "  docs(scope): description       - Documentation only"
echo "  ci(scope): description         - CI/CD pipeline"
echo "  evidence(scope): description   - Gate evidence artifacts"
echo ""
echo "Rules:"
echo "  - Scope is optional (lowercase, hyphens, underscores, slashes)"
echo "  - Mark a breaking change with ! before the colon: feat(api)!: ..."
echo "  - Description starts lowercase"
echo "  - Max 500 chars, no trailing period"
echo ""
echo "Examples:"
echo "  feat(harness): add component selection API"
echo "  fix(sync): resolve drift detection false positive"
echo "  refactor(openspec): archive completed change"
echo "  build: exclude openspec/changes from mutating hooks"
echo ""
echo "Your message: \"$MSG\""
echo ""
exit 1
