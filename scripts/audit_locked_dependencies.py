"""Audit dependencies exported read-only from the authoritative uv lockfile."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.process_runner import ProcessRunnerError, run_process

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]


def _export_requirements(requirements: Path) -> bool:
    """Export locked runtime and development dependencies."""
    command = [
        'uv',
        'export',
        '--locked',
        '--offline',
        '--all-extras',
        '--dev',
        '--no-emit-project',
        '--no-annotate',
        '--no-header',
        '--format',
        'requirements.txt',
        '--output-file',
        str(requirements),
    ]
    try:
        result = run_process(command, cwd=REPOSITORY_ROOT, check=False)
    except ProcessRunnerError:
        return False
    try:
        return (
            result.returncode == 0
            and requirements.is_file()
            and requirements.stat().st_size > 0
        )
    except OSError:
        return False


def _load_dependencies(report: Path, stderr: str) -> list[Any] | None:
    """Read report dependencies or emit a bounded diagnostic."""
    try:
        payload = json.loads(report.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, json.JSONDecodeError):
        if 'socket.gaierror' in stderr:
            print(
                'EXTERNAL_FAILURE [DEPENDENCY_AUDIT]: DNS lookup failed '
                'before a report was produced'
            )
        else:
            print(
                'ERROR [DEPENDENCY_AUDIT]: audit report is missing or invalid'
            )
        return None
    if not isinstance(payload, dict):
        print('ERROR [DEPENDENCY_AUDIT]: audit report is not an object')
        return None
    dependencies = payload.get('dependencies')
    if not isinstance(dependencies, list) or not dependencies:
        print('ERROR [DEPENDENCY_AUDIT]: audit report has no dependencies')
        return None
    return dependencies


def _audit_report(requirements: Path, report: Path) -> int:
    """Classify a complete pip-audit JSON report."""
    command = [
        'python',
        '-m',
        'pip_audit',
        '--format',
        'json',
        '--output',
        str(report),
        '--disable-pip',
        '--require-hashes',
        '--progress-spinner',
        'off',
        '--timeout',
        '60',
        '-r',
        str(requirements),
    ]
    try:
        result = run_process(command, cwd=REPOSITORY_ROOT, check=False)
    except ProcessRunnerError:
        print('ERROR [DEPENDENCY_AUDIT]: pip-audit could not start')
        return 2
    dependencies = _load_dependencies(report, result.stderr or '')
    if dependencies is None:
        return 2
    if result.returncode not in {0, 1}:
        print(
            f'ERROR [DEPENDENCY_AUDIT]: pip-audit exited {result.returncode}'
        )
        return 2
    try:
        findings = _findings(dependencies)
    except ValueError:
        print('ERROR [DEPENDENCY_AUDIT]: malformed dependency findings')
        return 2
    if findings:
        print(f'FAIL [DEPENDENCY_AUDIT]: {len(findings)} known advisories')
        for name, version, advisory in findings:
            print(f'  {name} {version}: {advisory}')
        return 1
    if result.returncode != 0:
        print('ERROR [DEPENDENCY_AUDIT]: audit did not complete cleanly')
        return 2
    print(f'PASS [DEPENDENCY_AUDIT]: audited {len(dependencies)} packages')
    return 0


def _findings(
    dependencies: list[Any],
) -> list[tuple[str, str, str]]:
    """Extract bounded advisory identifiers from pip-audit dependencies."""
    findings: list[tuple[str, str, str]] = []
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            raise ValueError('dependency must be an object')
        name = dependency.get('name')
        version = dependency.get('version')
        vulnerabilities = dependency.get('vulns')
        if (
            not isinstance(name, str)
            or not name
            or not isinstance(version, str)
            or not version
            or not isinstance(vulnerabilities, list)
        ):
            raise ValueError('dependency fields are incomplete')
        for vulnerability in vulnerabilities:
            if not isinstance(vulnerability, dict):
                raise ValueError('advisory must be an object')
            advisory = vulnerability.get('id')
            if not isinstance(advisory, str) or not advisory:
                raise ValueError('advisory id is missing')
            findings.append((name, version, advisory))
    return findings


def main() -> int:
    """Run a fail-closed advisory scan of the uv-locked dependency graph."""
    try:
        with TemporaryDirectory(prefix='gdf-locked-audit-') as temporary:
            requirements = Path(temporary) / 'requirements.txt'
            report = Path(temporary) / 'audit.json'
            if not _export_requirements(requirements):
                print('ERROR [DEPENDENCY_AUDIT]: uv lock export failed')
                return 2
            return _audit_report(requirements, report)
    except OSError:
        print('ERROR [DEPENDENCY_AUDIT]: temporary workspace unavailable')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
