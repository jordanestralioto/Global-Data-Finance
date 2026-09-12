"""Run repeatable, process-isolated ingestion measurements.

This local performance tool creates deterministic source corpora, runs each
measurement in a new process, validates logical output, and emits JSON.
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

if __name__ == '__main__' and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts import benchmark_corpus as _corpus
from scripts import benchmark_runtime as _runtime
from scripts import benchmark_support as _support
from scripts.process_runner import ProcessRunnerError, run_process

ScenarioInput = _support.ScenarioInput
RssSampler = _support.RssSampler
_SCENARIOS = _support.SCENARIOS
_SCHEMA_VERSION = _support.SCHEMA_VERSION
_sha256_file = _support.sha256_file
_write_cvm_zip = _corpus.write_cvm_zip
_prepare_input = _corpus.prepare_input
_run_parent_scenario = _runtime.run_parent_scenario
_median_records = _runtime.median_records
_write_json = _support.write_json
_child_operation = _runtime._child_operation


def _current_git_sha() -> str:
    """Read the current revision through the approved process boundary."""
    try:
        result = run_process(
            ['git', 'rev-parse', 'HEAD'], cwd=Path.cwd(), check=True
        )
    except ProcessRunnerError:
        return 'unknown'
    return result.stdout.strip() or 'unknown'


def _selected_scenarios(values: list[str]) -> tuple[str, ...]:
    """Expand ``all`` while preserving stable documented scenario order."""
    if 'all' in values:
        return _SCENARIOS
    return tuple(dict.fromkeys(values))


def _parser() -> argparse.ArgumentParser:
    """Create the CLI parser shared by parent and child execution modes."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--scenario',
        action='append',
        choices=(*_SCENARIOS, 'all'),
        default=None,
        help='Scenario to run; repeat the flag, or pass all.',
    )
    parser.add_argument('--repeats', type=int, default=3)
    parser.add_argument('--rows', type=int)
    parser.add_argument('--cotahist-path', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--input-path', type=Path)
    parser.add_argument('--input-sha256', default='')
    parser.add_argument('--row-count', type=int, default=0)
    parser.add_argument('--expected-first', default='')
    parser.add_argument('--expected-last', default='')
    parser.add_argument('--expected-digest', default='')
    parser.add_argument('--repeat-index', type=int, default=0)
    parser.add_argument('--result-path', type=Path)
    return parser


def _child_source(arguments: argparse.Namespace) -> ScenarioInput:
    """Reconstruct the source descriptor passed by the parent process."""
    return ScenarioInput(
        scenario=arguments.scenario[0],
        path=arguments.input_path,
        row_count=arguments.row_count,
        input_sha256=arguments.input_sha256,
        expected_first=arguments.expected_first,
        expected_last=arguments.expected_last,
        expected_digest=arguments.expected_digest,
    )


def _run_child(
    source: ScenarioInput, repeat_index: int, result_path: Path
) -> None:
    """Run a child while honoring test seams exposed by this entry point."""
    original = _runtime._child_operation
    _runtime._child_operation = _child_operation
    try:
        _runtime.run_child(source, repeat_index, result_path)
    finally:
        _runtime._child_operation = original


def main() -> int:
    """Run the parent coordinator or one private child measurement."""
    arguments = _parser().parse_args()
    selected = _selected_scenarios(arguments.scenario or ['import_root'])
    if arguments.repeats < 1:
        raise SystemExit('--repeats must be at least one')
    if arguments.rows is not None and arguments.rows < 1:
        raise SystemExit('--rows must be at least one')
    if arguments.child:
        if arguments.result_path is None or len(selected) != 1:
            raise SystemExit(
                'A child requires exactly one scenario and result path'
            )
        _run_child(
            _child_source(arguments),
            arguments.repeat_index,
            arguments.result_path,
        )
        return 0

    git_sha = _current_git_sha()
    records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix='gdf-benchmark-') as temporary:
        root = Path(temporary)
        for scenario in selected:
            source = _prepare_input(
                scenario,
                root,
                arguments.rows,
                arguments.cotahist_path,
            )
            records.extend(
                _run_parent_scenario(source, arguments.repeats, root, git_sha)
            )
    payload = {
        'schema_version': _SCHEMA_VERSION,
        'results': records,
        'medians': _median_records(records),
        'status': (
            'passed'
            if records
            and all(record['status'] == 'passed' for record in records)
            else 'failed'
            if any(record['status'] == 'failed' for record in records)
            else 'skipped'
        ),
    }
    if arguments.output is not None:
        _write_json(arguments.output, payload)
    else:
        print(json.dumps(payload, indent=2, sort_keys=True))
    return 1 if payload['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
