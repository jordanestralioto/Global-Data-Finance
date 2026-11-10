#!/usr/bin/env python3
"""Portable heuristic API triage; run by path from any consumer repository."""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from pathlib import Path
from typing import Any

from api_checks import check_api_code, check_openapi_spec, discover_api_files
from api_checks.contracts import FileResult, file_result


def inspect_file(path: Path) -> FileResult:
    kind = (
        'openapi'
        if path.suffix.lower() in {'.json', '.yaml', '.yml'}
        else 'code'
    )
    try:
        content = path.read_text(encoding='utf-8')
    except (OSError, UnicodeDecodeError) as exc:
        result = file_result(path, kind, 'inspection-error')
        result['issues'].append(f'[X] Unable to read UTF-8 input: {exc}')
        return result
    if kind == 'openapi':
        return check_openapi_spec(path, content)
    return check_api_code(path, content)


def build_report(
    target: Path,
    max_files: int = 25,
    includes: tuple[str, ...] = (),
    excludes: tuple[str, ...] = (),
) -> dict[str, Any]:
    report: dict[str, Any] = {
        'tool': 'api-patterns heuristic validator',
        'note': 'Triage only. Lexical markers and declared contracts do not prove runtime safety.',
        'target': str(target),
        'files_found': 0,
        'files_checked': 0,
        'files_omitted': 0,
        'status': 'complete',
        'summary': {'passed': 0, 'warnings': 0, 'critical': 0},
        'results': [],
        'errors': [],
    }
    try:
        files = discover_api_files(target, includes, excludes)
    except (OSError, ValueError) as exc:
        report['status'] = 'inspection-error'
        report['errors'].append(str(exc))
        return report
    results = [inspect_file(path) for path in files[:max_files]]
    report.update(
        files_found=len(files),
        files_checked=len(results),
        files_omitted=max(0, len(files) - len(results)),
        results=results,
    )
    for result in results:
        report['summary']['passed'] += len(result['passed'])
        for issue in result['issues']:
            level = 'critical' if issue.startswith('[X]') else 'warnings'
            report['summary'][level] += 1
    if not files:
        report['status'] = 'no-files'
        report['errors'].append(
            'No API candidates found; select a file or use --include with project conventions.'
        )
    elif any(item['analysis'] == 'inspection-error' for item in results):
        report['status'] = 'inspection-error'
    elif report['files_omitted']:
        report['status'] = 'partial'
    return report


def positive_count(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError('must be a positive integer')
    return number


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', nargs='?', default='.')
    parser.add_argument(
        '--output', choices=['summary', 'json'], default='summary'
    )
    parser.add_argument('--max-files', type=positive_count, default=25)
    parser.add_argument(
        '--include',
        action='append',
        default=[],
        help='Relative glob selecting candidates; repeat for custom conventions/languages.',
    )
    parser.add_argument(
        '--exclude',
        action='append',
        default=[],
        help='Relative glob excluding a file or subtree; repeat as needed.',
    )
    parser.add_argument('--fail-on-critical', action='store_true')
    return parser


def print_summary(report: dict[str, Any]) -> None:
    print('API triage: ' + report['status'])
    print(report['note'])
    print(
        f'Files: {report["files_checked"]}/{report["files_found"]}; omitted: {report["files_omitted"]}'
    )
    for error in report['errors']:
        print('[!] ' + error)
    for result in report['results']:
        print(f'\n[FILE] {result["file"]} ({result["analysis"]})')
        for message in result['passed'] + result['issues']:
            print('  ' + message)
        for check in result['unverified']:
            print('  [REVIEW] ' + check)
    print('\nFindings: ' + json.dumps(report['summary']))


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, 'reconfigure', None)
        if callable(reconfigure):
            with contextlib.suppress(OSError, ValueError):
                reconfigure(encoding='utf-8', errors='replace')
    args = build_parser().parse_args(argv)
    report = build_report(
        Path(args.path),
        args.max_files,
        tuple(args.include),
        tuple(args.exclude),
    )
    if args.output == 'json':
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_summary(report)
    if report['status'] != 'complete':
        return 2
    return 1 if args.fail_on_critical and report['summary']['critical'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
