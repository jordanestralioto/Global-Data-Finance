#!/usr/bin/env python3
"""Conservative test command resolver for testing-patterns."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

for stream in (sys.stdout, sys.stderr):
    with suppress(AttributeError, OSError):
        getattr(stream, 'reconfigure', lambda **_: None)(
            encoding='utf-8', errors='replace'
        )


@dataclass(frozen=True)
class TestCommand:
    project_type: str
    framework: str
    command: list[str]
    coverage_command: list[str] | None
    reason: str


def load_package_json(project_path: Path) -> dict[str, Any]:
    pkg = project_path / 'package.json'
    if not pkg.exists():
        return {}
    try:
        data = json.loads(pkg.read_text(encoding='utf-8'))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def detect_node_command(project_path: Path) -> TestCommand | None:
    pkg = load_package_json(project_path)
    if not pkg:
        return None

    raw_scripts = pkg.get('scripts', {})
    scripts = raw_scripts if isinstance(raw_scripts, dict) else {}
    raw_deps = pkg.get('dependencies', {})
    raw_dev = pkg.get('devDependencies', {})
    deps = {
        **(raw_deps if isinstance(raw_deps, dict) else {}),
        **(raw_dev if isinstance(raw_dev, dict) else {}),
    }

    test_cmd = str(scripts.get('test', '')).strip()
    placeholder = not test_cmd or 'no test specified' in test_cmd.lower()

    if 'test' in scripts and not placeholder:
        coverage = None
        if 'test:coverage' in scripts:
            coverage = ['npm', 'run', 'test:coverage']
        elif 'vitest' in deps:
            coverage = ['npx', 'vitest', 'run', '--coverage']
        elif 'jest' in deps:
            coverage = ['npx', 'jest', '--coverage']
        return TestCommand(
            'node',
            'npm test',
            ['npm', 'test'],
            coverage,
            'package.json exposes a test script',
        )

    if 'vitest' in deps:
        return TestCommand(
            'node',
            'vitest',
            ['npx', 'vitest', 'run'],
            ['npx', 'vitest', 'run', '--coverage'],
            'vitest dependency detected',
        )

    if 'jest' in deps:
        return TestCommand(
            'node',
            'jest',
            ['npx', 'jest'],
            ['npx', 'jest', '--coverage'],
            'jest dependency detected',
        )

    return None


def has_python_test_surface(project_path: Path) -> tuple[bool, str]:
    if (project_path / 'tests').is_dir() or (project_path / 'test').is_dir():
        return True, 'tests directory detected'
    if any(project_path.glob('test_*.py')) or any(
        project_path.glob('*_test.py')
    ):
        return True, 'Python test files detected'

    for cfg in ('pytest.ini', 'tox.ini'):
        if (project_path / cfg).exists():
            return True, f'{cfg} detected'

    setup_cfg = project_path / 'setup.cfg'
    if setup_cfg.exists():
        with suppress(OSError):
            txt = setup_cfg.read_text(encoding='utf-8', errors='replace')
            if '[tool:pytest]' in txt or '[pytest]' in txt:
                return True, 'setup.cfg pytest configuration detected'

    pyproject = project_path / 'pyproject.toml'
    if pyproject.exists():
        with suppress(OSError):
            txt = pyproject.read_text(encoding='utf-8', errors='replace')
            if '[tool.pytest' in txt:
                return True, 'pyproject.toml pytest configuration detected'
            if re.search(r'(?i)["\']pytest(?:[<>=!~].*)?["\']', txt):
                return True, 'pytest dependency declared in pyproject.toml'

    for req in project_path.glob('requirements*.txt'):
        with suppress(OSError):
            txt = req.read_text(encoding='utf-8', errors='replace')
            if re.search(r'(?im)^pytest\b', txt):
                return True, f'pytest dependency detected in {req.name}'

    return False, ''


def detect_python_command(project_path: Path) -> TestCommand | None:
    has_surface, reason = has_python_test_surface(project_path)
    if not has_surface:
        return None

    prefix = ['uv', 'run'] if (project_path / 'uv.lock').exists() else []
    base = [*prefix, 'python', '-m', 'pytest']
    return TestCommand(
        'python',
        'pytest',
        [*base, '-v'],
        [*base, '--cov', '--cov-report=term-missing'],
        reason,
    )


def detect_test_command(project_path: Path) -> TestCommand | None:
    node = detect_node_command(project_path)
    python = detect_python_command(project_path)
    if node and node.framework == 'npm test':
        return node
    return python or node


def parse_test_counts(output: str) -> dict[str, int]:
    m_tests = re.search(r'(?m)^\s*Tests\s*[:\s]\s*([^\r\n]+)', output)
    if m_tests:
        line = m_tests.group(1)
        p = re.search(r'(\d+)\s+passed\b', line, re.I)
        f = re.search(r'(\d+)\s+failed\b', line, re.I)
        s = re.search(r'(\d+)\s+skipped\b', line, re.I)
        t = re.search(r'(\d+)\s+total\b', line, re.I)
        passed = int(p.group(1)) if p else 0
        failed = int(f.group(1)) if f else 0
        skipped = int(s.group(1)) if s else 0
        total = int(t.group(1)) if t else (passed + failed + skipped)
        return {
            'passed': passed,
            'failed': failed,
            'skipped': skipped,
            'total': total,
        }

    counts = {'passed': 0, 'failed': 0, 'skipped': 0, 'total': 0}
    patterns: list[tuple[str, str]] = [
        ('passed', r'(\d+)\s+passed\b'),
        ('failed', r'(\d+)\s+failed\b'),
        ('failed', r'(\d+)\s+error[s]?\b'),
        ('skipped', r'(\d+)\s+skipped\b'),
    ]
    for key, pattern in patterns:
        m = re.search(pattern, output, re.I)
        if m:
            counts[key] += int(m.group(1))

    ran_m = re.search(r'Ran\s+(\d+)\s+tests?\b', output, re.I)
    if ran_m:
        total = int(ran_m.group(1))
        ufail = re.search(r'failures=(\d+)', output)
        uerr = re.search(r'errors=(\d+)', output)
        uskip = re.search(r'skipped=(\d+)', output)
        if ufail:
            counts['failed'] = max(counts['failed'], int(ufail.group(1)))
        if uerr:
            counts['failed'] += int(uerr.group(1))
        if uskip:
            counts['skipped'] = max(counts['skipped'], int(uskip.group(1)))
        if 'OK' in output and counts['failed'] == 0:
            counts['passed'] = max(counts['passed'], total - counts['skipped'])

    counts['total'] = counts['passed'] + counts['failed'] + counts['skipped']
    return counts


def _exec_fail(status: str, error: str, retcode: int = -1) -> dict[str, Any]:
    return {
        'status': status,
        'passed': False,
        'returncode': retcode,
        'error': error,
        'stdout': '',
        'stderr': '',
        'counts': {'passed': 0, 'failed': 0, 'skipped': 0, 'total': 0},
    }


def execute_test_command(
    command: list[str], cwd: Path, timeout: int
) -> dict[str, Any]:
    try:
        proc = subprocess.run(
            command,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace',
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        return _exec_fail('blocked', f'Command not found: {command[0]}')
    except subprocess.TimeoutExpired:
        return _exec_fail('timeout', f'Timeout after {timeout}s')

    combined = f'{proc.stdout}\n{proc.stderr}'
    counts = parse_test_counts(combined)
    code = proc.returncode

    if code != 0:
        is_empty = code == 5 or any(
            x in combined.lower()
            for x in ('no tests ran', 'collected 0 items')
        )
        status = 'no_tests_collected' if is_empty else 'failed'
        err = 'No tests collected' if is_empty else f'Exit code {code}'
        passed = False
    elif counts['failed'] > 0:
        status, passed, err = (
            'failed',
            False,
            f'{counts["failed"]} test(s) failed',
        )
    elif counts['total'] == 0:
        status, passed, err = (
            'no_tests_collected',
            False,
            'No tests discovered (total: 0)',
        )
    elif counts['passed'] == 0:
        if counts['skipped'] > 0:
            status = 'all_skipped'
            err = f'All {counts["skipped"]} test(s) skipped (0 passed)'
        else:
            status = 'no_passing_tests'
            err = f'No passing tests found ({counts["total"]} total, 0 passed)'
        passed = False
    else:
        status, passed, err = 'passed', True, ''

    return {
        'status': status,
        'passed': passed,
        'returncode': code,
        'error': err,
        'stdout': proc.stdout[:4000],
        'stderr': proc.stderr[:1000],
        'counts': counts,
    }


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description='Resolve and optionally run project-native tests.'
    )
    p.add_argument('project_path', nargs='?', default='.')
    p.add_argument('--coverage', action='store_true')
    p.add_argument('--dry-run', action='store_true')
    p.add_argument('--output', choices=['summary', 'json'], default='summary')
    p.add_argument('--timeout', type=int, default=300)
    return p


def command_payload(
    project_path: Path,
    cmd: TestCommand | None,
    selected: list[str] | None,
    status: str,
    result: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        'script': 'test_runner',
        'project': str(project_path),
        'timestamp': datetime.now(UTC).isoformat(),
        'status': status,
        'project_type': cmd.project_type if cmd else 'unknown',
        'framework': cmd.framework if cmd else None,
        'reason': cmd.reason if cmd else 'No test command detected',
        'command': selected,
        'result': result,
    }


def print_summary(payload: dict[str, Any]) -> None:
    print('Testing patterns runner')
    print(f'Project: {payload["project"]}')
    print(f'Status: {payload["status"]}')
    print(f'Framework: {payload["framework"]}')
    print(f'Reason: {payload["reason"]}')
    if payload['command']:
        print(f'Command: {" ".join(payload["command"])}')
    result = payload.get('result')
    if not result:
        return
    print(f'Result: {result["status"]}')
    if result.get('error'):
        print(f'Error: {result["error"]}')
    counts = result.get('counts', {})
    if counts.get('total') is not None:
        print(
            f'Tests: {counts["total"]} total, {counts["passed"]} passed, '
            f'{counts["failed"]} failed, {counts["skipped"]} skipped'
        )
    stdout = result.get('stdout') or ''
    if stdout:
        print('\n'.join(stdout.splitlines()[:30]))


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project_path = Path(args.project_path).resolve()
    if not project_path.exists():
        print(json.dumps({'error': f'Path not found: {project_path}'}))
        return 1
    if not project_path.is_dir():
        print(json.dumps({'error': f'Not a directory: {project_path}'}))
        return 1

    cmd = detect_test_command(project_path)
    if cmd is None:
        payload = command_payload(project_path, None, None, 'not_configured')
        if args.output == 'json':
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print_summary(payload)
        return 2

    selected = (
        cmd.coverage_command
        if args.coverage and cmd.coverage_command
        else cmd.command
    )
    if args.dry_run:
        payload = command_payload(project_path, cmd, selected, 'planned')
        if args.output == 'json':
            print(json.dumps(payload, indent=2, ensure_ascii=False))
        else:
            print_summary(payload)
        return 0

    result = execute_test_command(selected, project_path, args.timeout)
    payload = command_payload(
        project_path, cmd, selected, result['status'], result=result
    )
    if args.output == 'json':
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print_summary(payload)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
