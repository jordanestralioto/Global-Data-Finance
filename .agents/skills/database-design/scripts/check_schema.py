#!/usr/bin/env python3
"""Portable schema triage with explicit coverage and process exit semantics."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path
from typing import Any

from database_checks.inspection import inspect_paths


def positive_integer(raw: str) -> int:
    try:
        value = int(raw)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            'expected a positive integer'
        ) from exc
    if value <= 0:
        raise argparse.ArgumentTypeError('expected a positive integer')
    return value


def summary(report: dict[str, Any]) -> str:
    lines = [
        f'Schema triage: {report["status"]}',
        f'Files: {report["files_inspected"]}/{report["files_found"]}; units: {report["units_checked"]}; omitted: {report["files_omitted"]}',
    ]
    for record in report['files']:
        lines.append(f'{record["path"]}: {record["coverage"]}')
        lines.extend(
            f'  [{finding["severity"].upper()}] line {finding["line"]}: {finding["summary"]}'
            for finding in record['findings']
        )
        lines.extend(f'  [UNVERIFIED] {item}' for item in record['unverified'])
        lines.extend(f'  [ERROR] {item}' for item in record['errors'])
    lines.extend(f'[ERROR] {error}' for error in report['errors'])
    lines.extend(f'[LIMIT] {limit}' for limit in report['limitations'])
    return '\n'.join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        'paths',
        nargs='+',
        type=Path,
        help='Explicit files or directories; use one database boundary per run.',
    )
    parser.add_argument(
        '--include',
        action='append',
        default=[],
        help='Additional candidate glob relative to each directory root; repeatable.',
    )
    parser.add_argument(
        '--exclude',
        action='append',
        default=[],
        help='Excluded path glob relative to each directory root; repeatable.',
    )
    parser.add_argument('--max-files', type=positive_integer, default=500)
    parser.add_argument(
        '--max-bytes', type=positive_integer, default=2_000_000
    )
    parser.add_argument(
        '--output', choices=['json', 'summary'], default='json'
    )
    args = parser.parse_args(argv)
    report, exit_code = inspect_paths(
        args.paths,
        includes=args.include,
        excludes=args.exclude,
        max_files=args.max_files,
        max_bytes=args.max_bytes,
    )
    with contextlib.suppress(AttributeError, OSError):
        getattr(sys.stdout, 'reconfigure', lambda **_: None)(
            encoding='utf-8', errors='replace'
        )
    print(
        json.dumps(report, ensure_ascii=True, indent=2)
        if args.output == 'json'
        else summary(report)
    )
    return exit_code


if __name__ == '__main__':
    raise SystemExit(main())
