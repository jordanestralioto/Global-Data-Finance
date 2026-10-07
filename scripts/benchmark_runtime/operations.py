"""Production operations executed by benchmark child processes."""

from __future__ import annotations

import importlib.util
import os
import sys
import time
import zipfile
from collections.abc import Callable
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path
from typing import Any

import scripts.benchmark_runtime.output_validation as output_validation
from globaldatafinance.macro_exceptions import ExtractionError
from scripts.benchmark_corpus.annual import b3_extraction_selection
from scripts.benchmark_support.models import ScenarioInput

OperationResult = tuple[int, str, bool, int, float, str]
ChildOperation = Callable[[ScenarioInput, Path], OperationResult]


OPERATIONAL_ERRORS = (
    ExtractionError,
    OSError,
    ValueError,
    RuntimeError,
    zipfile.BadZipFile,
)

_last_b3_phase_timings: dict[str, Any] = {}


def get_last_b3_phase_timings() -> dict[str, Any]:
    """Return a snapshot of the last B3 benchmark phase measurements."""
    return dict(_last_b3_phase_timings)


def run_cvm(source: ScenarioInput, output_dir: Path) -> OperationResult:
    """Run the production CVM transaction over one generated ZIP."""
    import globaldatafinance.brazil.cvm.fundamental_stocks_data as cvm_data

    if source.path is None:
        raise ValueError('CVM benchmark requires a source ZIP')
    output_dir.mkdir()
    started = time.perf_counter()
    with zipfile.ZipFile(source.path, 'r') as archive:
        cvm_data.transaction.CvmFailureAtomicBatchCommit(
            str(source.path), str(output_dir)
        ).execute(archive)
    op_sec = time.perf_counter() - started
    rows, fp, eq, out_bytes, digest = output_validation.validate_cvm_output(
        output_dir, source
    )
    return rows, fp, eq, out_bytes, op_sec, digest


def run_b3(
    source: ScenarioInput,
    output_dir: Path,
    *,
    processing_mode: str = 'fast',
    executor_backend: str = 'thread',
) -> OperationResult:
    """Run the public B3 facade over generated or external input data."""
    global _last_b3_phase_timings
    from globaldatafinance import HistoricalQuotesB3

    if source.path is None:
        raise ValueError('B3 benchmark requires a source directory or TXT')
    input_dir = source.path if source.path.is_dir() else source.path.parent
    output_dir.mkdir()
    init_yr, last_yr, assets = b3_extraction_selection(source)
    overrides = {
        'GDF_B3_EXECUTOR_BACKEND': executor_backend,
        'GDF_B3_WORKER_LIMIT': str(source.worker_limit),
    }
    previous_environment = {name: os.environ.get(name) for name in overrides}
    os.environ.update(overrides)
    try:
        started = time.perf_counter()
        client = HistoricalQuotesB3()
        result = client.extract(
            path_of_docs=str(input_dir),
            destination_path=str(output_dir),
            assets_list=assets,
            initial_year=init_yr,
            last_year=last_yr,
            output_filename='benchmark_quotes',
            processing_mode=processing_mode,
            verbose=False,
        )
        if not result['success']:
            raise RuntimeError(f'B3 extraction failed: {result["errors"]}')
        op_sec = time.perf_counter() - started
        _last_b3_phase_timings = dict(client.last_phase_timings)
    finally:
        for name, previous_value in previous_environment.items():
            if previous_value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous_value
    output_path = Path(result['output_file'])
    rows, fp, eq, out_bytes, digest = output_validation.validate_b3_output(
        output_path, source
    )
    return rows, fp, eq, out_bytes, op_sec, digest


def _run_import_root() -> OperationResult:
    started = time.perf_counter()
    import globaldatafinance

    valid = globaldatafinance.__name__ == 'globaldatafinance' and not any(
        m == eng or m.startswith(f'{eng}.')
        for eng in ('pandas', 'numpy', 'polars', 'pyarrow')
        for m in sys.modules
    )
    return 0, '', valid, 0, time.perf_counter() - started, ''


def _run_runtime_footprint() -> OperationResult:
    started, total_bytes = time.perf_counter(), 0
    for pkg in ('globaldatafinance', 'pandas', 'pyarrow'):
        try:
            inst = distribution(pkg)
        except PackageNotFoundError:
            return 0, '', False, 0, time.perf_counter() - started, ''
        total_bytes += sum(
            c.stat().st_size
            for i in inst.files or []
            if (c := Path(str(inst.locate_file(i)))).is_file()
        )
    ok = importlib.util.find_spec('polars') is None
    return 0, '', ok, total_bytes, time.perf_counter() - started, ''


def execute_child_operation(
    source: ScenarioInput, output_dir: Path
) -> OperationResult:
    """Execute the appropriate child operation for the given scenario."""
    if source.scenario == 'import_root':
        return _run_import_root()
    if source.scenario == 'runtime_footprint':
        return _run_runtime_footprint()
    if source.scenario.startswith('cvm'):
        return run_cvm(source, output_dir)
    return run_b3(
        source,
        output_dir,
        processing_mode=source.processing_mode,
        executor_backend=source.executor_backend,
    )
