"""Deterministic tests for the isolated COTAHIST validator."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from os import sep
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Literal

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

import scripts.real_validation_b3 as b3
import scripts.real_validation_b3.artifact_validation as artifact_validation
import scripts.real_validation_b3.executor as executor
import scripts.real_validation_b3.frozen_baseline as frozen_baseline
import scripts.real_validation_utils as real_validation_utils
from globaldatafinance.brazil.b3_data.historical_quotes import input_validation
from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    CotahistCatalogError,
)
from scripts.cotahist_oracle import independent_schema
from scripts.real_validation_types import (
    ValidationCase,
    ValidationInputSnapshot,
)
from tests.support.builders import build_cotahist_record, write_cotahist_zip

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ('diagnostic', 'status'),
    [
        ('DiskFullError: Not enough storage', 'external_failure'),
        (
            'PathPermissionError: Destination is not writable',
            'external_failure',
        ),
        ('ExtractionError: invalid financial value', 'failed'),
        ('ExtractionError: field contains DiskFullError: text', 'failed'),
    ],
)
def test_public_storage_failures_keep_diagnostics_and_classification(
    tmp_path: Path, diagnostic: str, status: str
) -> None:
    """Environment prerequisites remain distinct from corrupted data."""
    public = {'success': False, 'errors': {'transaction': diagnostic}}

    details = artifact_validation._validate_result(
        public, tmp_path, 2024, 2024
    )
    failure = artifact_validation._failed_validation(public, details)
    parity = executor._parity_result(public, details, public, {'valid': True})

    assert failure['status'] == parity['status'] == status
    assert diagnostic in failure['message']
    assert failure['publicResult'] == public


def _write_b3_parquet(
    path: Path,
    *,
    year: int = 2024,
    ticker: str = 'PETR4',
    market: str = '010',
    rows: int = 1,
) -> None:
    """Write a small Parquet using the independent v2 contract."""
    values: dict[str, list[object]] = {}
    for field in independent_schema():
        if pa.types.is_date32(field.type):
            values[field.name] = [date(year, 1, 15)] * rows
        elif pa.types.is_large_string(field.type):
            if field.name == 'tipo_mercado':
                value = market
            elif field.name == 'ticker':
                value = ticker
            elif field.name == 'ano_origem':
                value = str(year)
            else:
                value = 'fixture'
            values[field.name] = [value] * rows
        elif pa.types.is_decimal(field.type):
            decimal_value = Decimal(
                '1.000000' if field.type.scale == 6 else '1.00'
            )
            values[field.name] = [decimal_value] * rows
        elif pa.types.is_binary(field.type) or pa.types.is_fixed_size_binary(
            field.type
        ):
            values[field.name] = [bytes(245)] * rows
        else:
            values[field.name] = [
                year if field.name == 'ano_origem' else 1
            ] * rows
    schema = independent_schema().with_metadata(
        {
            b'globaldatafinance.b3.schema_version': b'2',
            b'globaldatafinance.b3.integrity_manifest': b'{}',
        }
    )
    pq.write_table(pa.Table.from_pydict(values, schema=schema), path)


def _b3_result(output_path: Path, *, records: int = 1) -> dict[str, Any]:
    """Build a successful public result with complete-selection evidence."""
    return {
        'success': True,
        'schema_version': 2,
        'total_files': 1,
        'success_count': 1,
        'error_count': 0,
        'total_records': records,
        'errors': {},
        'output_file': str(output_path),
        'integrity': {
            'status': 'passed',
            'selection_complete': True,
            'source_complete': True,
            'missing_years': [],
        },
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


def _snapshot(path: Path) -> ValidationInputSnapshot:
    return ValidationInputSnapshot(
        str(path.resolve()),
        path.stat().st_size,
        real_validation_utils.sha256_file(path),
    )


def _mode_details(
    *,
    rows_hash: str = 'a' * 64,
    artifact: str = 'cotahist.parquet',
) -> dict[str, Any]:
    return {
        'valid': True,
        'message': '',
        'record_count': 2,
        'schema': b3.B3_SCHEMA,
        'date_range': ('2024-01-01', '2024-01-02'),
        'artifacts': [{'path': artifact}],
        'raw_reconciliation': {'rawQuotes': 2, 'outputSha256': 'c' * 64},
        'ordered_rows_sha256': rows_hash,
    }


def test_validate_result_accepts_schema_rows_metadata_and_dates(
    tmp_path: Path,
) -> None:
    """A valid B3 Parquet produces complete artifact evidence."""
    output_directory = tmp_path / 'fast'
    output_directory.mkdir()
    output_path = output_directory / 'cotahist.parquet'
    _write_b3_parquet(output_path)

    details = artifact_validation._validate_result(
        _b3_result(output_path), output_directory, 2024, 2024
    )

    assert details['valid'] is True
    assert details['record_count'] == 1
    assert details['schema'] == b3.B3_SCHEMA
    assert details['date_range'] == ('2024-01-15', '2024-01-15')
    assert details['artifacts'][0]['pyarrowReadable'] is True


def test_execute_fast_case_uses_public_mode_and_returns_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The fast case delegates to the facade and maps valid details."""
    case = _b3_case()
    public_result: dict[str, Any] = {'success': True}
    details = _mode_details()
    calls: list[tuple[Path, int, str, Path]] = []

    def fake_validate(path: Path) -> None:
        assert path == Path(case.input_path)

    def fake_execute(
        path: Path, year: int, mode: str, output_directory: Path
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        calls.append((path, year, mode, output_directory))
        return public_result, details

    monkeypatch.setattr(
        input_validation, 'validate_cotahist_input', fake_validate
    )
    monkeypatch.setattr(executor, '_execute_mode', fake_execute)

    result = b3.execute_cotahist_case(case, tmp_path / 'workspace')

    assert result['status'] == 'passed'
    assert result['recordCount'] == 2
    assert calls == [
        (
            Path(case.input_path),
            2024,
            'fast',
            tmp_path / 'workspace' / 'fast',
        )
    ]


def test_execute_fast_case_classifies_invalid_source(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Invalid source input is a functional case failure."""
    case = _b3_case()

    def reject_source(_path: Path) -> None:
        raise CotahistCatalogError('bad fixture')

    monkeypatch.setattr(
        input_validation, 'validate_cotahist_input', reject_source
    )
    result = b3.execute_cotahist_case(case, tmp_path / 'workspace')

    assert result['status'] == 'failed'
    assert 'bad fixture' in result['message']


def test_execute_fast_case_retains_public_failure_details(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A failed B3 artifact becomes a functional case failure."""
    case = _b3_case()
    monkeypatch.setattr(
        input_validation, 'validate_cotahist_input', lambda _path: None
    )
    monkeypatch.setattr(
        executor,
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
    """Parity evidence includes both exact ordered outputs."""
    case = _b3_case('parity')
    monkeypatch.setattr(
        input_validation, 'validate_cotahist_input', lambda _path: None
    )
    calls: list[str] = []

    def fake_execute(
        _path: Path, _year: int, mode: str, _output_directory: Path
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        calls.append(mode)
        return {'mode': mode}, _mode_details(artifact=f'{mode}.parquet')

    monkeypatch.setattr(executor, '_execute_mode', fake_execute)
    result = b3.execute_cotahist_case(case, tmp_path / 'workspace')

    assert result['status'] == 'passed'
    assert result['comparisonMethod'] == (
        'independent ordered raw-to-Parquet equality'
    )
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
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        details = _mode_details()
        details.update(
            valid=mode != failed_mode,
            message=message if mode == failed_mode else '',
        )
        return {'mode': mode}, details

    monkeypatch.setattr(executor, '_execute_mode', fake_execute)
    result = executor._execute_parity(case, Path(case.input_path), tmp_path)

    assert result['status'] == 'failed'
    assert result['message'] == message


@pytest.mark.parametrize(
    ('field', 'value', 'message'),
    [
        ('record_count', 3, 'fast/slow record_count mismatch'),
        ('schema', {'different': 'schema'}, 'fast/slow schema mismatch'),
        (
            'date_range',
            ('2023-01-01', '2023-01-01'),
            'fast/slow date_range mismatch',
        ),
        (
            'ordered_rows_sha256',
            'b' * 64,
            'fast/slow ordered_rows_sha256 mismatch',
        ),
    ],
)
def test_parity_rejects_cross_mode_evidence_mismatches(
    field: str, value: object, message: str
) -> None:
    """Parity rejects row, schema, date, or ordered-content drift."""
    fast_details = _mode_details()
    slow_details = {**fast_details, field: value}

    result = executor._parity_result(
        {'mode': 'fast'}, fast_details, {'mode': 'slow'}, slow_details
    )

    assert result['status'] == 'failed'
    assert result['message'] == message


def test_ordered_rows_digest_detects_row_reordering(tmp_path: Path) -> None:
    """Parity digest preserves output row order."""
    first = tmp_path / 'first.parquet'
    second = tmp_path / 'second.parquet'
    pq.write_table(pa.table({'ticker': ['B', 'A'], 'value': [2, 1]}), first)
    pq.write_table(pa.table({'ticker': ['A', 'B'], 'value': [1, 2]}), second)

    assert frozen_baseline._ordered_rows_sha256(
        first
    ) != frozen_baseline._ordered_rows_sha256(second)


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

    details = artifact_validation._validate_result(
        result_factory(output_path), output_directory, 2024, 2024
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

    details = artifact_validation._validate_result(
        _b3_result(output_path), output_directory, 2024, 2024
    )

    assert details['valid'] is False
    assert details['message'] == 'B3 output file count is not one'


def test_validate_result_reports_temporary_leaks_and_wrong_dates(
    tmp_path: Path,
) -> None:
    """Temporary files and out-of-range dates are explicit errors."""
    output_directory = tmp_path / 'output'
    output_directory.mkdir()
    output_path = output_directory / 'cotahist.parquet'
    _write_b3_parquet(output_path, year=2023)
    (output_directory / 'staging.tmp').touch()

    details = artifact_validation._validate_result(
        _b3_result(output_path), output_directory, 2024, 2024
    )

    assert details['valid'] is False
    assert 'temporary files leaked' in details['message']

    (output_directory / 'staging.tmp').unlink()
    details = artifact_validation._validate_result(
        _b3_result(output_path), output_directory, 2024, 2024
    )
    assert details['valid'] is False
    assert 'outside requested years' in details['message']


def test_validate_metadata_reports_empty_or_unreadable_outputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Low-level metadata validation classifies invalid Parquet outputs."""
    output = tmp_path / 'output.parquet'
    _write_b3_parquet(output)
    assert artifact_validation._validate_metadata(output) is None

    empty = tmp_path / 'empty.parquet'
    pq.write_table(
        pa.table({'data_pregao': pa.array([None], type=pa.date32())}), empty
    )
    assert (
        artifact_validation._validate_metadata(empty)
        == 'B3 schema version metadata is invalid'
    )

    class EmptyMetadata:
        num_rows = 0

    monkeypatch.setattr(
        artifact_validation.pq,
        'ParquetFile',
        lambda _path: SimpleNamespace(
            metadata=EmptyMetadata(), schema_arrow=pa.schema([])
        ),
    )
    assert (
        artifact_validation._validate_metadata(output)
        == 'B3 schema version metadata is invalid'
    )


def test_frozen_checksum_manifest_only_applies_to_full_supplied_range() -> (
    None
):
    """The frozen checksums pin precisely the accepted 2000-2026 set."""
    paths = tuple(
        Path(f'/data/COTAHIST_A{year}.ZIP') for year in range(2000, 2027)
    )

    assert frozen_baseline._expected_frozen_checksums(paths) is None
    checksums = frozen_baseline._expected_frozen_checksums(paths, enabled=True)

    assert checksums is not None
    assert len(checksums) == 27
    assert frozen_baseline._expected_frozen_checksums(paths[:-1]) is None
    with pytest.raises(ValueError, match='complete 2000-2026 range'):
        frozen_baseline._expected_frozen_checksums(paths[:-1], enabled=True)


def test_frozen_baseline_rejects_any_raw_oracle_drift() -> None:
    """The independently audited corpus facts remain a release oracle."""
    details = {
        'rawQuotes': 22_305_860,
        'previousSupportedRows': 22_303_577,
        'blockLotRowsByYear': {2023: 30, 2024: 346, 2025: 539, 2026: 1_368},
        'blockLotDistinctTradingCodes': 345,
        'blockLotVolumeTotal': '57359085637.97',
        'lastTradingDate': '2026-09-02',
        'intentionalExclusions': 0,
        'previousTwentyFieldsEqual': True,
    }
    frozen_baseline._validate_frozen_baseline(details)

    raw_quote_count = details['rawQuotes']
    assert isinstance(raw_quote_count, int)
    details['rawQuotes'] = raw_quote_count + 1
    with pytest.raises(
        AssertionError, match='frozen corpus acceptance mismatch'
    ):
        frozen_baseline._validate_frozen_baseline(details)


def test_case_source_paths_validates_snapshot_size_and_checksum(
    tmp_path: Path,
) -> None:
    """A manifest case cannot silently switch its frozen input file."""
    source = write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024)],
    )
    snapshot = _snapshot(source)
    case = _b3_case()
    case = ValidationCase(
        **{
            **case.__dict__,
            'input_path': str(source),
            'input_files': (snapshot,),
        }
    )
    assert frozen_baseline._case_source_paths(case) == (source.resolve(),)

    changed = ValidationInputSnapshot(
        snapshot.path, snapshot.size_bytes + 1, snapshot.sha256
    )
    bad_size = ValidationCase(**{**case.__dict__, 'input_files': (changed,)})
    with pytest.raises(ValueError, match='size changed'):
        frozen_baseline._case_source_paths(bad_size)

    bad_hash = ValidationInputSnapshot(
        snapshot.path, snapshot.size_bytes, '0' * 64
    )
    bad_checksum = ValidationCase(
        **{**case.__dict__, 'input_files': (bad_hash,)}
    )
    with pytest.raises(ValueError, match='checksum changed'):
        frozen_baseline._case_source_paths(bad_checksum)


def test_execute_multi_year_parity_forwards_the_full_source_range(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Range parity runs both modes against the same ordered inputs."""
    first = write_cotahist_zip(
        tmp_path,
        year=2023,
        records=[build_cotahist_record(year=2023)],
    )
    second = write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024)],
    )
    case = ValidationCase(
        case_id='cotahist-multi-parity-2023-2024',
        source='cotahist',
        year=2023,
        input_path=str(first),
        output_root='',
        mode='multi_parity',
        initial_year=2023,
        last_year=2024,
        input_files=(_snapshot(first), _snapshot(second)),
    )
    monkeypatch.setattr(
        input_validation, 'validate_cotahist_input', lambda _path: None
    )
    calls: list[tuple[str, tuple[Path, ...], int, int]] = []

    def fake_execute(
        _anchor: Path,
        _year: int,
        mode: str,
        _output: Path,
        *,
        source_paths,
        initial_year: int,
        last_year: int,
        frozen_baseline: bool = False,
    ):
        calls.append((mode, tuple(source_paths), initial_year, last_year))
        assert frozen_baseline is False
        return {'mode': mode}, _mode_details()

    monkeypatch.setattr(executor, '_execute_mode', fake_execute)
    result = b3.execute_cotahist_case(case, tmp_path / 'workspace')

    assert result['status'] == 'passed'
    assert [call[0] for call in calls] == ['fast', 'slow']
    assert all(
        call[1] == (first.resolve(), second.resolve()) for call in calls
    )
    assert all(call[2:] == (2023, 2024) for call in calls)


def test_multi_year_parity_rejects_missing_range_metadata(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A multi-year case cannot run without frozen inputs and boundaries."""
    case = ValidationCase(
        case_id='cotahist-multi-parity-2023-2024',
        source='cotahist',
        year=2023,
        input_path=str(tmp_path / 'COTAHIST_A2023.ZIP'),
        output_root='',
        mode='multi_parity',
    )
    monkeypatch.setattr(
        input_validation, 'validate_cotahist_input', lambda _path: None
    )

    result = b3.execute_cotahist_case(case, tmp_path / 'workspace')

    assert result['status'] == 'failed'
    assert 'lacks its range' in result['message']


def test_execute_mode_runs_facade_and_independent_reconciliation(
    tmp_path: Path,
) -> None:
    """An annual native case publishes evidence from raw reconciliation."""
    source = write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024)],
    )

    result, details = executor._execute_mode(
        source, 2024, 'fast', tmp_path / 'campaign-output'
    )

    assert result['success'] is True
    assert details['valid'] is True
    assert details['raw_reconciliation']['verifiedRows'] == 1
    assert len(details['ordered_rows_sha256']) == 64


@pytest.mark.parametrize(
    ('market', 'records', 'message'),
    [
        ('01', 1, 'invalid TPMERC'),
        ('010', 2, 'row count mismatch'),
    ],
)
def test_validate_result_rejects_invalid_frame_contents(
    tmp_path: Path, market: str, records: int, message: str
) -> None:
    """Invalid market codes and public row counters fail structural checks."""
    output_directory = tmp_path / 'output'
    output_directory.mkdir()
    output_path = output_directory / 'cotahist.parquet'
    _write_b3_parquet(output_path, market=market)

    details = artifact_validation._validate_result(
        _b3_result(output_path, records=records), output_directory, 2024, 2024
    )

    assert details['valid'] is False
    assert message in details['message']


def test_validate_result_reports_missing_and_escaped_outputs(
    tmp_path: Path,
) -> None:
    """Missing or caller-escaped artifact paths are rejected."""
    output_directory = tmp_path / 'output'
    output_directory.mkdir()
    missing = output_directory / 'missing.parquet'
    details = artifact_validation._validate_result(
        _b3_result(missing), output_directory, 2024, 2024
    )
    assert details['valid'] is False
    assert 'missing or empty' in details['message']

    escaped = tmp_path / 'outside.parquet'
    _write_b3_parquet(escaped)
    details = artifact_validation._validate_result(
        _b3_result(escaped), output_directory, 2024, 2024
    )
    assert details['valid'] is False
    assert 'escaped its directory' in details['message']


def test_validate_result_catches_frame_reader_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Readback exceptions are classified as invalid artifact evidence."""
    output_directory = tmp_path / 'output'
    output_directory.mkdir()
    output_path = output_directory / 'cotahist.parquet'
    _write_b3_parquet(output_path)
    monkeypatch.setattr(
        artifact_validation,
        '_validate_frame',
        lambda *_args: (_ for _ in ()).throw(OSError('reader failed')),
    )

    details = artifact_validation._validate_result(
        _b3_result(output_path), output_directory, 2024, 2024
    )

    assert details['valid'] is False
    assert 'reader failed' in details['message']


def test_validate_schema_and_metadata_reject_v1_contracts(
    tmp_path: Path,
) -> None:
    """An old schema version and a missing audit footer cannot pass."""
    old_schema = tmp_path / 'old-schema.parquet'
    pq.write_table(pa.table({'ticker': ['PETR4']}), old_schema)
    assert (
        artifact_validation._validate_schema(old_schema)
        == 'B3 schema differs from v2 oracle'
    )

    missing_manifest = tmp_path / 'missing-manifest.parquet'
    schema = independent_schema().with_metadata(
        {b'globaldatafinance.b3.schema_version': b'2'}
    )
    pq.write_table(
        pa.Table.from_pydict(
            {field.name: [] for field in independent_schema()}, schema=schema
        ),
        missing_manifest,
    )
    assert artifact_validation._validate_metadata(missing_manifest) == (
        'B3 integrity footer manifest is missing'
    )


def test_path_year_is_case_insensitive_and_rejects_other_names() -> None:
    """The validator recognizes only the annual COTAHIST filename contract."""
    assert frozen_baseline._path_year(Path('cotahist_a2024.txt')) == 2024
    with pytest.raises(ValueError, match='invalid COTAHIST annual filename'):
        frozen_baseline._path_year(Path('quotes.zip'))


def test_validate_result_accepts_one_file_through_symlink_ancestry(
    tmp_path: Path,
) -> None:
    """Resolved public paths agree with aliased directory glob results."""
    physical = tmp_path / 'physical'
    physical.mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(physical, target_is_directory=True)
    output_directory = alias / 'fast'
    output_directory.mkdir()
    output = output_directory / 'cotahist.parquet'
    _write_b3_parquet(output)

    details = artifact_validation._validate_result(
        _b3_result(output.resolve()), output_directory, 2024, 2024
    )

    assert details['valid'] is True
    assert details['record_count'] == 1
    assert details['artifacts'][0]['path'] == 'cotahist.parquet'


def test_symlink_directory_still_rejects_two_actual_parquets(
    tmp_path: Path,
) -> None:
    """Path normalization cannot weaken exactly-one-output validation."""
    physical = tmp_path / 'physical'
    physical.mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(physical, target_is_directory=True)
    first = physical / 'first.parquet'
    _write_b3_parquet(first)
    _write_b3_parquet(physical / 'second.parquet')

    details = artifact_validation._validate_result(
        _b3_result(first), alias, 2024, 2024
    )

    assert details == {
        'valid': False,
        'message': 'B3 output file count is not one',
    }
