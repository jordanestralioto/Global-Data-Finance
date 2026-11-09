"""Real caller scripts must handle spawn without repeating B3 preflight."""

from __future__ import annotations

import json
import textwrap
from concurrent.futures.process import BrokenProcessPool
from pathlib import Path

import pytest

from globaldatafinance import HistoricalQuotesB3
from scripts.process_runner import run_process
from tests.support.builders import build_cotahist_record, write_cotahist_txt

pytestmark = pytest.mark.integration


def _caller_script(
    root: Path, *, asynchronous: bool, guarded: bool, backend: str, phase: str
) -> Path:
    """Instrument source validation without changing its real behavior."""
    sources = root / 'sources'
    sources.mkdir()
    for year in (2023, 2024):
        write_cotahist_txt(
            sources, year=year, records=[build_cotahist_record(year=year)]
        )
    destination = root / 'output'
    destination.mkdir()
    (destination / 'quotes.parquet').write_bytes(b'previous output')
    invocation = (
        'asyncio.run(client.extract_async(**arguments))'
        if asynchronous
        else 'client.extract(**arguments)'
    )
    script = root / 'caller.py'
    script.write_text(
        textwrap.dedent(
            f"""\
            import asyncio
            import json
            import os
            from pathlib import Path
            from globaldatafinance import HistoricalQuotesB3
            from globaldatafinance.brazil.b3_data.historical_quotes import (
                preflight,
            )

            root = Path({str(root)!r})
            os.environ['GDF_B3_EXECUTOR_BACKEND'] = {backend!r}
            os.environ['GDF_B3_WORKER_LIMIT'] = '2'
            preflight.ResourcePolicyB3.worker_limit = lambda self, count: 2
            if {phase!r} == 'preflight':
                preflight._MIN_PREFLIGHT_SOURCE_BYTES = 1
            original = preflight.CotahistDocumentValidator.validate

            def observed_validation(self, *args, **kwargs):
                (root / f'validated-{{os.getpid()}}').touch()
                return original(self, *args, **kwargs)

            preflight.CotahistDocumentValidator.validate = observed_validation

            def main():
                client = HistoricalQuotesB3()
                arguments = dict(
                    path_of_docs=str(root / 'sources'),
                    destination_path=str(root / 'output'),
                    initial_year=2023,
                    last_year=2024,
                    output_filename='quotes.parquet',
                    verbose=False,
                )
                result = {invocation}
                (root / f'result-{{os.getpid()}}.json').write_text(
                    json.dumps(result), encoding='utf-8'
                )
            """
        )
        + (
            '\nif __name__ == "__main__":\n    main()\n'
            if guarded
            else '\nmain()\n'
        ),
        encoding='utf-8',
    )
    return script


@pytest.mark.parametrize('asynchronous', [False, True], ids=['sync', 'async'])
@pytest.mark.parametrize('phase', ['extraction', 'preflight'])
def test_unguarded_spawn_call_fails_before_child_source_validation(
    tmp_path: Path, asynchronous: bool, phase: str
) -> None:
    """Both APIs explain a broken pool and preserve the existing artifact."""
    script = _caller_script(
        tmp_path,
        asynchronous=asynchronous,
        guarded=False,
        backend='process',
        phase=phase,
    )

    completed = run_process(
        ['python', str(script)], cwd=tmp_path, check=False, timeout=30
    )

    assert completed.returncode == 0, completed.stderr
    results = list(tmp_path.glob('result-*.json'))
    assert len(results) == 1
    result = json.loads(results[0].read_text(encoding='utf-8'))
    assert result['success'] is False
    assert result['output_file'] == ''
    errors = '\n'.join(result['errors'].values())
    assert "if __name__ == '__main__':" in errors
    assert 'GDF_B3_EXECUTOR_BACKEND=thread' in errors
    assert 'spawn bootstrap' in completed.stderr
    assert len(list(tmp_path.glob('validated-*'))) == (
        1 if phase == 'extraction' else 0
    )
    assert (tmp_path / 'output' / 'quotes.parquet').read_bytes() == (
        b'previous output'
    )
    assert not list(
        (tmp_path / 'output').glob('.globaldatafinance-transaction*')
    )


@pytest.mark.parametrize(
    ('guarded', 'backend'), [(True, 'process'), (False, 'thread')]
)
def test_safe_script_publishes_without_reexecuting_its_entrypoint(
    tmp_path: Path, guarded: bool, backend: str
) -> None:
    """The main guard and explicit threads are working migration paths."""
    script = _caller_script(
        tmp_path,
        asynchronous=False,
        guarded=guarded,
        backend=backend,
        phase='extraction',
    )

    completed = run_process(
        ['python', str(script)], cwd=tmp_path, check=False, timeout=30
    )

    assert completed.returncode == 0, completed.stderr
    results = list(tmp_path.glob('result-*.json'))
    assert len(results) == 1
    result = json.loads(results[0].read_text(encoding='utf-8'))
    assert result['success'] is True
    assert result['total_records'] == 2
    assert result['errors'] == {}
    assert len(list(tmp_path.glob('validated-*'))) == 1


def test_failed_pool_submission_preserves_output_and_explains_guard(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A pool failing at submission keeps the migration diagnostic too."""
    _caller_script(
        tmp_path,
        asynchronous=False,
        guarded=True,
        backend='process',
        phase='extraction',
    )
    shutdowns: list[tuple[bool, bool]] = []

    class FailedPool:
        def submit(self, *_args: object, **_kwargs: object) -> None:
            raise BrokenProcessPool('worker startup failed')

        def shutdown(self, *, wait: bool, cancel_futures: bool) -> None:
            shutdowns.append((wait, cancel_futures))

    monkeypatch.setattr(
        'globaldatafinance.brazil.b3_data.historical_quotes.'
        'extraction_service.scheduler.create_b3_executor',
        lambda *_a, **_kw: (FailedPool(), None, True),
    )
    result = HistoricalQuotesB3().extract(
        path_of_docs=str(tmp_path / 'sources'),
        destination_path=str(tmp_path / 'output'),
        initial_year=2023,
        last_year=2024,
        output_filename='quotes.parquet',
        verbose=False,
    )

    assert result['success'] is False
    assert "if __name__ == '__main__':" in result['errors']['executor']
    assert 'GDF_B3_EXECUTOR_BACKEND=thread' in result['errors']['executor']
    assert shutdowns == [(True, False)]
    assert (tmp_path / 'output' / 'quotes.parquet').read_bytes() == (
        b'previous output'
    )
    assert not list(
        (tmp_path / 'output').glob('.globaldatafinance-transaction*')
    )
