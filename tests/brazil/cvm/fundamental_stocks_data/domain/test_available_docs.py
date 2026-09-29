import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    InvalidDocumentName,
    InvalidDocumentType,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.core import (
    get_available_docs,
    get_url_docs,
    validate_docs_name,
)


@pytest.mark.unit
class TestAvailableDocs:
    def test_get_available_docs_returns_dict(self):
        docs = get_available_docs()
        assert isinstance(docs, dict)

    def test_get_available_docs_returns_all_expected_keys(self):
        docs = get_available_docs()
        expected_keys = ['CGVN', 'FRE', 'FCA', 'DFP', 'ITR', 'IPE', 'VLMO']

        assert len(docs) == len(expected_keys)
        for key in expected_keys:
            assert key in docs

    def test_get_available_docs_returns_copy(self):
        docs1 = get_available_docs()
        docs2 = get_available_docs()

        docs1['TEST'] = 'Test value'
        assert 'TEST' not in docs2

    def test_get_available_docs_values_are_strings(self):
        docs = get_available_docs()
        for value in docs.values():
            assert isinstance(value, str)
            assert len(value) > 0

    def test_get_available_docs_keys_are_uppercase(self):
        docs = get_available_docs()
        for key in docs:
            assert key.isupper()

    def test_validate_docs_name_with_valid_doc_uppercase(self):
        for doc_name in ('DFP', 'ITR', 'FRE'):
            assert validate_docs_name(doc_name) is None

    def test_validate_docs_name_with_valid_doc_lowercase(self):
        for doc_name in ('dfp', 'itr', 'fre'):
            assert validate_docs_name(doc_name) is None

    def test_validate_docs_name_with_valid_doc_mixed_case(self):
        for doc_name in ('DfP', 'ItR', 'FrE'):
            assert validate_docs_name(doc_name) is None

    def test_validate_docs_name_with_spaces(self):
        for doc_name in ('  DFP  ', ' ITR ', 'FRE   '):
            assert validate_docs_name(doc_name) is None

    def test_validate_docs_name_with_invalid_doc_name(self):
        with pytest.raises(InvalidDocumentName) as exc_info:
            validate_docs_name('INVALID_DOC')

        assert 'INVALID_DOC' in str(exc_info.value)

    def test_validate_docs_name_with_empty_string(self):
        with pytest.raises(InvalidDocumentName):
            validate_docs_name('')

    def test_validate_docs_name_with_non_string_type_integer(self):
        with pytest.raises(InvalidDocumentType) as exc_info:
            validate_docs_name(123)

        assert '123' in str(exc_info.value)

    def test_validate_docs_name_with_non_string_type_list(self):
        with pytest.raises(InvalidDocumentType):
            validate_docs_name(['DFP'])

    def test_validate_docs_name_with_non_string_type_dict(self):
        with pytest.raises(InvalidDocumentType):
            validate_docs_name({'doc': 'DFP'})

    def test_validate_docs_name_with_none(self):
        with pytest.raises(InvalidDocumentType):
            validate_docs_name(None)

    def test_validate_docs_name_with_float(self):
        with pytest.raises(InvalidDocumentType):
            validate_docs_name(3.14)

    def test_validate_docs_name_with_boolean(self):
        with pytest.raises(InvalidDocumentType):
            validate_docs_name(True)

    def test_validate_all_available_docs(self):
        docs = get_available_docs()
        validation_results = [
            validate_docs_name(doc_name) for doc_name in docs
        ]

        assert validation_results == [None] * len(docs)

    def test_doc_descriptions_not_empty(self):
        docs = get_available_docs()
        for description in docs.values():
            assert len(description.strip()) > 0


@pytest.mark.unit
class TestUrlDocs:
    def test_get_url_docs_builds_all_url_prefixes(self):
        urls, set_docs = get_url_docs()

        assert len(urls) == 7
        assert len(set_docs) == 7
        for key in get_available_docs():
            assert key in urls

    def test_get_url_docs_without_parameters_returns_all_urls(self):
        urls, set_docs = get_url_docs()

        assert isinstance(urls, dict)
        assert isinstance(set_docs, set)
        assert len(urls) == 7
        assert len(set_docs) == 7

    def test_get_url_docs_returns_list_of_strings(self):
        urls, _set_docs = get_url_docs()

        for url in urls.values():
            assert isinstance(url, str)

    def test_get_url_docs_urls_start_with_https(self):
        urls, _set_docs = get_url_docs()

        for url in urls.values():
            assert url.startswith('https://')

    def test_get_url_docs_urls_contain_cvm_domain(self):
        urls, _set_docs = get_url_docs()

        for url in urls.values():
            assert 'dados.cvm.gov.br' in url

    def test_get_url_docs_with_single_doc(self):
        urls, set_docs = get_url_docs(['DFP'])

        assert len(urls) == 1
        assert len(set_docs) == 1
        assert 'DFP' in urls
        assert 'DFP' in set_docs
        assert 'dfp_cia_aberta_' in urls['DFP']

    def test_get_url_docs_with_multiple_docs(self):
        urls, set_docs = get_url_docs(['DFP', 'ITR', 'FRE'])

        assert len(urls) == 3
        assert len(set_docs) == 3
        assert 'DFP' in urls
        assert 'ITR' in urls
        assert 'FRE' in urls
        assert 'DFP' in set_docs
        assert 'ITR' in set_docs
        assert 'FRE' in set_docs
        assert 'dfp_cia_aberta_' in urls['DFP']
        assert 'itr_cia_aberta_' in urls['ITR']
        assert 'fre_cia_aberta_' in urls['FRE']

    def test_get_url_docs_with_lowercase_doc_name(self):
        urls, set_docs = get_url_docs(['dfp'])

        assert len(urls) == 1
        assert 'DFP' in urls
        assert 'DFP' in set_docs
        assert 'dfp_cia_aberta_' in urls['DFP']

    def test_get_url_docs_with_mixed_case_doc_name(self):
        urls, set_docs = get_url_docs(['DfP'])

        assert len(urls) == 1
        assert 'DFP' in urls
        assert 'DFP' in set_docs
        assert 'dfp_cia_aberta_' in urls['DFP']

    def test_get_url_docs_with_invalid_doc_name(self):
        with pytest.raises(InvalidDocumentName):
            get_url_docs(['INVALID_DOC'])

    @pytest.mark.parametrize('list_docs', ['DFP', (), '', 0, False])
    def test_get_url_docs_with_non_list_parameter(self, list_docs):
        with pytest.raises(TypeError) as exc_info:
            get_url_docs(list_docs)

        assert 'list_docs must be a list of strings or None' in str(
            exc_info.value
        )

    def test_get_url_docs_with_dict_parameter(self):
        with pytest.raises(TypeError):
            get_url_docs({'doc': 'DFP'})

    def test_get_url_docs_with_integer_parameter(self):
        with pytest.raises(TypeError):
            get_url_docs(123)

    def test_get_url_docs_with_empty_list(self):
        urls, set_docs = get_url_docs([])

        assert isinstance(urls, dict)
        assert isinstance(set_docs, set)
        assert len(urls) == 7
        assert len(set_docs) == 7

    def test_get_url_docs_with_none_selects_all_docs(self):
        urls, set_docs = get_url_docs(None)

        assert len(urls) == 7
        assert len(set_docs) == 7

    def test_get_url_docs_with_all_available_docs(self):
        all_docs = ['CGVN', 'FRE', 'FCA', 'DFP', 'ITR', 'IPE', 'VLMO']
        urls, set_docs = get_url_docs(all_docs)

        assert len(urls) == 7
        assert len(set_docs) == 7
        for doc in all_docs:
            assert doc in set_docs

    def test_get_url_docs_with_duplicate_docs(self):
        urls, set_docs = get_url_docs(['DFP', 'DFP'])

        assert len(urls) == 1
        assert len(set_docs) == 1
        assert 'DFP' in urls
        assert 'DFP' in set_docs
        assert 'dfp_cia_aberta_' in urls['DFP']

    def test_get_url_docs_with_non_string_in_list(self):
        with pytest.raises(InvalidDocumentType):
            get_url_docs([123])

    def test_get_url_docs_with_mixed_valid_invalid_docs(self):
        with pytest.raises(InvalidDocumentName):
            get_url_docs(['DFP', 'INVALID'])

    def test_get_url_docs_specific_urls_for_each_doc(self):
        urls_cgvn, set_cgvn = get_url_docs(['CGVN'])
        assert 'CGVN' in urls_cgvn
        assert 'CGVN' in set_cgvn
        assert 'cgvn_cia_aberta_' in urls_cgvn['CGVN']

        urls_fre, set_fre = get_url_docs(['FRE'])
        assert 'FRE' in urls_fre
        assert 'FRE' in set_fre
        assert 'fre_cia_aberta_' in urls_fre['FRE']

        urls_fca, set_fca = get_url_docs(['FCA'])
        assert 'FCA' in urls_fca
        assert 'FCA' in set_fca
        assert 'fca_cia_aberta_' in urls_fca['FCA']

        urls_dfp, set_dfp = get_url_docs(['DFP'])
        assert 'DFP' in urls_dfp
        assert 'DFP' in set_dfp
        assert 'dfp_cia_aberta_' in urls_dfp['DFP']

        urls_itr, set_itr = get_url_docs(['ITR'])
        assert 'ITR' in urls_itr
        assert 'ITR' in set_itr
        assert 'itr_cia_aberta_' in urls_itr['ITR']

        urls_ipe, set_ipe = get_url_docs(['IPE'])
        assert 'IPE' in urls_ipe
        assert 'IPE' in set_ipe
        assert 'ipe_cia_aberta_' in urls_ipe['IPE']

        urls_vlmo, set_vlmo = get_url_docs(['VLMO'])
        assert 'VLMO' in urls_vlmo
        assert 'VLMO' in set_vlmo
        assert 'vlmo_cia_aberta_' in urls_vlmo['VLMO']

    def test_get_url_docs_urls_end_correctly(self):
        urls, _set_docs = get_url_docs(['DFP'])

        assert urls['DFP'].endswith('_')

    def test_get_url_docs_order_preserved(self):
        docs_list = ['ITR', 'DFP', 'FRE']
        urls, set_docs = get_url_docs(docs_list)

        keys = list(urls.keys())
        assert keys[0] == 'ITR'
        assert keys[1] == 'DFP'
        assert keys[2] == 'FRE'
        assert len(set_docs) == 3
        for doc in docs_list:
            assert doc in set_docs

    def test_get_url_docs_with_none_returns_all(self):
        urls, set_docs = get_url_docs(None)

        assert len(urls) == 7
        assert len(set_docs) == 7
        assert isinstance(urls, dict)
        assert isinstance(set_docs, set)
