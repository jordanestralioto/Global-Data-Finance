"""Run repeatable, process-isolated ingestion measurements.

This local performance tool creates deterministic source corpora, runs each
measurement in a new process, validates logical output, and emits JSON.
"""

from __future__ import annotations

import argparse
import hashlib
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


def _current_git_provenance() -> tuple[str, str]:
    """Return revision and a content digest when the worktree is dirty."""
    try:
        result = run_process(
            ['git', 'rev-parse', 'HEAD'], cwd=Path.cwd(), check=True
        )
        sha = result.stdout.strip() or 'unknown'
        status = run_process(
            ['git', 'status', '--porcelain'], cwd=Path.cwd(), check=True
        )
        if not status.stdout.strip():
            return sha, ''
        diff = run_process(
            ['git', 'diff', '--no-ext-diff', '--binary', 'HEAD'],
            cwd=Path.cwd(),
            check=True,
        )
        untracked = run_process(
            ['git', 'ls-files', '--others', '--exclude-standard'],
            cwd=Path.cwd(),
            check=True,
        )
    except ProcessRunnerError:
        return 'unknown', ''

    digest = hashlib.sha256()
    digest.update(status.stdout.encode('utf-8'))
    digest.update(diff.stdout.encode('utf-8'))
    root = Path.cwd().resolve()
    for relative_path in sorted(untracked.stdout.splitlines()):
        candidate = root / relative_path
        digest.update(relative_path.encode('utf-8'))
        if candidate.is_file() and candidate.resolve().is_relative_to(root):
            digest.update(_sha256_file(candidate).encode('ascii'))
    return f'{sha}-dirty', digest.hexdigest()


def _current_git_sha() -> str:
    """Read the current revision through the approved process boundary."""
    return _current_git_provenance()[0]


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
    parser.add_argument(
        '--backend', choices=('thread', 'process'), default='thread'
    )
    parser.add_argument(
        '--processing-mode',
        choices=('fast', 'slow'),
        default='fast',
        help='B3 processing mode (fast or slow).',
    )
    parser.add_argument('--source-count', type=int, default=None)
    parser.add_argument('--worker-limit', type=int, default=None)
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
        executor_backend=arguments.backend,
        processing_mode=arguments.processing_mode,
        source_count=arguments.source_count or 1,
        worker_limit=arguments.worker_limit or 1,
    )


def _validate_arguments(
    arguments: argparse.Namespace, selected: tuple[str, ...]
) -> None:
    """Reject unsupported benchmark arguments before starting a measurement."""
    if arguments.repeats < 1:
        raise SystemExit('--repeats must be at least one')
    if arguments.rows is not None and arguments.rows < 1:
        raise SystemExit('--rows must be at least one')
    if arguments.source_count is not None and arguments.source_count < 1:
        raise SystemExit('--source-count must be at least one')
    if arguments.worker_limit is not None and arguments.worker_limit < 1:
        raise SystemExit('--worker-limit must be at least one')
    if (
        arguments.source_count is not None
        and arguments.rows is not None
        and arguments.source_count > arguments.rows
    ):
        raise SystemExit('--source-count cannot be greater than --rows')
    if arguments.child:
        if arguments.result_path is None or len(selected) != 1:
            raise SystemExit(
                'A child requires exactly one scenario and result path'
            )
        return
    if arguments.source_count is not None and 'b3_annual' in selected:
        raise SystemExit(
            '--source-count is only supported by b3_multi_4x25k; '
            'b3_annual always uses all 27 source files'
        )


def _prepare_parent_source(
    scenario: str,
    root: Path,
    arguments: argparse.Namespace,
) -> ScenarioInput:
    """Prepare one parent scenario and normalize user-facing input errors."""
    try:
        return _prepare_input(
            scenario,
            root,
            arguments.rows,
            arguments.cotahist_path,
            backend=arguments.backend,
            processing_mode=arguments.processing_mode,
            source_count=arguments.source_count,
            worker_limit=arguments.worker_limit,
        )
    except ValueError as error:
        raise SystemExit(str(error)) from None


def _run_child(
    source: ScenarioInput,
    repeat_index: int,
    result_path: Path,
    *,
    operation: _runtime.ChildOperation = _runtime.execute_child_operation,
) -> None:
    """Run a child while honoring test seams exposed by this entry point."""
    _runtime.run_child(
        source,
        repeat_index,
        result_path,
        operation=operation,
    )


def main() -> int:
    """Run the parent coordinator or one private child measurement."""
    arguments = _parser().parse_args()
    selected = _selected_scenarios(arguments.scenario or ['import_root'])
    _validate_arguments(arguments, selected)
    if arguments.child:
        _run_child(
            _child_source(arguments),
            arguments.repeat_index,
            arguments.result_path,
        )
        return 0

    git_sha, worktree_sha256 = _current_git_provenance()
    records: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix='gdf-benchmark-') as temporary:
        root = Path(temporary)
        for scenario in selected:
            source = _prepare_parent_source(scenario, root, arguments)
            records.extend(
                _run_parent_scenario(
                    source, arguments.repeats, root, git_sha, worktree_sha256
                )
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
        sys.stdout.write(json.dumps(payload, indent=2, sort_keys=True) + '\n')
    return 1 if payload['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
