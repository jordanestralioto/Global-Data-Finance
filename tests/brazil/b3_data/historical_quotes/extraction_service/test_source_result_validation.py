"""Worker evidence must match preflight before any artifact is published."""

from __future__ import annotations

import os
from dataclasses import replace
from pathlib import Path

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes import (
    CotahistParserB3,
    ExtractionServiceB3,
    extraction_service,
)
from globaldatafinance.brazil.b3_data.historical_quotes.catalog import (
    resolve_cotahist_sources,
)
from globaldatafinance.brazil.b3_data.historical_quotes.parquet_writer import (
    schema as b3_schema,
)
from globaldatafinance.brazil.b3_data.historical_quotes.processing import (
    ProcessingModeEnumB3,
)
from globaldatafinance.brazil.b3_data.historical_quotes.zip_reader import (
    ZipFileReaderB3,
)
from globaldatafinance.macro_exceptions import ExtractionError
from globaldatafinance.macro_infra.transactional_publication.locking import (
    WINDOWS_GUARD_NAME,
)
from tests.support.builders import build_cotahist_record, write_cotahist_txt

pytestmark = pytest.mark.integration


_VIOLATIONS = [
    ('selected_records', 'parser/write count invariant'),
    ('parsed_vs_written', 'parser/write count invariant'),
    ('written_records', 'parser/write count invariant'),
    ('source_count', 'parser/write count invariant'),
    ('descriptor', 'different validated source descriptor'),
    ('digest', 'row digest differs from source preflight'),
    ('schema', 'logical schema fingerprint mismatch'),
]


def _alter_result(
    result: extraction_service.types.SourceExtractionResult, violation: str
) -> extraction_service.types.SourceExtractionResult:
    """Damage one invariant after the real worker has finished."""
    if violation == 'selected_records':
        return replace(result, selected_records=0)
    if violation == 'parsed_vs_written':
        return replace(result, selected_records=0, parsed_records=0)
    if violation == 'written_records':
        return replace(result, written_records=0)
    if violation == 'source_count':
        return replace(
            result, source=replace(result.source, selected_quotes=0)
        )
    if violation == 'descriptor':
        return replace(
            result, source=replace(result.source, outer_sha256='0' * 64)
        )
    if violation == 'digest':
        return replace(result, parsed_rows_sha256='0' * 64)
    if violation == 'schema':
        return replace(result, schema_fingerprint='0' * 64)
    raise ValueError(violation)


@pytest.fixture
def worker_result(
    tmp_path: Path,
) -> extraction_service.types.SourceExtractionResult:
    """Produce evidence with the real preflight, parser and Arrow writer."""
    path = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024, ticker='PETR4')],
    )
    source = resolve_cotahist_sources(
        tmp_path,
        expected_years={2024},
        target_tpmerc_codes={'010'},
        all_markets=False,
    ).sources[0]
    return extraction_service.ZipProcessorB3(ZipFileReaderB3()).process(
        path,
        {'010'},
        tmp_path / 'worker.parquet',
        source_descriptor=source,
    )


@pytest.mark.parametrize(('violation', 'message'), _VIOLATIONS)
def test_rejects_worker_evidence_that_disagrees_with_preflight(
    worker_result: extraction_service.types.SourceExtractionResult,
    violation: str,
    message: str,
) -> None:
    """Counts, source identity, content and schema each enforce rejection."""
    fingerprint = b3_schema.schema_fingerprint(b3_schema.build_b3_schema())
    altered = _alter_result(worker_result, violation)

    with pytest.raises(ExtractionError, match=message) as raised:
        extraction_service.service.execution.validate_source_results(
            [altered], fingerprint, (worker_result.source,)
        )

    assert raised.value.path == worker_result.source_path.name


@pytest.mark.parametrize('result_count', [0, 2])
def test_rejects_missing_or_extra_worker_results(
    worker_result: extraction_service.types.SourceExtractionResult,
    result_count: int,
) -> None:
    """Every requested source must contribute exactly one result."""
    with pytest.raises(ExtractionError, match='Not every validated source'):
        extraction_service.service.execution.validate_source_results(
            [worker_result] * result_count,
            b3_schema.schema_fingerprint(b3_schema.build_b3_schema()),
            (worker_result.source,),
        )


@pytest.mark.parametrize('selected', [True, False])
def test_accepts_valid_worker_results_including_fully_filtered_sources(
    tmp_path: Path, selected: bool
) -> None:
    """Zero selected rows legitimately have no private Parquet artifact."""
    path = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(market='010' if selected else '070')],
    )
    source = resolve_cotahist_sources(
        tmp_path,
        expected_years={2024},
        target_tpmerc_codes={'010'},
        all_markets=False,
    ).sources[0]
    result = extraction_service.ZipProcessorB3(ZipFileReaderB3()).process(
        path, {'010'}, tmp_path / 'worker.parquet', source_descriptor=source
    )

    extraction_service.service.execution.validate_source_results(
        [result],
        b3_schema.schema_fingerprint(b3_schema.build_b3_schema()),
        (source,),
    )

    assert result.written_records == int(selected)
    assert (result.temp_path is not None) is selected
    assert result.parsed_rows_sha256 == source.expected_rows_sha256


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ('violation', 'message'),
    [('missing', 'Not every validated source'), *_VIOLATIONS],
)
async def test_rejected_worker_results_preserve_output_and_clean_staging(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    violation: str,
    message: str,
) -> None:
    """Untrusted worker evidence is rejected before the transaction commits."""
    path = write_cotahist_txt(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024, ticker='PETR4')],
    )
    source_before = path.read_bytes()
    output = tmp_path / 'quotes.parquet'
    output.write_bytes(b'previous output')
    service = ExtractionServiceB3(
        ZipFileReaderB3(), CotahistParserB3(), ProcessingModeEnumB3.SLOW
    )
    run_sources = service._run_sources

    async def alter_completed_results(*args, **kwargs):
        state = await run_sources(*args, **kwargs)
        if violation == 'missing':
            state.results.clear()
        else:
            state.results[0] = _alter_result(state.results[0], violation)
        return state

    monkeypatch.setattr(service, '_run_sources', alter_completed_results)

    result = await service.extract_from_zip_files({str(path)}, {'010'}, output)

    assert result['success_count'] == 0
    assert result['error_count'] == 1
    assert result['output_file'] == ''
    assert result['integrity']['status'] == 'failed'
    assert any(message in error for error in result['errors'].values())
    assert output.read_bytes() == b'previous output'
    assert path.read_bytes() == source_before
    expected = {path, output}
    if os.name == 'nt':
        guard = tmp_path / WINDOWS_GUARD_NAME
        assert guard.is_file() and guard.read_bytes() == b''
        expected.add(guard)
    assert set(tmp_path.iterdir()) == expected
