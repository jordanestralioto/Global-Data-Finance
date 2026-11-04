#!/usr/bin/env python3
"""Skill: performance-profiling.

Script: lighthouse_audit.py
Purpose: Run Lighthouse performance audit on a URL
Usage: python lighthouse_audit.py https://example.com
Output: JSON with performance scores
Note: Requires lighthouse CLI (npm install -g lighthouse)
"""

import json
import os
import subprocess
import sys
import tempfile
from shutil import which


def run_lighthouse(url: str) -> dict:
    """Run Lighthouse audit on URL."""
    try:
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False) as f:
            output_path = f.name

        lighthouse_bin = which('lighthouse')
        if lighthouse_bin is None:
            return {'error': 'lighthouse executable not found'}

        process_result = subprocess.run(
            [
                lighthouse_bin,
                url,
                '--output=json',
                f'--output-path={output_path}',
                '--chrome-flags=--headless',
                '--only-categories=performance,accessibility,best-practices,seo',
            ],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )

        if os.path.exists(output_path):
            with open(output_path, encoding='utf-8') as f:
                report = json.load(f)
            os.unlink(output_path)

            categories = report.get('categories', {})
            return {
                'url': url,
                'scores': {
                    'performance': int(
                        categories.get('performance', {}).get('score', 0) * 100
                    ),
                    'accessibility': int(
                        categories.get('accessibility', {}).get('score', 0)
                        * 100
                    ),
                    'best_practices': int(
                        categories.get('best-practices', {}).get('score', 0)
                        * 100
                    ),
                    'seo': int(
                        categories.get('seo', {}).get('score', 0) * 100
                    ),
                },
                'summary': get_summary(categories),
            }
        return {
            'error': 'Lighthouse failed to generate report',
            'stderr': process_result.stderr[:500],
        }

    except subprocess.TimeoutExpired:
        return {'error': 'Lighthouse audit timed out'}
    except FileNotFoundError:
        return {
            'error': 'Lighthouse CLI not found. Install with: npm install -g lighthouse'
        }


def get_summary(categories: dict) -> str:
    """Generate summary based on scores."""
    perf = categories.get('performance', {}).get('score', 0) * 100
    if perf >= 90:
        return '[OK] Excellent performance'
    if perf >= 50:
        return '[!] Needs improvement'
    return '[X] Poor performance'


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print(json.dumps({'error': 'Usage: python lighthouse_audit.py <url>'}))
        sys.exit(1)

    result = run_lighthouse(sys.argv[1])
    print(json.dumps(result, indent=2))
