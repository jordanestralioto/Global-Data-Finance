import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    EmptyDocumentListError,
    VerifyPathsUseCasesCVM,
)
from globaldatafinance.macro_exceptions import SecurityError


@pytest.mark.unit
class TestVerifyPathsUseCasesInitialization:
    def test_initialization_with_valid_parameters(self, tmp_path):
        new_set_docs = {'DFP', 'ITR'}
        range_years = range(2020, 2024)

        use_case_instance = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs=new_set_docs,
            range_years=range_years,
        )

        assert use_case_instance is not None
        assert use_case_instance.destination_path == str(tmp_path)
        assert use_case_instance.new_set_docs == new_set_docs
        assert use_case_instance.range_years == range_years

    def test_initialization_validates_destination_path(self, tmp_path):
        new_set_docs = {'DFP'}
        range_years = range(2020, 2024)

        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs=new_set_docs,
            range_years=range_years,
        )

        assert use_case.destination_path == str(tmp_path)

    def test_initialization_with_empty_doc_set_raises_error(self, tmp_path):
        with pytest.raises(EmptyDocumentListError):
            VerifyPathsUseCasesCVM(
                destination_path=str(tmp_path),
                new_set_docs=set(),
                range_years=range(2020, 2024),
            )

    def test_initialization_logs_debug_message(self, tmp_path, caplog):
        with caplog.at_level(logging.DEBUG):
            VerifyPathsUseCasesCVM(
                destination_path=str(tmp_path),
                new_set_docs={'DFP'},
                range_years=range(2020, 2024),
            )

        assert any(
            'created' in record.message.lower() for record in caplog.records
        )


@pytest.mark.unit
class TestVerifyPathsUseCasesExecute:
    @pytest.mark.parametrize(
        'blocked_path',
        ['/', 'D:\\', 'D:\\Windows', '\\\\server\\share\\output'],
    )
    def test_execute_blocks_unsafe_destination_before_directory_creation(
        self,
        blocked_path,
    ):
        """The CVM entrypoint rejects dangerous raw destinations first."""
        use_case = VerifyPathsUseCasesCVM(
            destination_path=blocked_path,
            new_set_docs={'DFP'},
            range_years=range(2024, 2025),
        )

        with (
            patch.object(Path, 'mkdir') as mkdir,
            pytest.raises(SecurityError),
        ):
            use_case.execute()

        mkdir.assert_not_called()

    def test_execute_creates_doc_subdirectories(self, tmp_path):
        new_set_docs = {'DFP', 'ITR'}
        range_years = range(2020, 2022)

        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs=new_set_docs,
            range_years=range_years,
        )

        use_case.execute()

        for doc in new_set_docs:
            doc_path = tmp_path / doc
            assert doc_path.exists()
            assert doc_path.is_dir()

    def test_execute_creates_year_subdirectories(self, tmp_path):
        new_set_docs = {'DFP'}
        range_years = range(2020, 2023)

        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs=new_set_docs,
            range_years=range_years,
        )

        use_case.execute()

        for doc in new_set_docs:
            for year in range_years:
                year_path = tmp_path / doc / str(year)
                assert year_path.exists()
                assert year_path.is_dir()

    def test_execute_creates_complete_directory_structure(self, tmp_path):
        new_set_docs = {'DFP', 'ITR', 'FRE'}
        range_years = range(2020, 2024)

        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs=new_set_docs,
            range_years=range_years,
        )

        use_case.execute()

        for doc in new_set_docs:
            for year in range_years:
                path = tmp_path / doc / str(year)
                assert path.exists()

    def test_execute_returns_docs_paths(self, tmp_path):
        new_set_docs = {'DFP', 'ITR'}
        range_years = range(2020, 2022)

        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs=new_set_docs,
            range_years=range_years,
        )

        docs_paths = use_case.execute()

        assert isinstance(docs_paths, dict)
        assert len(docs_paths) == 2

        for doc in new_set_docs:
            assert doc in docs_paths
            assert isinstance(docs_paths[doc], dict)

    def test_execute_docs_paths_has_correct_structure(self, tmp_path):
        new_set_docs = {'DFP'}
        range_years = range(2020, 2023)

        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs=new_set_docs,
            range_years=range_years,
        )

        docs_paths = use_case.execute()

        assert 'DFP' in docs_paths
        for year in range_years:
            assert year in docs_paths['DFP']
            assert isinstance(docs_paths['DFP'][year], str)
            assert Path(docs_paths['DFP'][year]).is_absolute()

    def test_execute_handles_existing_directories(self, tmp_path):
        new_set_docs = {'DFP'}
        range_years = range(2020, 2022)

        for doc in new_set_docs:
            for year in range_years:
                (tmp_path / doc / str(year)).mkdir(parents=True, exist_ok=True)

        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs=new_set_docs,
            range_years=range_years,
        )

        use_case.execute()

        assert (tmp_path / 'DFP' / '2020').exists()

    def test_execute_logs_success_message(self, tmp_path, caplog):
        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs={'DFP'},
            range_years=range(2020, 2022),
        )

        with caplog.at_level(logging.DEBUG):
            use_case.execute()

        assert any(
            'created successfully' in record.message.lower()
            for record in caplog.records
        )

    def test_execute_with_single_doc_single_year(self, tmp_path):
        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs={'DFP'},
            range_years=range(2023, 2024),
        )

        docs_paths = use_case.execute()

        assert (tmp_path / 'DFP' / '2023').exists()
        assert len(docs_paths) == 1
        assert len(docs_paths['DFP']) == 1

    def test_execute_with_many_docs_and_years(self, tmp_path):
        new_set_docs = {'DFP', 'ITR', 'FRE', 'FCA', 'CGVN'}
        range_years = range(2010, 2025)

        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs=new_set_docs,
            range_years=range_years,
        )

        docs_paths = use_case.execute()

        created_dirs = sum(
            1
            for doc in new_set_docs
            for year in range_years
            if (tmp_path / doc / str(year)).exists()
        )

        # Expected: DFP(15) + ITR(14) + FRE(15) + FCA(15) + CGVN(7) = 66.
        expected_total = 66
        assert created_dirs == expected_total
        assert len(docs_paths) == len(new_set_docs)


@pytest.mark.unit
class TestVerifyPathsUseCasesEdgeCases:
    def test_execute_with_path_containing_spaces(self, tmp_path):
        path_with_spaces = tmp_path / 'path with spaces'

        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(path_with_spaces),
            new_set_docs={'DFP'},
            range_years=range(2020, 2022),
        )

        use_case.execute()

        assert path_with_spaces.exists()

    def test_execute_with_unicode_path(self, tmp_path):
        unicode_path = tmp_path / '路径_测试'

        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(unicode_path),
            new_set_docs={'DFP'},
            range_years=range(2020, 2022),
        )

        use_case.execute()

        assert unicode_path.exists()

    def test_execute_handles_long_year_range(self, tmp_path):
        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs={'DFP'},
            range_years=range(
                2010, 2025
            ),  # Changed from 2000 to 2010 (min year)
        )

        docs_paths = use_case.execute()

        assert len(docs_paths['DFP']) == 15

    def test_execute_with_multiple_docs_different_structures(self, tmp_path):
        new_set_docs = {'DFP', 'ITR', 'FRE'}
        range_years = range(2020, 2023)

        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs=new_set_docs,
            range_years=range_years,
        )

        docs_paths = use_case.execute()

        assert len(docs_paths['DFP']) == len(range_years)
        assert len(docs_paths['FRE']) == len(range_years)
        assert len(docs_paths['ITR']) == len(range_years)

    def test_execute_is_idempotent(self, tmp_path):
        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs={'DFP'},
            range_years=range(2020, 2022),
        )

        first_paths = use_case.execute()
        second_paths = use_case.execute()

        assert first_paths == second_paths


@pytest.mark.unit
class TestVerifyPathsUseCasesDocumentYearValidation:
    def test_itr_skips_years_before_2011(self, tmp_path):
        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs={'ITR'},
            range_years=range(2010, 2013),  # 2010, 2011, 2012
        )

        docs_paths = use_case.execute()

        assert 'ITR' in docs_paths
        assert 2011 in docs_paths['ITR']
        assert 2012 in docs_paths['ITR']
        assert 2010 not in docs_paths['ITR']
        assert len(docs_paths['ITR']) == 2

    def test_cgvn_skips_years_before_2018(self, tmp_path):
        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs={'CGVN'},
            range_years=range(2016, 2020),  # 2016, 2017, 2018, 2019
        )

        docs_paths = use_case.execute()

        assert 'CGVN' in docs_paths
        assert 2018 in docs_paths['CGVN']
        assert 2019 in docs_paths['CGVN']
        assert 2016 not in docs_paths['CGVN']
        assert 2017 not in docs_paths['CGVN']
        assert len(docs_paths['CGVN']) == 2

    def test_vlmo_skips_years_before_2018(self, tmp_path):
        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs={'VLMO'},
            range_years=range(2016, 2020),
        )

        docs_paths = use_case.execute()

        assert 'VLMO' in docs_paths
        assert 2018 in docs_paths['VLMO']
        assert 2019 in docs_paths['VLMO']
        assert 2016 not in docs_paths['VLMO']
        assert 2017 not in docs_paths['VLMO']
        assert len(docs_paths['VLMO']) == 2

    def test_dfp_accepts_all_years_from_2010(self, tmp_path):
        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs={'DFP'},
            range_years=range(2010, 2013),
        )

        docs_paths = use_case.execute()

        # Should have all years from 2010
        assert 'DFP' in docs_paths
        assert 2010 in docs_paths['DFP']
        assert 2011 in docs_paths['DFP']
        assert 2012 in docs_paths['DFP']
        assert len(docs_paths['DFP']) == 3

    def test_fre_accepts_all_years_from_2010(self, tmp_path):
        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs={'FRE'},
            range_years=range(2010, 2013),
        )

        docs_paths = use_case.execute()

        assert 'FRE' in docs_paths
        assert len(docs_paths['FRE']) == 3

    def test_mixed_documents_different_year_constraints(self, tmp_path):
        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs={'DFP', 'ITR', 'CGVN'},
            range_years=range(2010, 2020),  # 2010-2019
        )

        docs_paths = use_case.execute()

        assert len(docs_paths['DFP']) == 10
        assert 2010 in docs_paths['DFP']

        assert len(docs_paths['ITR']) == 9
        assert 2010 not in docs_paths['ITR']
        assert 2011 in docs_paths['ITR']

        assert len(docs_paths['CGVN']) == 2
        assert 2017 not in docs_paths['CGVN']
        assert 2018 in docs_paths['CGVN']

    def test_itr_with_only_valid_years(self, tmp_path):
        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs={'ITR'},
            range_years=range(2015, 2020),
        )

        docs_paths = use_case.execute()

        assert len(docs_paths['ITR']) == 5
        for year in range(2015, 2020):
            assert year in docs_paths['ITR']

    def test_cgvn_with_only_invalid_years(self, tmp_path):
        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs={'CGVN'},
            range_years=range(2010, 2018),  # All years before 2018
        )

        docs_paths = use_case.execute()

        assert 'CGVN' in docs_paths
        assert len(docs_paths['CGVN']) == 0

    def test_case_insensitive_document_name_validation(self, tmp_path):
        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs={'itr'},  # lowercase
            range_years=range(2010, 2013),
        )

        docs_paths = use_case.execute()

        assert 'itr' in docs_paths
        assert 2010 not in docs_paths['itr']
        assert 2011 in docs_paths['itr']

    def test_all_doc_types_with_full_year_range(self, tmp_path):
        all_docs = {'DFP', 'ITR', 'FRE', 'FCA', 'CGVN', 'IPE', 'VLMO'}
        use_case = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs=all_docs,
            range_years=range(2010, 2020),
        )

        docs_paths = use_case.execute()

        for doc in ['DFP', 'FRE', 'FCA', 'IPE']:
            assert len(docs_paths[doc]) == 10

        assert len(docs_paths['ITR']) == 9

        assert len(docs_paths['CGVN']) == 2
        assert len(docs_paths['VLMO']) == 2


@pytest.mark.unit
class TestVerifyPathsUseCasesIntegration:
    def test_verify_paths_integrates_with_download_workflow(self, tmp_path):
        new_set_docs = {'DFP', 'ITR'}
        range_years = range(2020, 2023)

        verify_paths_instance = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs=new_set_docs,
            range_years=range_years,
        )

        docs_paths = verify_paths_instance.execute()

        assert isinstance(docs_paths, dict)
        assert verify_paths_instance.destination_path == str(tmp_path)

        for doc in new_set_docs:
            for year in range_years:
                path = docs_paths[doc][year]
                assert Path(path).exists()
                assert os.access(path, os.W_OK)

    def test_verify_paths_accepts_set_from_generate_urls(self, tmp_path):
        new_set_docs = {'DFP', 'ITR', 'FRE'}
        range_years = range(2020, 2023)

        use_case_instance = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs=new_set_docs,
            range_years=range_years,
        )

        docs_paths = use_case_instance.execute()

        assert len(docs_paths) == 3

    def test_verify_paths_accepts_range_from_generate_range_years(
        self, tmp_path
    ):
        range_years = range(2020, 2024)

        use_case_instance = VerifyPathsUseCasesCVM(
            destination_path=str(tmp_path),
            new_set_docs={'DFP'},
            range_years=range_years,
        )

        docs_paths = use_case_instance.execute()

        assert len(docs_paths['DFP']) == 4
