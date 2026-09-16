"""Orchestration-focused unit tests for the public B3 facade."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from globaldatafinance.application.b3_docs import HistoricalQuotesB3
from globaldatafinance.application.b3_docs import (
    historical_quotes as facade_module,
)

pytestmark = pytest.mark.unit


def _raw_result(*, error_count: int = 0) -> dict[str, object]:
    """Return a service-shaped result whose enrichment remains observable."""
    return {
        'total_files': 2,
        'success_count': 2 - error_count,
        'error_count': error_count,
        'total_records': 321,
        'output_file': '/output/quotes.parquet',
        'errors': {'input.zip': 'bad member'} if error_count else {},
    }


def _docs_to_extract() -> Mock:
    """Return a minimal prepared request observable by the facade."""
    docs = Mock(name='docs_to_extract')
    docs.documents_to_download = [object()]
    return docs


def test_initialization_and_reference_queries_have_public_contract() -> None:
    """The facade exposes stable identity and source metadata entrypoints."""
    b3 = HistoricalQuotesB3()

    assert repr(b3) == 'HistoricalQuotesB3()'
    assert {'ações', 'etf'}.issubset(b3.get_available_assets())
    assert b3.get_available_years()['minimal_year'] == 1986


@patch.object(facade_module, 'CreateDocsToExtractUseCaseB3')
@patch.object(facade_module, 'ExtractHistoricalQuotesUseCaseB3')
def test_extract_forwards_normalized_arguments_and_enriches_result(
    extract_constructor: Mock,
    create_docs_constructor: Mock,
) -> None:
    """The sync facade normalizes output then awaits the use case once."""
    docs = _docs_to_extract()
    create_docs_constructor.return_value.execute.return_value = docs
    extract_use_case = Mock()
    extract_use_case.execute = AsyncMock(return_value=_raw_result())
    extract_constructor.return_value = extract_use_case
    b3 = HistoricalQuotesB3()

    result = b3.extract(
        path_of_docs='/data/cotahist',
        destination_path='/output',
        assets_list=['ações', 'etf'],
        initial_year=2020,
        last_year=2023,
        output_filename='quotes',
        processing_mode='FAST',
        verbose=False,
    )

    create_docs_constructor.assert_called_once_with(
        path_of_docs='/data/cotahist',
        assets_list=['ações', 'etf'],
        initial_year=2020,
        last_year=2023,
        destination_path='/output',
        allowed_unc_roots=(),
    )
    extract_use_case.execute.assert_awaited_once_with(
        docs_to_extract=docs,
        processing_mode='fast',
        output_filename='quotes.parquet',
    )
    assert result['success'] is True
    assert result['assets'] == ['ações', 'etf']
    assert result['processing_mode'] == 'fast'
    assert result['output_file'] == '/output/quotes.parquet'
    assert result['message'].startswith('Successfully extracted 321 records')


@pytest.mark.asyncio
@patch.object(facade_module, 'CreateDocsToExtractUseCaseB3')
@patch.object(facade_module, 'ExtractHistoricalQuotesUseCaseB3')
async def test_extract_async_applies_defaults_and_preserves_error(
    extract_constructor: Mock,
    create_docs_constructor: Mock,
) -> None:
    """The async facade applies default years and returns an error result."""
    docs = _docs_to_extract()
    create_docs_constructor.return_value.execute.return_value = docs
    extract_use_case = Mock()
    extract_use_case.execute = AsyncMock(
        return_value=_raw_result(error_count=1)
    )
    extract_constructor.return_value = extract_use_case
    b3 = HistoricalQuotesB3()
    b3._available_years_use_case = Mock(
        get_minimal_year=Mock(return_value=1986),
        get_current_year=Mock(return_value=2026),
    )

    result = await b3.extract_async(
        path_of_docs='/data/cotahist',
        assets_list=['ações'],
        output_filename='already.parquet',
        processing_mode='slow',
        verbose=False,
    )

    create_docs_constructor.assert_called_once_with(
        path_of_docs='/data/cotahist',
        assets_list=['ações'],
        initial_year=1986,
        last_year=2026,
        destination_path=None,
        allowed_unc_roots=(),
    )
    extract_use_case.execute.assert_awaited_once_with(
        docs_to_extract=docs,
        processing_mode='slow',
        output_filename='already.parquet',
    )
    assert result['success'] is False
    assert result['error_count'] == 1
    assert result['errors'] == {'input.zip': 'bad member'}
    assert result['message'].startswith('Extraction completed with errors')


@patch.object(facade_module, 'CreateDocsToExtractUseCaseB3')
@patch.object(facade_module, 'ExtractHistoricalQuotesUseCaseB3')
def test_extract_formats_only_when_verbose(
    extract_constructor: Mock,
    create_docs_constructor: Mock,
) -> None:
    """The presentation collaborator is conditional, not part of extraction."""
    docs = _docs_to_extract()
    create_docs_constructor.return_value.execute.return_value = docs
    extract_use_case = Mock()
    extract_use_case.execute = AsyncMock(return_value=_raw_result())
    extract_constructor.return_value = extract_use_case
    b3 = HistoricalQuotesB3()
    formatter = Mock()
    b3._result_formatter = formatter

    b3.extract(
        path_of_docs='/data/cotahist',
        assets_list=['ações'],
        initial_year=2024,
        verbose=False,
    )
    b3.extract(
        path_of_docs='/data/cotahist',
        assets_list=['ações'],
        initial_year=2024,
        verbose=True,
    )

    assert extract_use_case.execute.await_count == 2
    formatter.print_result.assert_called_once()
    printed_result = formatter.print_result.call_args.args[0]
    assert printed_result['processing_mode'] == 'fast'


@pytest.mark.asyncio
@patch.object(facade_module, 'CreateDocsToExtractUseCaseB3')
@patch.object(facade_module, 'ExtractHistoricalQuotesUseCaseB3')
async def test_extract_async_propagates_use_case_error_once(
    extract_constructor: Mock,
    create_docs_constructor: Mock,
) -> None:
    """A delegated failure remains visible instead of becoming success."""
    docs = _docs_to_extract()
    create_docs_constructor.return_value.execute.return_value = docs
    extract_use_case = Mock()
    extract_use_case.execute = AsyncMock(
        side_effect=RuntimeError('storage unavailable')
    )
    extract_constructor.return_value = extract_use_case
    b3 = HistoricalQuotesB3()

    with pytest.raises(RuntimeError, match='storage unavailable'):
        await b3.extract_async(
            path_of_docs='/data/cotahist',
            assets_list=['ações'],
            initial_year=2024,
            verbose=False,
        )

    extract_use_case.execute.assert_awaited_once_with(
        docs_to_extract=docs,
        processing_mode='fast',
        output_filename='cotahist_extracted.parquet',
    )
