#!/usr/bin/env python3
"""Run a Lighthouse navigation baseline; requires the Lighthouse CLI and Chrome.

Usage: python lighthouse_audit.py https://example.com
Output: JSON with metrics, diagnostics and measurement settings; errors exit 1.
"""

import json
import math
import subprocess
import sys
import tempfile
from pathlib import Path
from shutil import which
from typing import Any

METRIC_AUDITS = (
    'first-contentful-paint',
    'largest-contentful-paint',
    'total-blocking-time',
    'cumulative-layout-shift',
    'speed-index',
    'server-response-time',
    'interactive',
    'interaction-to-next-paint',
)


def extract_metrics(audits: dict[str, Any]) -> dict[str, Any]:
    """Keep raw values and units; unavailable metrics stay null, never zero."""
    metrics: dict[str, Any] = {}
    for audit_id in METRIC_AUDITS:
        audit = audits.get(audit_id)
        value = audit.get('numericValue') if isinstance(audit, dict) else None
        if (
            not isinstance(audit, dict)
            or not isinstance(value, (int, float))
            or isinstance(value, bool)
            or not math.isfinite(value)
        ):
            metrics[audit_id] = None
            continue
        metrics[audit_id] = {
            key: audit[key]
            for key in ('numericValue', 'numericUnit', 'displayValue')
            if key in audit
        }
    return metrics


def extract_diagnostics(audits: dict[str, Any]) -> list[dict[str, Any]]:
    """Show up to five failed audits, prioritizing estimated time savings."""
    diagnostics = []
    for audit_id, audit in audits.items():
        if audit_id in METRIC_AUDITS or not isinstance(audit, dict):
            continue
        score = audit.get('score')
        if (
            not isinstance(score, (int, float))
            or isinstance(score, bool)
            or not 0 <= score < 1
        ):
            continue
        savings = audit.get('metricSavings', {})
        details = audit.get('details', {})
        estimates = (
            [savings.get(metric) for metric in ('FCP', 'LCP', 'TBT', 'INP')]
            if isinstance(savings, dict)
            else []
        )
        if isinstance(details, dict):
            estimates.append(details.get('overallSavingsMs'))
        estimated_savings = max(
            (
                value
                for value in estimates
                if isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(value)
            ),
            default=None,
        )
        diagnostics.append(
            {
                'id': audit_id,
                **{
                    key: audit[key]
                    for key in (
                        'title',
                        'score',
                        'numericValue',
                        'numericUnit',
                        'displayValue',
                        'metricSavings',
                    )
                    if key in audit
                },
                'estimatedSavingsMs': (
                    max(0, estimated_savings)
                    if estimated_savings is not None
                    else None
                ),
            }
        )
    return sorted(
        diagnostics,
        key=lambda item: (
            -(item['estimatedSavingsMs'] or 0),
            item['score'],
            item['id'],
        ),
    )[:5]


def summarize_report(url: str, report: object) -> dict[str, Any]:
    """Validate the report before presenting a successful baseline."""
    if not isinstance(report, dict):
        return {'error': 'Lighthouse report must be a JSON object'}
    if report.get('runtimeError'):
        return {
            'error': 'Lighthouse reported a runtime error',
            'runtimeError': report['runtimeError'],
        }
    categories = report.get('categories')
    performance = (
        categories.get('performance') if isinstance(categories, dict) else None
    )
    score = performance.get('score') if isinstance(performance, dict) else None
    if (
        not isinstance(score, (int, float))
        or isinstance(score, bool)
        or not 0 <= score <= 1
    ):
        return {
            'error': 'Lighthouse performance score is unavailable or invalid'
        }
    audits = report.get('audits')
    if not isinstance(audits, dict):
        return {'error': 'Lighthouse audits must be a JSON object'}
    performance_score = round(score * 100)
    return {
        'url': url,
        'lighthouseVersion': report.get('lighthouseVersion'),
        'fetchTime': report.get('fetchTime'),
        'configSettings': report.get('configSettings', {}),
        'scores': {'performance': performance_score},
        'metrics': extract_metrics(audits),
        'diagnostics': extract_diagnostics(audits),
        'summary': get_summary(performance_score),
    }


def run_lighthouse(url: str) -> dict[str, Any]:
    """Run one performance-only navigation and clean up on every exit path."""
    lighthouse_bin = which('lighthouse')
    if lighthouse_bin is None:
        return {'error': 'lighthouse executable not found'}
    try:
        with tempfile.TemporaryDirectory(prefix='lighthouse-') as directory:
            output_path = Path(directory) / 'report.json'
            process_result = subprocess.run(
                [
                    lighthouse_bin,
                    url,
                    '--output=json',
                    f'--output-path={output_path}',
                    '--chrome-flags=--headless',
                    '--only-categories=performance',
                ],
                capture_output=True,
                text=True,
                timeout=120,
                check=False,
            )
            if process_result.returncode != 0:
                return {
                    'error': 'Lighthouse process failed',
                    'returncode': process_result.returncode,
                    'stderr': process_result.stderr[:500],
                }
            if not output_path.is_file():
                return {'error': 'Lighthouse failed to generate report'}
            report = json.loads(output_path.read_text(encoding='utf-8'))
            return summarize_report(url, report)

    except subprocess.TimeoutExpired:
        return {'error': 'Lighthouse audit timed out'}
    except FileNotFoundError:
        return {'error': 'Lighthouse executable or report disappeared'}
    except (json.JSONDecodeError, UnicodeError):
        return {'error': 'Lighthouse output is not valid UTF-8 JSON'}
    except OSError as error:
        return {'error': f'Lighthouse audit could not be completed: {error}'}


def get_summary(performance: int) -> str:
    """Generate summary based on scores."""
    if performance >= 90:
        return '[OK] Excellent performance'
    if performance >= 50:
        return '[!] Needs improvement'
    return '[X] Poor performance'


def main(argv: list[str] | None = None) -> int:
    """Print machine-readable output and fail loudly when no baseline exists."""
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        print(json.dumps({'error': 'Usage: python lighthouse_audit.py <url>'}))
        return 1
    result = run_lighthouse(args[0])
    print(json.dumps(result, indent=2))
    return 1 if 'error' in result else 0


if __name__ == '__main__':
    sys.exit(main())
