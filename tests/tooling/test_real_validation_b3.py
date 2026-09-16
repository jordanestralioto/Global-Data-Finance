"""Deterministic tests for the isolated COTAHIST validator."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from os import sep
from pathlib import Path
from types import SimpleNamespace
from typing import Literal

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import scripts.real_validation_b3 as b3
from globaldatafinance.brazil.b3_data.historical_quotes import (
    parquet_writer,
)
from scripts.real_validation_b3 import B3_SCHEMA
from scripts.real_validation_types import ValidationCase

pytestmark = pytest.mark.unit


_STRING_COLUMNS = {
    'codigo_bdi',
    'ticker',
    'tipo_mercado',
    'nome_resumido',
    'especificacao_papel',
    'codigo_isin',
}
_DATE_COLUMNS = {'data_pregao', 'data_vencimento'}
_INTEGER_COLUMNS = {
    'numero_negocios',
    'quantidade_total',
    'fator_cotacao',
    'numero_distribuicao',
}


def _write_b3_parquet(
    path: Path,
    *,
    year: int = 2024,
    ticker: str = 'PETR4',
    market: str = '010',
    rows: int = 1,
) -> None:
    """Write a small Parquet with the exact public B3 schema."""
    values: dict[str, list[object]] = {}
    for name in B3_SCHEMA:
        if name in _DATE_COLUMNS:
            values[name] = [date(year, 1, 15)] * rows
        elif name in _STRING_COLUMNS:
            value = market if name == 'tipo_mercado' else ticker
            values[name] = [value] * rows
        elif name in _INTEGER_COLUMNS:
            values[name] = [1] * rows
        else:
            values[name] = [Decimal('1.00')] * rows
    table = pa.Table.from_pydict(
        values, schema=parquet_writer.build_b3_schema()
    )
    pq.write_table(table, path)


def _b3_result(output_path: Path, *, records: int = 1) -> dict[str, object]:
    """Build the successful public facade result used by validator tests."""
    return {
        'success': True,
        'total_files': 1,
        'success_count': 1,
        'error_count': 0,
        'total_records': records,
        'errors': {},
        'output_file': str(output_path),
    }


def _b3_case(mode: Literal['fast', 'parity'] = 'fast') -> ValidationCase:
    """Build a case with a harmless input placeholder."""
    return ValidationCase(
        case_id=f'cotahist-{mode}-2024',
        source='cotahist',
        year=2024,
        input_path=str(Path(sep, 'tmp', 'COTAHIST_A2024.ZIP')),
        output_root='',
        mode=mode,
    )


def test_validate_result_accepts_schema_rows_metadata_and_dates(
    tmp_path: Path,
) -> None:
    """A valid B3 Parquet produces complete artifact evidence."""
    output_directory = tmp_path / 'fast'
    output_directory.mkdir()
    output_path = output_directory / 'cotahist.parquet'
    _write_b3_parquet(output_path)

    details = b3._validate_result(
        _b3_result(output_path), output_directory, 2024
    )

    assert details['valid'] is True
    assert details['record_count'] == 1
    assert details['schema'] == {
        name: str(dtype) for name, dtype in B3_SCHEMA.items()
    }
    assert details['date_range'] == ('2024-01-15', '2024-01-15')
    assert details['artifacts'][0]['pyarrowReadable'] is True


def test_execute_fast_case_uses_public_mode_and_returns_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fast case delegates to the facade and maps valid details."""
    case = _b3_case()
    public_result: dict[str, object] = {'success': True}
    details = {
        'valid': True,
        'message': '',
        'record_count': 3,
        'schema': {'ticker': 'String'},
        'date_range': ('2024-01-01', '2024-01-02'),
        'artifacts': [{'path': 'cotahist.parquet'}],
    }
    calls: list[tuple[Path, int, str, Path]] = []

    def fake_validate(path: Path) -> None:
        assert path == Path(case.input_path)

    def fake_execute(
        path: Path, year: int, mode: str, output_directory: Path
    ) -> tuple[dict[str, object], dict[str, object]]:
        calls.append((path, year, mode, output_directory))
        return public_result, details

    monkeypatch.setattr(b3, 'validate_cotahist_input', fake_validate)
    monkeypatch.setattr(b3, '_execute_mode', fake_execute)

    result = b3.execute_cotahist_case(case, tmp_path / 'workspace')

    assert result['status'] == 'passed'
    assert result['recordCount'] == 3
    assert calls == [
        (
            Path(case.input_path),
            2024,
            'fast',
            tmp_path / 'workspace' / 'fast',
        )
    ]


def test_execute_fast_case_retains_public_failure_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed B3 artifact becomes a functional case failure."""
    case = _b3_case()
    monkeypatch.setattr(b3, 'validate_cotahist_input', lambda _path: None)
    monkeypatch.setattr(
        b3,
        '_execute_mode',
        lambda *_args: (
            {'success': False},
            {'valid': False, 'message': 'schema mismatch'},
        ),
    )

    result = b3.execute_cotahist_case(case, tmp_path / 'workspace')

    assert result['status'] == 'failed'
    assert result['message'] == 'schema mismatch'
    assert result['publicResult'] == {'success': False}


def test_execute_parity_compares_both_public_modes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Parity evidence contains both artifacts and the comparison method."""
    case = _b3_case('parity')
    monkeypatch.setattr(b3, 'validate_cotahist_input', lambda _path: None)
    fast_path = tmp_path / 'fast.parquet'
    slow_path = tmp_path / 'slow.parquet'
    fast_details = {
        'valid': True,
        'message': '',
        'record_count': 2,
        'schema': {'ticker': 'String'},
        'date_range': ('2024-01-01', '2024-01-02'),
        'artifacts': [{'path': fast_path.name}],
    }
    slow_details = {
        **fast_details,
        'artifacts': [{'path': slow_path.name}],
    }
    calls: list[str] = []

    def fake_execute(
        _path: Path, _year: int, mode: str, _output_directory: Path
    ) -> tuple[dict[str, object], dict[str, object]]:
        calls.append(mode)
        result: dict[str, object] = {
            'output_file': str(fast_path if mode == 'fast' else slow_path)
        }
        return result, fast_details if mode == 'fast' else slow_details

    monkeypatch.setattr(b3, '_execute_mode', fake_execute)
    monkeypatch.setattr(
        b3, '_compare_content', lambda _first, _second: 'full_frame'
    )

    result = b3.execute_cotahist_case(case, tmp_path / 'workspace')

    assert result['status'] == 'passed'
    assert result['comparisonMethod'] == 'full_frame'
    assert [item['mode'] for item in result['artifacts']] == ['fast', 'slow']
    assert calls == ['fast', 'slow']


@pytest.mark.parametrize(
    ('failed_mode', 'message'),
    [
        ('fast', 'fast invalid'),
        ('slow', 'slow invalid'),
    ],
)
def test_parity_stops_when_one_mode_is_invalid(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failed_mode: str,
    message: str,
) -> None:
    """Parity does not compare content after a mode validation failure."""
    case = _b3_case('parity')

    def fake_execute(
        _path: Path, _year: int, mode: str, _output_directory: Path
    ) -> tuple[dict[str, object], dict[str, object]]:
        details = {
            'valid': mode != failed_mode,
            'message': message if mode == failed_mode else '',
            'record_count': 1,
            'schema': {},
            'date_range': ('2024-01-01', '2024-01-01'),
            'artifacts': [],
        }
        return {'mode': mode}, details

    monkeypatch.setattr(b3, '_execute_mode', fake_execute)

    result = b3._execute_parity(case, Path(case.input_path), tmp_path)

    assert result['status'] == 'failed'
    assert result['message'] == message


@pytest.mark.parametrize(
    ('field', 'value', 'message'),
    [
        ('record_count', 2, 'fast/slow row count mismatch'),
        ('schema', {'different': 'schema'}, 'fast/slow schema mismatch'),
        (
            'date_range',
            ('2023-01-01', '2023-01-01'),
            'fast/slow date range mismatch',
        ),
    ],
)
def test_parity_rejects_cross_mode_metadata_mismatches(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    field: str,
    value: object,
    message: str,
) -> None:
    """Parity rejects metadata mismatches before file comparison."""
    case = _b3_case('parity')
    base = {
        'valid': True,
        'message': '',
        'record_count': 1,
        'schema': {},
        'date_range': ('2024-01-01', '2024-01-01'),
        'artifacts': [],
    }
    fast_details = dict(base)
    slow_details = {**base, field: value}
    modes = iter([fast_details, slow_details])
    monkeypatch.setattr(
        b3,
        '_execute_mode',
        lambda *_args: (
            {'output_file': str(Path(sep, 'tmp', 'output.parquet'))},
            next(modes),
        ),
    )

    result = b3._execute_parity(case, Path(case.input_path), tmp_path)

    assert result['status'] == 'failed'
    assert result['message'] == message


def test_compare_content_uses_full_frame_for_small_files(
    tmp_path: Path,
) -> None:
    """Small outputs compare sorted complete frames with dtype checking."""
    first = tmp_path / 'first.parquet'
    second = tmp_path / 'second.parquet'
    _write_b3_parquet(first)
    _write_b3_parquet(second)

    assert b3._compare_content(first, second) == 'full_frame'


def test_compare_content_uses_digest_for_large_outputs_and_rejects_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The bounded fallback remains order-independent and detects changes."""
    first = tmp_path / 'first.parquet'
    second = tmp_path / 'second.parquet'
    _write_b3_parquet(first)
    _write_b3_parquet(second)
    monkeypatch.setattr(b3, '_FRAME_COMPARE_LIMIT', 0)

    assert b3._compare_content(first, second) == (
        'order_independent_batch_digest'
    )
    _write_b3_parquet(second, ticker='VALE3')
    with pytest.raises(AssertionError, match='canonical content digest'):
        b3._compare_content(first, second)


@pytest.mark.parametrize(
    ('result_factory', 'message'),
    [
        (lambda _path: {'success': False}, 'public B3 result'),
        (lambda path: _b3_result(path, records=2), 'row count mismatch'),
    ],
)
def test_validate_result_rejects_public_or_counter_mismatch(
    tmp_path: Path,
    result_factory,
    message: str,
) -> None:
    """Invalid public counters fail before a false approval is recorded."""
    output_directory = tmp_path / 'output'
    output_directory.mkdir()
    output_path = output_directory / 'cotahist.parquet'
    _write_b3_parquet(output_path)

    details = b3._validate_result(
        result_factory(output_path), output_directory, 2024
    )

    assert details['valid'] is False
    assert message in details['message']


def test_validate_result_rejects_wrong_schema_and_output_inventory(
    tmp_path: Path,
) -> None:
    """An escaped or extra output cannot be accepted as the annual artifact."""
    output_directory = tmp_path / 'output'
    output_directory.mkdir()
    output_path = output_directory / 'cotahist.parquet'
    pq.write_table(pa.table({'wrong': [1]}), output_path)
    extra = output_directory / 'extra.parquet'
    extra.write_bytes(output_path.read_bytes())

    details = b3._validate_result(
        _b3_result(output_path), output_directory, 2024
    )

    assert details['valid'] is False
    assert details['message'] == 'B3 output file count is not one'


def test_validate_result_reports_temporary_leaks_and_wrong_dates(
    tmp_path: Path,
) -> None:
    """Temporary files and wrong annual dates are explicit errors."""
    output_directory = tmp_path / 'output'
    output_directory.mkdir()
    output_path = output_directory / 'cotahist.parquet'
    _write_b3_parquet(output_path, year=2023)
    (output_directory / 'staging.tmp').touch()

    details = b3._validate_result(
        _b3_result(output_path), output_directory, 2024
    )

    assert details['valid'] is False
    assert 'wrong year' in details['message']


def test_validate_metadata_and_date_range_report_empty_or_unreadable_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Low-level evidence readers classify empty metadata and date ranges."""
    output = tmp_path / 'output.parquet'
    _write_b3_parquet(output)
    assert b3._date_range(output) == ('2024-01-15', '2024-01-15')
    assert b3._validate_metadata(output) is None

    empty = tmp_path / 'empty.parquet'
    pq.write_table(
        pa.table({'data_pregao': pa.array([None], type=pa.date32())}), empty
    )
    with pytest.raises(ValueError, match='date range is empty'):
        b3._date_range(empty)

    class EmptyMetadata:
        num_rows = 0

    monkeypatch.setattr(
        b3.pq,
        'ParquetFile',
        lambda _path: SimpleNamespace(metadata=EmptyMetadata()),
    )
    assert b3._validate_metadata(output) == 'B3 Parquet metadata is invalid'
