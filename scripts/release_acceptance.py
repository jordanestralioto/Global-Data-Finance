"""Bind release acceptance to native results and checked artifacts."""

from __future__ import annotations

import argparse
import json
import math
import sys
import tomllib
from pathlib import Path
from typing import Any

from scripts.check_distributions import inspect_distributions
from scripts.check_release_evidence import verify_native, verify_shards


def _one(root: Path, name: str) -> Path:
    paths = list(root.rglob(name))
    if len(paths) != 1:
        raise ValueError(f'requires exactly one {name} under {root.name}')
    return paths[0]


def _require_sha(path: Path, sha: str) -> None:
    if sha not in path.read_text().splitlines():
        raise ValueError('evidence belongs to a different candidate SHA')


def coverage_results(root: Path, sha: str) -> dict[str, dict[str, float]]:
    """Require product and executor branch coverage on every Linux version."""
    project = Path(__file__).resolve().parents[1] / 'pyproject.toml'
    config = tomllib.loads(project.read_text())
    floor = float(config['tool']['coverage']['report']['fail_under'])
    results = {}
    for version in ('3.12', '3.13', '3.14'):
        directory = root / f'coverage-report-py{version}'
        _require_sha(_one(directory, 'environment.txt'), sha)
        values = {}
        for kind in ('product', 'executor'):
            report = json.loads(_one(directory, f'{kind}.json').read_text())
            totals = report['totals']
            percentage = float(totals['percent_covered'])
            if (
                report['meta']['branch_coverage'] is not True
                or totals['num_statements'] <= 0
                or totals['num_branches'] <= 0
            ):
                raise ValueError(
                    'coverage must measure executed code and branches'
                )
            if not math.isfinite(percentage) or not floor <= percentage <= 100:
                raise ValueError(
                    f'{kind} coverage below {floor}% on Python {version}'
                )
            values[kind] = percentage
        results[version] = values
    return results


def collect_acceptance(
    root: Path,
    version: str,
    sha: str,
    statuses: dict[str, str],
) -> dict[str, Any]:
    """Reject missing jobs, stale native results, and unchecked builds."""
    if statuses != {
        'quality': 'success',
        'security': 'success',
        'package': 'success',
    }:
        raise ValueError(
            'quality, security, and package prerequisites must succeed'
        )
    native = sorted(root.rglob('results.json'))
    native_count = verify_native(native)
    for report in native:
        _require_sha(report.parent / 'environment.txt', sha)
        if not (report.parent / 'junit.xml').is_file():
            raise ValueError('native JUnit evidence is missing')
    campaign = sorted(root.rglob('campaign-*.json'))
    campaign_count = verify_shards(campaign, 8)
    for report in campaign:
        _require_sha(report.parent.parent / 'environment.txt', sha)
    distributions = inspect_distributions(root / 'dist-packages', version)
    recorded = json.loads(
        _one(
            root / 'release-package-evidence', 'distributions.json'
        ).read_text()
    )
    if distributions != recorded:
        raise ValueError(
            'downloaded distribution bytes differ from checked build'
        )
    for kind in ('wheel', 'sdist'):
        directory = root / 'release-package-evidence'
        if (
            directory / f'smoke-{kind}.status'
        ).read_text().strip() != 'passed' or not (
            directory / f'smoke-{kind}.log'
        ).is_file():
            raise ValueError(f'isolated {kind} smoke evidence is missing')
    return {
        'version': version,
        'sha': sha,
        'native_count': native_count,
        'campaign_count': campaign_count,
        'distributions': distributions,
        'coverage': coverage_results(root, sha),
    }


def render_acceptance(data: dict[str, Any], run_url: str) -> str:
    """Describe verified automated results and their acceptance boundaries."""
    lines = [
        f'# Release acceptance evidence — v{data["version"]}',
        '',
        f'- Candidate SHA: `{data["sha"]}`',
        f'- CI execution: {run_url}',
        '- Automated prerequisites: passed',
        '',
        '## Passed',
        '',
        '- Linux quality, security, integrity, and packaging jobs.',
        f'- {data["native_count"]} focused native tests across Windows/macOS '
        'and Python 3.12/3.13/3.14.',
        f'- {data["campaign_count"]} fault cases across every scenario '
        'and all eight shards.',
        '- Isolated wheel/sdist installation, public exports, '
        'and local CVM/B3 flows.',
        '',
        'Coverage totals combine statements and branches; '
        'branch tracking is enabled.',
        '',
        '| Python | Product coverage | Executor coverage |',
        '| --- | --- | --- |',
    ]
    for version, coverage in data['coverage'].items():
        lines.append(
            f'| {version} | {coverage["product"]:.2f}% '
            f'| {coverage["executor"]:.2f}% |'
        )
    lines.extend(['', '## Checked distributions', ''])
    for distribution in data['distributions']:
        lines.append(
            f'- `{distribution["file"]}` — SHA-256 `{distribution["sha256"]}`'
        )
    lines.extend(
        [
            '',
            '## Failed',
            '',
            'None among required automated prerequisites.',
            '',
            '## Skipped and separate evidence',
            '',
            '- Opt-in real datasets and performance tests remain separate.',
            '- Native validation covers the focused suite; '
            'complete deterministic suites run on Linux.',
            '',
            '## External failure',
            '',
            'None among completed required jobs.',
            '',
        ]
    )
    return '\n'.join(lines)


def main() -> int:
    """Produce an acceptance or failure artifact without bypassing a gate."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('evidence', type=Path)
    parser.add_argument('--version', required=True)
    parser.add_argument('--sha', required=True)
    parser.add_argument('--run-url', required=True)
    parser.add_argument('--quality-status', required=True)
    parser.add_argument('--security-status', required=True)
    parser.add_argument('--package-status', required=True)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    status = 0
    try:
        data = collect_acceptance(
            args.evidence,
            args.version,
            args.sha,
            {
                'quality': args.quality_status,
                'security': args.security_status,
                'package': args.package_status,
            },
        )
        report = render_acceptance(data, args.run_url)
    except (OSError, ValueError, TypeError, KeyError) as error:
        status = 1
        report = (
            '# Release acceptance pending\n\n'
            f'Candidate: `{args.sha}`\n\nFailed prerequisite: {error}\n'
        )
        sys.stderr.write(f'FAIL [RELEASE_ACCEPTANCE]: {error}\n')
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report)
    return status


if __name__ == '__main__':
    sys.exit(main())
