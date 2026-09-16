import os
import tempfile
from pathlib import Path

import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    DownloadDocumentsUseCaseCVM,
    DownloadResultCVM,
    InvalidDocumentName,
    InvalidFirstYear,
    client,
)


class MockRepository:
    def __init__(self):
        self.download_docs_called = False
        self.last_tasks = None
        self.last_automatic_extractor = None

    def download_docs(
        self,
        tasks: list,
        *,
        automatic_extractor: bool = False,
    ) -> DownloadResultCVM:
        self.download_docs_called = True
        self.last_tasks = tasks
        self.last_automatic_extractor = automatic_extractor

        return DownloadResultCVM(successful_downloads=['DFP_2020', 'DFP_2021'])


@pytest.mark.unit
class TestDownloadDocumentsUseCaseOrchestration:
    def test_orchestrator_calls_repository(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['DFP'],
            initial_year=2020,
            last_year=2023,
        )

        assert mock_repo.download_docs_called
        assert mock_repo.last_tasks is not None
        assert isinstance(mock_repo.last_tasks, list)

    def test_orchestrator_passes_validated_data_to_repository(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['DFP', 'ITR'],
            initial_year=2020,
            last_year=2022,
        )

        assert mock_repo.last_tasks is not None
        assert len(mock_repo.last_tasks) >= 1
        for task in mock_repo.last_tasks:
            assert isinstance(task, tuple)
            assert len(task) == 4
            url, doc_name, year, dest_path = task
            assert isinstance(url, str)
            assert isinstance(doc_name, str)
            assert isinstance(year, str)
            assert isinstance(dest_path, str)

    def test_orchestrator_returns_download_result(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        result = use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['DFP'],
            initial_year=2020,
            last_year=2023,
        )

        assert isinstance(result, DownloadResultCVM)
        assert result.success_count_downloads > 0

    def test_orchestrator_creates_directory_via_validator(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            new_path = Path(tmpdir) / 'new_dir'

            mock_repo = MockRepository()
            use_case = DownloadDocumentsUseCaseCVM(mock_repo)

            use_case.execute(
                destination_path=str(new_path),
                list_docs=['DFP'],
                initial_year=2020,
                last_year=2020,
            )

            assert new_path.exists()

    def test_orchestrator_generates_correct_tasks(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['DFP'],
            initial_year=2020,
            last_year=2021,
        )

        assert len(mock_repo.last_tasks) == 2

        for task in mock_repo.last_tasks:
            url, doc_name, year, dest_path = task
            assert 'dados.cvm.gov.br' in url
            assert doc_name == 'DFP'
            assert year in ['2020', '2021']
            assert dest_path.startswith(str(tmp_path))

    def test_orchestrator_respects_year_constraints_for_itr(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['ITR'],
            initial_year=2010,
            last_year=2012,
        )

        assert len(mock_repo.last_tasks) == 2
        years_in_tasks = [task[2] for task in mock_repo.last_tasks]
        assert '2011' in years_in_tasks
        assert '2012' in years_in_tasks
        assert '2010' not in years_in_tasks

    def test_orchestrator_respects_year_constraints_for_cgvn(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['CGVN'],
            initial_year=2016,
            last_year=2019,
        )

        assert len(mock_repo.last_tasks) == 2
        years_in_tasks = [task[2] for task in mock_repo.last_tasks]
        assert '2018' in years_in_tasks
        assert '2019' in years_in_tasks
        assert '2016' not in years_in_tasks
        assert '2017' not in years_in_tasks


@pytest.mark.unit
class TestDownloadDocumentsUseCaseBackwardCompatibility:
    def test_same_interface_as_before(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        result = use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['DFP'],
            initial_year=2020,
            last_year=2023,
        )

        assert isinstance(result, DownloadResultCVM)

    def test_handles_none_doc_types(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        result = use_case.execute(
            destination_path=str(tmp_path),
            list_docs=None,
            initial_year=2020,
            last_year=2020,
        )

        assert isinstance(result, DownloadResultCVM)
        assert len(mock_repo.last_tasks) > 1

    def test_handles_none_years(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        result = use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['DFP'],
            initial_year=None,
            last_year=None,
        )

        assert isinstance(result, DownloadResultCVM)
        assert mock_repo.download_docs_called

    def test_creates_directory_if_not_exists(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            new_path = Path(tmpdir) / 'new_dir'

            mock_repo = MockRepository()
            use_case = DownloadDocumentsUseCaseCVM(mock_repo)

            use_case.execute(
                destination_path=str(new_path),
                list_docs=['DFP'],
                initial_year=2020,
                last_year=2020,
            )

            assert new_path.exists()


@pytest.mark.unit
class TestDownloadDocumentsUseCaseErrorHandling:
    def test_validation_error_stops_execution(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        with pytest.raises(InvalidDocumentName):
            use_case.execute(
                destination_path=str(tmp_path),
                list_docs=['INVALID'],
                initial_year=2020,
                last_year=2023,
            )

        assert not mock_repo.download_docs_called

    def test_invalid_year_error_stops_execution(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        with pytest.raises(InvalidFirstYear):
            use_case.execute(
                destination_path=str(tmp_path),
                list_docs=['DFP'],
                initial_year=1990,
                last_year=2020,
            )

        assert not mock_repo.download_docs_called

    def test_repository_error_is_propagated(self, tmp_path):
        class ErrorRepository:
            def download_docs(
                self,
                tasks,
                *,
                automatic_extractor=False,
            ):
                _ = tasks, automatic_extractor
                raise RuntimeError('Download failed')

        error_repo = ErrorRepository()
        use_case = DownloadDocumentsUseCaseCVM(error_repo)

        with pytest.raises(RuntimeError, match='Download failed'):
            use_case.execute(
                destination_path=str(tmp_path),
                list_docs=['DFP'],
                initial_year=2020,
                last_year=2020,
            )


@pytest.mark.unit
class TestDownloadDocumentsUseCaseInitialization:
    def test_constructor_repository_is_used_by_public_execute(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        result = use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['DFP'],
            initial_year=2020,
            last_year=2020,
        )

        assert isinstance(result, DownloadResultCVM)
        assert mock_repo.download_docs_called


@pytest.mark.unit
class TestDownloadDocumentsUseCaseLogging:
    def test_logs_orchestration_start(self, tmp_path, caplog):
        import logging

        caplog.set_level(logging.INFO)

        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['DFP'],
            initial_year=2020,
            last_year=2020,
        )

        assert any(
            'orchestration' in record.message.lower()
            for record in caplog.records
        )

    def test_logs_download_completion(self, tmp_path, caplog):
        import logging

        caplog.set_level(logging.INFO)

        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['DFP'],
            initial_year=2020,
            last_year=2020,
        )

        assert any(
            'completed' in record.message.lower() for record in caplog.records
        )


@pytest.mark.unit
class TestDownloadDocumentsUseCaseIntegrationWithRealSubUseCases:
    def test_full_integration_with_real_sub_use_cases(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        result = use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['DFP'],
            initial_year=2022,
            last_year=2023,
        )

        assert isinstance(result, DownloadResultCVM)

        assert len(mock_repo.last_tasks) == 2

        for task in mock_repo.last_tasks:
            url, doc_name, year, _dest_path = task
            assert 'dados.cvm.gov.br' in url
            assert doc_name == 'DFP'
            assert year in ['2022', '2023']

    def test_integration_with_multiple_docs_and_years(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        result = use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['DFP', 'ITR', 'FRE'],
            initial_year=2020,
            last_year=2022,
        )

        assert isinstance(result, DownloadResultCVM)

        assert len(mock_repo.last_tasks) == 9

        doc_names = {task[1] for task in mock_repo.last_tasks}
        assert doc_names == {'DFP', 'ITR', 'FRE'}


@pytest.mark.unit
class TestDownloadDocumentsUseCaseTaskPreparation:
    def test_tasks_contain_correct_structure(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['DFP'],
            initial_year=2020,
            last_year=2020,
        )

        assert len(mock_repo.last_tasks) == 1
        task = mock_repo.last_tasks[0]

        assert isinstance(task, tuple)
        assert len(task) == 4

        url, doc_name, year, dest_path = task
        assert isinstance(url, str) and url.startswith('https://')
        assert isinstance(doc_name, str) and doc_name == 'DFP'
        assert isinstance(year, str) and year == '2020'
        assert isinstance(dest_path, str) and Path(dest_path).is_absolute()

    def test_tasks_match_years_from_docs_paths(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['ITR'],
            initial_year=2010,
            last_year=2012,
        )

        years_in_tasks = [task[2] for task in mock_repo.last_tasks]
        assert '2011' in years_in_tasks
        assert '2012' in years_in_tasks
        assert '2010' not in years_in_tasks
        assert len(years_in_tasks) == 2

    def test_tasks_urls_match_years(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['DFP'],
            initial_year=2020,
            last_year=2021,
        )

        for task in mock_repo.last_tasks:
            url, _doc_name, year, _dest_path = task
            assert year in url, f'Year {year} should be in URL {url}'

    def test_tasks_destination_paths_are_valid(self, tmp_path):
        """Destination paths in tasks should exist and be writable."""
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['DFP'],
            initial_year=2020,
            last_year=2021,
        )

        for task in mock_repo.last_tasks:
            _url, _doc_name, _year, dest_path = task
            assert Path(dest_path).exists()
            assert Path(dest_path).is_dir()
            assert os.access(dest_path, os.W_OK)

    def test_tasks_with_all_document_types(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        all_docs = ['CGVN', 'FRE', 'FCA', 'DFP', 'ITR', 'IPE', 'VLMO']

        use_case.execute(
            destination_path=str(tmp_path),
            list_docs=all_docs,
            initial_year=2020,
            last_year=2020,
        )

        doc_names_in_tasks = {task[1] for task in mock_repo.last_tasks}
        assert len(doc_names_in_tasks) >= 5

    def test_task_urls_contain_correct_doc_type(self, tmp_path):
        """URL should contain the correct document type identifier."""
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['DFP', 'ITR'],
            initial_year=2020,
            last_year=2020,
        )

        for task in mock_repo.last_tasks:
            url, doc_name, _year, _dest_path = task
            # URL should contain the doc name in lowercase
            assert doc_name.lower() in url.lower()

    def test_task_urls_end_with_zip(self, tmp_path):
        """All task URLs should end with .zip extension."""
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['DFP'],
            initial_year=2020,
            last_year=2021,
        )

        for task in mock_repo.last_tasks:
            url, _doc_name, _year, _dest_path = task
            assert url.endswith('.zip')

    def test_tasks_for_multiple_years_ordered_correctly(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['DFP'],
            initial_year=2018,
            last_year=2022,
        )

        dfp_years = [
            int(task[2]) for task in mock_repo.last_tasks if task[1] == 'DFP'
        ]

        assert len(dfp_years) == 5
        assert min(dfp_years) == 2018
        assert max(dfp_years) == 2022

    def test_tasks_preserve_absolute_paths(self, tmp_path):
        """All destination paths in tasks should be absolute."""
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['DFP'],
            initial_year=2020,
            last_year=2020,
        )

        for task in mock_repo.last_tasks:
            _url, _doc_name, _year, dest_path = task
            assert Path(dest_path).is_absolute()

    def test_empty_tasks_when_no_valid_years(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        result = use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['CGVN'],
            initial_year=2010,
            last_year=2017,
        )

        assert isinstance(result, DownloadResultCVM)
        assert len(mock_repo.last_tasks) == 0

    def test_tasks_count_matches_valid_years_count(self, tmp_path):
        mock_repo = MockRepository()
        use_case = DownloadDocumentsUseCaseCVM(mock_repo)

        use_case.execute(
            destination_path=str(tmp_path),
            list_docs=['DFP', 'ITR'],
            initial_year=2020,
            last_year=2022,
        )

        assert len(mock_repo.last_tasks) == 6


class MockRepositoryWithFailures:
    def download_docs(
        self,
        tasks: list,
        *,
        automatic_extractor: bool = False,
    ) -> DownloadResultCVM:
        _ = tasks, automatic_extractor
        return DownloadResultCVM(
            successful_downloads=['DFP_2020'],
            failed_downloads={'DFP_2021': 'connection reset'},
        )


@pytest.mark.unit
class TestDownloadDocumentsUseCaseTaskPreparationGaps:
    def test_missing_download_url_raises_through_execute(
        self, tmp_path, monkeypatch
    ):
        from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
            MissingDownloadUrlError,
        )

        monkeypatch.setattr(
            client,
            'generate_range_years',
            lambda **_kwargs: range(2020, 2021),
        )
        monkeypatch.setattr(
            client,
            'generate_urls',
            lambda **_kwargs: ({}, {'DFP'}),
        )
        use_case = DownloadDocumentsUseCaseCVM(MockRepository())

        with pytest.raises(MissingDownloadUrlError):
            use_case.execute(
                destination_path=str(tmp_path),
                list_docs=['DFP'],
                initial_year=2020,
                last_year=2020,
            )

    def test_no_url_match_for_year_logs_warning_through_execute(
        self, tmp_path, monkeypatch, caplog
    ):
        monkeypatch.setattr(
            client,
            'generate_range_years',
            lambda **_kwargs: range(2020, 2021),
        )
        monkeypatch.setattr(
            client,
            'generate_urls',
            lambda **_kwargs: ({'DFP': ['http://x/dfp_1999.zip']}, {'DFP'}),
        )
        use_case = DownloadDocumentsUseCaseCVM(MockRepository())

        with caplog.at_level('WARNING'):
            result = use_case.execute(
                destination_path=str(tmp_path),
                list_docs=['DFP'],
                initial_year=2020,
                last_year=2020,
            )

        assert isinstance(result, DownloadResultCVM)
        assert any(
            'No URL found for DFP_2020' in record.message
            for record in caplog.records
        )


@pytest.mark.unit
class TestDownloadDocumentsUseCaseFailureLogging:
    def test_logs_failed_downloads_when_repository_reports_errors(
        self, tmp_path, caplog
    ):
        use_case = DownloadDocumentsUseCaseCVM(MockRepositoryWithFailures())

        with caplog.at_level('WARNING'):
            result = use_case.execute(
                destination_path=str(tmp_path),
                list_docs=['DFP'],
                initial_year=2020,
                last_year=2021,
            )

        assert result.error_count_downloads == 1
        assert any(
            'Failed downloads' in record.message
            and 'connection reset' in record.message
            for record in caplog.records
        )
