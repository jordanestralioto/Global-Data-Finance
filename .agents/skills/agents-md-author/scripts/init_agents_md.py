#!/usr/bin/env python3
"""Create a portable AGENTS.md scaffold without overwriting existing files."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

TEMPLATE_PATH = (
    Path(__file__).resolve().parents[1] / 'assets' / 'AGENTS.template.md'
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description='Create an AGENTS.md scaffold from the portable template.'
    )
    parser.add_argument(
        '--output',
        type=Path,
        default=Path('AGENTS.md'),
        help='Destination path (default: AGENTS.md)',
    )
    parser.add_argument(
        '--stdout',
        action='store_true',
        help='Print the scaffold instead of writing a file.',
    )
    args = parser.parse_args()

    try:
        rendered = TEMPLATE_PATH.read_text(encoding='utf-8')
    except OSError as exc:
        print(f'ERROR: cannot read bundled template: {exc}', file=sys.stderr)
        return 2

    if args.stdout:
        print(rendered, end='')
        return 0

    if not args.output.parent.is_dir():
        print(
            f'ERROR: destination parent does not exist: {args.output.parent}',
            file=sys.stderr,
        )
        return 2

    try:
        with args.output.open('x', encoding='utf-8', newline='\n') as output:
            output.write(rendered)
    except FileExistsError:
        print(
            f'ERROR: destination already exists: {args.output}',
            file=sys.stderr,
        )
        return 2
    except OSError as exc:
        print(f'ERROR: cannot write {args.output}: {exc}', file=sys.stderr)
        return 2

    print(f'CREATED: {args.output}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
