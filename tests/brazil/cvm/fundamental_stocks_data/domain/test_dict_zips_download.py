from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    DictZipsToDownloadCVM,
    InvalidDocumentName,
    InvalidDocumentType,
    InvalidFirstYear,
    InvalidLastYear,
)

_DOCUMENT_FIRST_YEARS = {
    'CGVN': 2018,
    'DFP': 2010,
    'FCA': 2010,
    'FRE': 2010,
    'IPE': 2003,
    'ITR': 2011,
    'VLMO': 2018,
}


@pytest.mark.unit
class TestDictZipsToDownload:
    @pytest.fixture
    def dict_zips(self):
        return DictZipsToDownloadCVM()

    def test_initialization(self, dict_zips):
        assert dict_zips is not None
        assert hasattr(dict_zips, '_available_years')

    def test_get_dict_zips_to_download_returns_dict(self, dict_zips):
        result, set_docs = dict_zips.get_dict_zips_to_download(
            ['DFP'], 2020, 2020
        )
        assert isinstance(result, dict)
        assert isinstance(set_docs, set)

    def test_get_dict_zips_to_download_returns_strings(self, dict_zips):
        result, _set_docs = dict_zips.get_dict_zips_to_download(
            ['DFP'], 2020, 2020
        )
        for urls_list in result.values():
            for item in urls_list:
                assert isinstance(item, str)

    def test_get_dict_zips_to_download_single_doc_single_year(self, dict_zips):
        result, set_docs = dict_zips.get_dict_zips_to_download(
            ['DFP'], 2020, 2020
        )

        assert len(result) == 1
        assert len(set_docs) == 1
        assert 'DFP' in result
        assert 'DFP' in set_docs
        assert len(result['DFP']) == 1
        assert 'dfp_cia_aberta_2020.zip' in result['DFP'][0]
        assert result['DFP'][0].startswith('https://')

    def test_get_dict_zips_to_download_single_doc_multiple_years(
        self, dict_zips
    ):
        result, set_docs = dict_zips.get_dict_zips_to_download(
            ['DFP'], 2020, 2022
        )

        assert len(result) == 1
        assert len(set_docs) == 1
        assert 'DFP' in result
        assert 'DFP' in set_docs
        assert len(result['DFP']) == 3
        assert any('2020.zip' in url for url in result['DFP'])
        assert any('2021.zip' in url for url in result['DFP'])
        assert any('2022.zip' in url for url in result['DFP'])

    def test_get_dict_zips_to_download_multiple_docs_single_year(
        self, dict_zips
    ):
        result, set_docs = dict_zips.get_dict_zips_to_download(
            ['DFP', 'ITR'], 2020, 2020
        )

        assert len(result) == 2
        assert len(set_docs) == 2
        assert 'DFP' in result
        assert 'ITR' in result
        assert 'DFP' in set_docs
        assert 'ITR' in set_docs
        assert len(result['DFP']) == 1
        assert len(result['ITR']) == 1
        assert 'dfp_cia_aberta_2020.zip' in result['DFP'][0]
        assert 'itr_cia_aberta_2020.zip' in result['ITR'][0]

    def test_get_dict_zips_to_download_multiple_docs_multiple_years(
        self, dict_zips
    ):
        result, set_docs = dict_zips.get_dict_zips_to_download(
            ['DFP', 'ITR'], 2020, 2021
        )

        assert len(result) == 2
        assert len(set_docs) == 2
        assert 'DFP' in result
        assert 'ITR' in result
        assert 'DFP' in set_docs
        assert 'ITR' in set_docs
        assert len(result['DFP']) == 2
        assert len(result['ITR']) == 2
        assert any('dfp_cia_aberta_2020.zip' in url for url in result['DFP'])
        assert any('dfp_cia_aberta_2021.zip' in url for url in result['DFP'])
        assert any('itr_cia_aberta_2020.zip' in url for url in result['ITR'])
        assert any('itr_cia_aberta_2021.zip' in url for url in result['ITR'])

    def test_get_dict_zips_to_download_with_default_parameters(
        self, dict_zips
    ):
        result, set_docs = dict_zips.get_dict_zips_to_download()

        assert len(result) == 7
        assert len(set_docs) == 7
        for document, first_year in _DOCUMENT_FIRST_YEARS.items():
            expected_years = date.today().year - first_year + 1
            assert len(result[document]) == expected_years
            assert result[document][0].endswith(f'_{first_year}.zip')

        for urls_list in result.values():
            for url in urls_list:
                assert '.zip' in url

    def test_get_dict_zips_to_download_all_urls_end_with_zip(self, dict_zips):
        result, _set_docs = dict_zips.get_dict_zips_to_download(
            ['DFP'], 2020, 2022
        )

        for urls_list in result.values():
            for url in urls_list:
                assert url.endswith('.zip')

    def test_get_dict_zips_to_download_all_urls_start_with_https(
        self, dict_zips
    ):
        result, _set_docs = dict_zips.get_dict_zips_to_download(
            ['DFP'], 2020, 2022
        )

        for urls_list in result.values():
            for url in urls_list:
                assert url.startswith('https://')

    def test_get_dict_zips_to_download_urls_contain_cvm_domain(
        self, dict_zips
    ):
        result, _set_docs = dict_zips.get_dict_zips_to_download(
            ['DFP'], 2020, 2020
        )

        for urls_list in result.values():
            for url in urls_list:
                assert 'dados.cvm.gov.br' in url

    def test_get_dict_zips_to_download_with_only_list_docs(self, dict_zips):
        result, set_docs = dict_zips.get_dict_zips_to_download(
            list_docs=['DFP']
        )

        assert len(result) == 1
        assert len(set_docs) == 1
        assert 'DFP' in result
        assert 'DFP' in set_docs
        current_year = date.today().year
        expected_count = current_year - 2010 + 1
        assert len(result['DFP']) == expected_count

    def test_get_dict_zips_to_download_with_only_initial_year(self, dict_zips):
        result, set_docs = dict_zips.get_dict_zips_to_download(
            initial_year=2020
        )

        assert len(result) == 7
        assert len(set_docs) == 7
        current_year = date.today().year
        expected_count = current_year - 2020 + 1
        for urls_list in result.values():
            assert len(urls_list) == expected_count

    def test_get_dict_zips_to_download_with_only_last_year(self, dict_zips):
        result, set_docs = dict_zips.get_dict_zips_to_download(last_year=2020)

        assert len(result) == 7
        assert len(set_docs) == 7
        for document, first_year in _DOCUMENT_FIRST_YEARS.items():
            expected_count = 2020 - first_year + 1
            assert len(result[document]) == expected_count

    def test_get_dict_zips_to_download_with_lowercase_doc_name(
        self, dict_zips
    ):
        result, set_docs = dict_zips.get_dict_zips_to_download(
            ['dfp'], 2020, 2020
        )

        assert len(result) == 1
        assert len(set_docs) == 1
        assert 'DFP' in result
        assert 'DFP' in set_docs
        assert 'dfp_cia_aberta_2020.zip' in result['DFP'][0]

    def test_get_dict_zips_to_download_with_mixed_case_doc_name(
        self, dict_zips
    ):
        result, set_docs = dict_zips.get_dict_zips_to_download(
            ['DfP'], 2020, 2020
        )

        assert len(result) == 1
        assert len(set_docs) == 1
        assert 'DFP' in result
        assert 'DFP' in set_docs
        assert 'dfp_cia_aberta_2020.zip' in result['DFP'][0]

    def test_get_dict_zips_to_download_with_invalid_doc_raises_error(
        self, dict_zips
    ):
        with pytest.raises(InvalidDocumentName):
            dict_zips.get_dict_zips_to_download(['INVALID_DOC'], 2020, 2020)

    def test_get_dict_zips_to_download_with_non_string_doc_raises_error(
        self, dict_zips
    ):
        with pytest.raises(InvalidDocumentType):
            dict_zips.get_dict_zips_to_download([123], 2020, 2020)

    def test_get_dict_zips_to_download_with_invalid_first_year_raises_error(
        self, dict_zips
    ):
        with pytest.raises(InvalidFirstYear):
            dict_zips.get_dict_zips_to_download(['DFP'], 2002, 2020)

    def test_get_dict_zips_to_download_with_invalid_last_year_raises_error(
        self, dict_zips
    ):
        with pytest.raises(InvalidLastYear):
            dict_zips.get_dict_zips_to_download(['DFP'], 2020, 2019)

    def test_get_dict_zips_to_download_with_future_year_raises_error(
        self, dict_zips
    ):
        future_year = date.today().year + 10
        with pytest.raises(InvalidLastYear):
            dict_zips.get_dict_zips_to_download(['DFP'], 2020, future_year)

    def test_get_dict_zips_to_download_with_year_before_minimum_raises_error(
        self, dict_zips
    ):
        with pytest.raises(InvalidFirstYear):
            dict_zips.get_dict_zips_to_download(['DFP'], 2000, 2020)

    def test_get_dict_zips_to_download_order_years_then_docs(self, dict_zips):
        result, set_docs = dict_zips.get_dict_zips_to_download(
            ['DFP', 'ITR'], 2020, 2021
        )

        assert len(result) == 2
        assert len(set_docs) == 2
        assert 'DFP' in result
        assert 'ITR' in result
        assert 'DFP' in set_docs
        assert 'ITR' in set_docs
        assert len(result['DFP']) == 2
        assert len(result['ITR']) == 2

    def test_get_dict_zips_to_download_all_seven_docs(self, dict_zips):
        all_docs = ['CGVN', 'FRE', 'FCA', 'DFP', 'ITR', 'IPE', 'VLMO']
        result, set_docs = dict_zips.get_dict_zips_to_download(
            all_docs, 2020, 2020
        )

        assert len(result) == 7
        assert len(set_docs) == 7
        for doc in all_docs:
            assert doc in result
            assert doc in set_docs
            assert len(result[doc]) == 1
            assert doc.lower() in result[doc][0].lower()

    def test_get_dict_zips_to_download_with_empty_list_docs(self, dict_zips):
        result, set_docs = dict_zips.get_dict_zips_to_download([], 2020, 2020)

        assert len(result) == 7
        assert len(set_docs) == 7
        for urls_list in result.values():
            assert len(urls_list) == 1

    def test_get_dict_zips_to_download_url_format_is_correct(self, dict_zips):
        result, _set_docs = dict_zips.get_dict_zips_to_download(
            ['DFP'], 2020, 2020
        )

        url = result['DFP'][0]
        assert url.startswith('https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/')
        assert 'dfp_cia_aberta_2020.zip' in url

    def test_get_dict_zips_to_download_with_duplicate_docs(self, dict_zips):
        result, set_docs = dict_zips.get_dict_zips_to_download(
            ['DFP', 'DFP'], 2020, 2020
        )

        assert len(result) == 1
        assert len(set_docs) == 1
        assert 'DFP' in result
        assert 'DFP' in set_docs
        assert 'dfp_cia_aberta_2020.zip' in result['DFP'][0]

    def test_get_dict_zips_to_download_range_includes_boundaries(
        self, dict_zips
    ):
        result, set_docs = dict_zips.get_dict_zips_to_download(
            ['DFP'], 2018, 2020
        )

        assert len(result) == 1
        assert len(set_docs) == 1
        assert 'DFP' in result
        assert 'DFP' in set_docs
        assert len(result['DFP']) == 3
        assert any('2018.zip' in url for url in result['DFP'])
        assert any('2019.zip' in url for url in result['DFP'])
        assert any('2020.zip' in url for url in result['DFP'])

    def test_get_dict_zips_to_download_with_minimum_year_2010(self, dict_zips):
        result, set_docs = dict_zips.get_dict_zips_to_download(
            ['DFP'], 2010, 2010
        )

        assert len(result) == 1
        assert len(set_docs) == 1
        assert 'DFP' in result
        assert 'DFP' in set_docs
        assert len(result['DFP']) == 1
        assert '2010.zip' in result['DFP'][0]

    def test_get_dict_zips_to_download_with_current_year(self, dict_zips):
        current_year = date.today().year
        result, set_docs = dict_zips.get_dict_zips_to_download(
            ['DFP'], current_year, current_year
        )

        assert len(result) == 1
        assert len(set_docs) == 1
        assert 'DFP' in result
        assert 'DFP' in set_docs
        assert len(result['DFP']) == 1
        assert f'{current_year}.zip' in result['DFP'][0]

    def test_get_dict_zips_to_download_no_duplicate_urls(self, dict_zips):
        result, set_docs = dict_zips.get_dict_zips_to_download(
            ['DFP'], 2020, 2020
        )

        assert len(result) == 1
        assert len(set_docs) == 1
        assert 'DFP' in result
        assert 'DFP' in set_docs
        assert len(result['DFP']) == 1

    def test_get_dict_zips_to_download_large_year_range(self, dict_zips):
        result, set_docs = dict_zips.get_dict_zips_to_download(
            ['DFP'], 2010, 2024
        )

        assert len(result) == 1
        assert len(set_docs) == 1
        assert 'DFP' in result
        assert 'DFP' in set_docs
        assert len(result['DFP']) == 15

    def test_get_dict_zips_to_download_specific_url_structure_for_each_doc(
        self, dict_zips
    ):
        result_dfp, _set_dfp = dict_zips.get_dict_zips_to_download(
            ['DFP'], 2020, 2020
        )
        assert '/DFP/DADOS/dfp_cia_aberta_2020.zip' in result_dfp['DFP'][0]

        result_itr, _set_itr = dict_zips.get_dict_zips_to_download(
            ['ITR'], 2020, 2020
        )
        assert '/ITR/DADOS/itr_cia_aberta_2020.zip' in result_itr['ITR'][0]

        result_fre, _set_fre = dict_zips.get_dict_zips_to_download(
            ['FRE'], 2020, 2020
        )
        assert '/FRE/DADOS/fre_cia_aberta_2020.zip' in result_fre['FRE'][0]

    def test_get_dict_zips_to_download_with_non_list_docs_type_raises_error(
        self, dict_zips
    ):
        with pytest.raises(TypeError):
            dict_zips.get_dict_zips_to_download('DFP', 2020, 2020)

    def test_get_dict_zips_to_download_with_string_years_raises_error(
        self, dict_zips
    ):
        with pytest.raises(InvalidFirstYear):
            dict_zips.get_dict_zips_to_download(['DFP'], '2020', 2021)

    def test_get_dict_zips_to_download_with_float_years_raises_error(
        self, dict_zips
    ):
        with pytest.raises(InvalidFirstYear):
            dict_zips.get_dict_zips_to_download(['DFP'], 2020.5, 2021)

    def test_get_dict_zips_to_download_combinations(self, dict_zips):
        result1, set1 = dict_zips.get_dict_zips_to_download(
            ['DFP', 'ITR', 'FRE'], 2020, 2021
        )
        assert len(result1) == 3
        assert len(set1) == 3
        assert len(result1['DFP']) == 2
        assert len(result1['ITR']) == 2
        assert len(result1['FRE']) == 2

        result2, set2 = dict_zips.get_dict_zips_to_download(
            ['DFP'], 2018, 2022
        )
        assert len(result2) == 1
        assert len(set2) == 1
        assert len(result2['DFP']) == 5

        result3, set3 = dict_zips.get_dict_zips_to_download(
            ['DFP', 'ITR'], 2020, 2020
        )
        assert len(result3) == 2
        assert len(set3) == 2
        assert len(result3['DFP']) == 1
        assert len(result3['ITR']) == 1

    @patch(
        'globaldatafinance.brazil.cvm.fundamental_stocks_data.core.get_url_docs'
    )
    @patch(
        'globaldatafinance.brazil.cvm.fundamental_stocks_data.core.AvailableYearsCVM'
    )
    def test_get_dict_zips_to_download_uses_dependencies_correctly(
        self, mock_available_years, mock_get_url_docs
    ):
        mock_years_instance = MagicMock()
        mock_years_instance.return_range_years.return_value = range(2020, 2022)
        mock_available_years.return_value = mock_years_instance

        mock_get_url_docs.return_value = (
            {
                'DFP': 'https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_'
            },
            {'DFP'},
        )

        dict_zips_test = DictZipsToDownloadCVM()
        result, set_docs = dict_zips_test.get_dict_zips_to_download(
            ['DFP'], 2020, 2021
        )

        mock_years_instance.return_range_years.assert_called_once_with(
            2020, 2021
        )
        mock_get_url_docs.assert_called_once_with(['DFP'])

        assert len(result) == 1
        assert 'DFP' in result
        assert len(set_docs) == 1
        assert 'DFP' in set_docs
        assert len(result['DFP']) == 2

    def test_get_dict_zips_to_download_result_is_new_list(self, dict_zips):
        result1, _set1 = dict_zips.get_dict_zips_to_download(
            ['DFP'], 2020, 2020
        )
        result2, _set2 = dict_zips.get_dict_zips_to_download(
            ['DFP'], 2020, 2020
        )

        result1['DFP'].append('test')
        assert len(result2['DFP']) == 1

    def test_mixed_documents_do_not_generate_unpublished_years(
        self, dict_zips
    ):
        result, documents = dict_zips.get_dict_zips_to_download(
            ['DFP', 'IPE', 'CGVN'], 2003, 2018
        )

        assert documents == {'DFP', 'IPE', 'CGVN'}
        assert result['DFP'][0].endswith('_2010.zip')
        assert result['IPE'][0].endswith('_2003.zip')
        assert result['CGVN'] == [
            'https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/CGVN/DADOS/'
            'cgvn_cia_aberta_2018.zip'
        ]
