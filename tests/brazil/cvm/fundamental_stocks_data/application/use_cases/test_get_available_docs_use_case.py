import logging
from unittest.mock import patch

import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    get_available_docs,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.core import (
    get_available_docs as core_get_available_docs,
)


@pytest.mark.unit
class TestGetAvailableDocsUseCase:
    def test_execute_returns_dict(self):
        use_case = get_available_docs
        result = use_case()
        assert isinstance(result, dict)

    def test_execute_returns_non_empty_dict(self):
        use_case = get_available_docs
        result = use_case()
        assert len(result) > 0

    def test_execute_returns_expected_document_types(self):
        use_case = get_available_docs
        result = use_case()

        expected_docs = ['DFP', 'ITR', 'FRE', 'FCA', 'CGVN', 'IPE', 'VLMO']
        for doc in expected_docs:
            assert doc in result, (
                f"Expected document '{doc}' not found in results"
            )

    def test_execute_returns_exact_document_count(self):
        use_case = get_available_docs
        result = use_case()
        assert len(result) == 7

    def test_execute_all_values_are_strings(self):
        use_case = get_available_docs
        result = use_case()

        for key, value in result.items():
            assert isinstance(key, str)
            assert isinstance(value, str)

    def test_execute_all_keys_are_uppercase(self):
        use_case = get_available_docs
        result = use_case()

        for key in result:
            assert key.isupper()

    def test_execute_values_are_non_empty(self):
        use_case = get_available_docs
        result = use_case()

        for _key, value in result.items():
            assert len(value) > 0

    def test_execute_returns_copy_not_reference(self):
        use_case = get_available_docs
        result1 = use_case()
        result2 = use_case()

        result1['TEST'] = 'test value'
        assert 'TEST' not in result2

    def test_execute_returns_consistent_results(self):
        use_case = get_available_docs
        result1 = use_case()
        result2 = use_case()

        assert result1 == result2

    def test_execute_logs_info_message(self, caplog):
        use_case = get_available_docs

        with caplog.at_level(logging.INFO):
            use_case()

        assert any(
            'retrieving' in record.message.lower() for record in caplog.records
        )

    def test_execute_logs_debug_message_on_success(self, caplog):
        use_case = get_available_docs

        with caplog.at_level(logging.DEBUG):
            use_case()

        assert any(
            'retrieved' in record.message.lower() for record in caplog.records
        )

    def test_execute_raises_exception_when_available_docs_fails(self):
        use_case = get_available_docs

        with (
            patch(
                'globaldatafinance.brazil.cvm.fundamental_stocks_data.core.get_available_docs',
                side_effect=Exception('Database connection failed'),
            ),
            pytest.raises(Exception, match='Database connection failed'),
        ):
            use_case()

    def test_execute_raises_runtime_error(self):
        use_case = get_available_docs

        with (
            patch(
                'globaldatafinance.brazil.cvm.fundamental_stocks_data.core.get_available_docs',
                side_effect=RuntimeError('Runtime error'),
            ),
            pytest.raises(RuntimeError),
        ):
            use_case()

    def test_execute_raises_value_error(self):
        use_case = get_available_docs

        with (
            patch(
                'globaldatafinance.brazil.cvm.fundamental_stocks_data.core.get_available_docs',
                side_effect=ValueError('Invalid value'),
            ),
            pytest.raises(ValueError),
        ):
            use_case()

    def test_execute_raises_timeout_error(self):
        use_case = get_available_docs

        with (
            patch(
                'globaldatafinance.brazil.cvm.fundamental_stocks_data.core.get_available_docs',
                side_effect=TimeoutError('Request timeout'),
            ),
            pytest.raises(TimeoutError),
        ):
            use_case()

    def test_execute_raises_type_error(self):
        use_case = get_available_docs

        with (
            patch(
                'globaldatafinance.brazil.cvm.fundamental_stocks_data.core.get_available_docs',
                side_effect=TypeError('Type error'),
            ),
            pytest.raises(TypeError),
        ):
            use_case()

    def test_execute_returns_specific_doc_descriptions(self):
        use_case = get_available_docs
        result = use_case()

        assert len(result['DFP']) > 20
        assert len(result['ITR']) > 20
        assert len(result['FRE']) > 20

    def test_repeated_calls_return_independent_results(self):
        result1 = get_available_docs()
        result2 = get_available_docs()

        assert result1 == result2
        assert result1 is not result2

    def test_execute_returns_immutable_data(self):
        use_case = get_available_docs

        result1 = use_case()
        result1.clear()

        result2 = use_case()
        assert len(result2) == 7

    def test_execute_matches_core_available_docs(self):
        use_case = get_available_docs
        result = use_case()

        expected_result = core_get_available_docs()

        assert result == expected_result

    def test_execute_dfp_document_exists_and_valid(self):
        use_case = get_available_docs
        result = use_case()

        assert 'DFP' in result
        assert isinstance(result['DFP'], str)
        assert len(result['DFP']) > 0

    def test_execute_all_documents_have_valid_structure(self):
        use_case = get_available_docs
        result = use_case()

        required_docs = ['DFP', 'ITR', 'FRE', 'FCA', 'CGVN', 'IPE', 'VLMO']
        for doc in required_docs:
            assert doc in result
            assert isinstance(result[doc], str)
            assert len(result[doc]) > 10

    def test_execute_returns_mocked_data(self):
        use_case_instance = get_available_docs
        mock_data = {'TEST': 'Test document'}

        with patch(
            'globaldatafinance.brazil.cvm.fundamental_stocks_data.core.get_available_docs',
            return_value=mock_data,
        ):
            result = use_case_instance()
            assert result == mock_data

    def test_execute_with_empty_dict_from_available_docs(self):
        use_case = get_available_docs

        with patch(
            'globaldatafinance.brazil.cvm.fundamental_stocks_data.core.get_available_docs',
            return_value={},
        ):
            result = use_case()
            assert result == {}
            assert isinstance(result, dict)

    def test_execute_with_large_dataset(self):
        use_case = get_available_docs
        large_mock_data = {f'DOC_{i}': f'Description {i}' for i in range(1000)}

        with patch(
            'globaldatafinance.brazil.cvm.fundamental_stocks_data.core.get_available_docs',
            return_value=large_mock_data,
        ):
            result = use_case()
            assert len(result) == 1000
            assert isinstance(result, dict)

    def test_execute_propagates_generic_exception(self):
        use_case = get_available_docs

        with (
            patch(
                'globaldatafinance.brazil.cvm.fundamental_stocks_data.core.get_available_docs',
                side_effect=Exception('Generic error'),
            ),
            pytest.raises(Exception, match='Generic error'),
        ):
            use_case()

    def test_execute_propagates_attribute_error(self):
        use_case = get_available_docs

        with (
            patch(
                'globaldatafinance.brazil.cvm.fundamental_stocks_data.core.get_available_docs',
                side_effect=AttributeError('Attribute not found'),
            ),
            pytest.raises(AttributeError, match='Attribute not found'),
        ):
            use_case()

    def test_execute_propagates_os_error(self):
        use_case = get_available_docs

        with (
            patch(
                'globaldatafinance.brazil.cvm.fundamental_stocks_data.core.get_available_docs',
                side_effect=OSError('File not found'),
            ),
            pytest.raises(OSError, match='File not found'),
        ):
            use_case()

    def test_execute_return_type_is_dict(self):
        use_case = get_available_docs
        result = use_case()
        assert isinstance(result, dict)

    def test_execute_with_special_characters_in_values(self):
        use_case = get_available_docs
        result = use_case()

        for _key, value in result.items():
            assert isinstance(value, str)

    def test_execute_dict_keys_remain_constant(self):
        use_case = get_available_docs
        keys1 = set(use_case().keys())
        keys2 = set(use_case().keys())
        keys3 = set(use_case().keys())

        assert keys1 == keys2 == keys3

    def test_execute_dict_values_remain_constant(self):
        use_case = get_available_docs
        result1 = use_case()
        result2 = use_case()
        result3 = use_case()

        for key in result1:
            assert result1[key] == result2[key] == result3[key]
