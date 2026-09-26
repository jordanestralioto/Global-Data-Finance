"""Enforce rules missing from the shared conventional commit validator."""

from __future__ import annotations

import sys
from pathlib import Path


def valid_additional_rules(subject: str) -> bool:
    """Check the length and ending promised by the shared validator."""
    if subject.startswith(('Merge ', 'Revert ')):
        return True
    return len(subject) <= 500 and not subject.endswith('.')


def main(argv: list[str] | None = None) -> int:
    """Validate the message file supplied by the commit-msg hook."""
    arguments = sys.argv[1:] if argv is None else argv
    if len(arguments) != 1:
        print('ERROR [COMMIT_MSG]: expected one message file', file=sys.stderr)
        return 2
    try:
        lines = Path(arguments[0]).read_text(encoding='utf-8').splitlines()
    except (OSError, UnicodeError) as error:
        print(
            f'ERROR [COMMIT_MSG]: cannot read message: {error}',
            file=sys.stderr,
        )
        return 2
    subject = lines[0] if lines else ''
    if valid_additional_rules(subject):
        return 0
    print(
        'FAIL [COMMIT_MSG_POLICY]: subject must be at most 500 characters '
        'and have no trailing period',
        file=sys.stderr,
    )
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
