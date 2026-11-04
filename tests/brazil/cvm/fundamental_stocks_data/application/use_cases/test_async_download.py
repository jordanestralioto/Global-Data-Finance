"""Tests for the async download surface added in Phase 5.

Covers the three layers of the async path:
- adapter ``CvmDownloadAdapter.async_download_docs`` (+ the sync
  ``download_docs`` wrapper),
- orchestrator ``DownloadDocumentsUseCaseCVM.execute_async``,
- facade ``FundamentalStocksDataCVM.async_download``.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from globaldatafinance import FundamentalStocksDataCVM
from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    DownloadDocumentsUseCaseCVM,
    InvalidDocumentName,
)
from globaldatafinance.brazil.cvm.ingestion.http import CvmDownloadAdapter
from globaldatafinance.brazil.cvm.ingestion.models import DownloadResultCVM

pytestmark = pytest.mark.unit


def _make_adapter() -> CvmDownloadAdapter:
    return CvmDownloadAdapter(file_extractor_repository=MagicMock())


@pytest.mark.asyncio
class TestAsyncDownloadDocsAdapter:
    async def test_empty_tasks_return_empty_result(self):
        adapter = _make_adapter()

        result = await adapter.async_download_docs([])

        assert isinstance(result, DownloadResultCVM)
        assert result.success_count_downloads == 0
        assert result.error_count_downloads == 0

    async def test_records_successes_from_download_path(self):
        adapter = _make_adapter()

        async def fake_download_and_extract(
            _url, _dest_path, doc_name, year, result, _progress_bar, **_kwargs
        ):
            result.add_success_downloads(f'{doc_name}_{year}')

        adapter._download_and_extract = fake_download_and_extract

        tasks = [
            (
                'https://example.com/dfp_2020.zip',
                'DFP',
                '2020',
                'test-data/out',
            ),
            (
                'https://example.com/dfp_2021.zip',
                'DFP',
                '2021',
                'test-data/out',
            ),
        ]

        result = await adapter.async_download_docs(tasks)

        assert result.success_count_downloads == 2
        assert 'DFP_2020' in result.successful_downloads
        assert 'DFP_2021' in result.successful_downloads

    async def test_automatic_extractor_param_overrides_attribute(self):
        adapter = _make_adapter()
        assert adapter.automatic_extractor is False

        adapter._run_downloads = AsyncMock()
        tasks = [('https://example.com/x.zip', 'DFP', '2020', 'test-data/out')]

        await adapter.async_download_docs(tasks, automatic_extractor=True)

        adapter._run_downloads.assert_awaited_once()
        assert (
            adapter._run_downloads.await_args.kwargs['automatic_extractor']
            is True
        )

    async def test_automatic_extractor_defaults_to_attribute(self):
        adapter = CvmDownloadAdapter(
            file_extractor_repository=MagicMock(),
            automatic_extractor=True,
        )
        adapter._run_downloads = AsyncMock()
        tasks = [('https://example.com/x.zip', 'DFP', '2020', 'test-data/out')]

        await adapter.async_download_docs(tasks)

        assert (
            adapter._run_downloads.await_args.kwargs['automatic_extractor']
            is True
        )


@pytest.mark.unit
class TestDownloadDocsSyncWrapper:
    def test_sync_download_docs_wraps_async(self):
        adapter = _make_adapter()
        sentinel = DownloadResultCVM(successful_downloads=['DFP_2020'])
        adapter.async_download_docs = AsyncMock(return_value=sentinel)

        result = adapter.download_docs([], automatic_extractor=True)

        assert result is sentinel
        adapter.async_download_docs.assert_awaited_once()
        assert (
            adapter.async_download_docs.await_args.kwargs[
                'automatic_extractor'
            ]
            is True
        )


class _FakeAsyncRepository:
    """Repository double exposing only the async entrypoint."""

    def __init__(self, result: DownloadResultCVM | None = None):
        self.result = result or DownloadResultCVM()
        self.called = False
        self.received_automatic_extractor: bool | None = None

    async def async_download_docs(
        self, tasks, *, automatic_extractor=False
    ) -> DownloadResultCVM:
        _ = tasks
        self.called = True
        self.received_automatic_extractor = automatic_extractor
        return self.result


@pytest.mark.asyncio
class TestExecuteAsyncOrchestrator:
    async def test_execute_async_awaits_repository(self, tmp_path):
        expected = DownloadResultCVM(successful_downloads=['DFP_2020'])
        repo = _FakeAsyncRepository(expected)
        use_case = DownloadDocumentsUseCaseCVM(repo)

        result = await use_case.execute_async(
            destination_path=str(tmp_path),
            list_docs=['DFP'],
            initial_year=2020,
            last_year=2020,
            automatic_extractor=True,
        )

        assert repo.called is True
        assert repo.received_automatic_extractor is True
        assert result is expected
        assert result.elapsed_time >= 0

    async def test_execute_async_validation_error_stops(self, tmp_path):
        repo = _FakeAsyncRepository()
        use_case = DownloadDocumentsUseCaseCVM(repo)

        with pytest.raises(InvalidDocumentName):
            await use_case.execute_async(
                destination_path=str(tmp_path),
                list_docs=['INVALID'],
                initial_year=2020,
                last_year=2020,
            )

        assert repo.called is False

    async def test_execute_async_propagates_repository_error(self, tmp_path):
        class ErrorRepository:
            async def async_download_docs(
                self, tasks, *, automatic_extractor=False
            ):
                _ = tasks, automatic_extractor
                raise RuntimeError('async download failed')

        use_case = DownloadDocumentsUseCaseCVM(ErrorRepository())

        with pytest.raises(RuntimeError, match='async download failed'):
            await use_case.execute_async(
                destination_path=str(tmp_path),
                list_docs=['DFP'],
                initial_year=2020,
                last_year=2020,
            )


@pytest.mark.asyncio
class TestFacadeAsyncDownload:
    async def test_async_download_returns_result(self, tmp_path):
        cvm = FundamentalStocksDataCVM()
        expected = DownloadResultCVM(successful_downloads=['DFP_2020'])
        cvm.download_adapter.async_download_docs = AsyncMock(
            return_value=expected
        )

        result = await cvm.async_download(
            destination_path=str(tmp_path),
            list_docs=['DFP'],
            initial_year=2020,
            last_year=2020,
        )

        assert result is expected
        assert result.success_count_downloads == 1
        cvm.download_adapter.async_download_docs.assert_awaited_once()

    async def test_async_download_rejects_non_bool_extractor(self, tmp_path):
        cvm = FundamentalStocksDataCVM()

        with pytest.raises(TypeError):
            await cvm.async_download(
                destination_path=str(tmp_path),
                list_docs=['DFP'],
                initial_year=2020,
                last_year=2020,
                automatic_extractor='yes',  # type: ignore[arg-type]
            )
