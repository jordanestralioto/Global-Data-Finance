# Finding Baselines for Legacy Projects

> Summary: Freeze the identity of existing findings so a fixed old error cannot
> hide a new one with the same total count.

## 1. The Baseline / Ratchet Principle

In legacy repositories, full validation may find historical lint or type
errors. Keep those findings reviewable without authorizing new ones.

The baseline strategy enforces two complementary rules:

1. **Historical debt is identified**: Record stable fingerprints, such as
   path, rule code and normalized message or a tool-provided finding ID.
   Preserve enough context to distinguish two findings in the same file.
2. **New findings fail**: Compare finding sets and fail when
   `current - baseline` is nonempty. A count cap alone is insufficient:
   `{A, B}` becoming `{B, C}` keeps the count at two but introduces `C`.
3. **Baseline edits are reviewed**: Reject added fingerprints during ordinary
   changes. Remove a fingerprint when its finding is fixed; add one only by
   an explicit debt-policy change with evidence.

## 2. Tool-Specific Baseline Recipes

### 2.1 Mypy / Python Typing Baseline

- Prefer a pinned baseline tool that records error signatures and compares
  them to the current mypy output. Verify that a new finding fails even when
  another finding was removed in the same run.
- If the project cannot compare findings by identity, mark the result as
  partial coverage. Checking changed files may help, but cross-file typing
  errors can appear outside those paths; it is not a zero-regression proof.

### 2.2 ESLint Baseline

- Use a pinned ESLint baseline mechanism or normalize machine-readable
  findings to stable per-finding IDs. Run read-only lint in the gate; do not
  use `--fix` or shell command substitution to approximate a baseline.

### 2.3 Gitleaks / Secret Scanning Baseline

- Use tool-supported finding fingerprints only for reviewed false positives.
  Keep scanner output redacted; do not print or copy detected secret values
  into a report or baseline.

### 2.4 File Size / Max Lines Baseline

- Use `check-max-lines.py --write-baseline` only during initial adoption, then
  review the generated `.max-lines-baseline.json`. Each entry records the
  existing file's exact line-count cap; any growth beyond it fails the gate.
  Remove entries when files return below their fixed role limit.

## 3. Ratchet Workflow

1. When cleaning up a file, remove resolved finding IDs from the baseline.
2. Exercise a replacement test: one old finding disappears and a different
   finding appears; the gate must fail even though the total is unchanged.
3. Protect the baseline file from silent expansion by the same gate or a
   separate review policy.
