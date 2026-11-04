import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    EmptyDocumentListError,
    InvalidDocumentName,
    InvalidDocumentType,
    InvalidFirstYear,
    InvalidLastYear,
)


@pytest.mark.unit
class TestInvalidFirstYear:
    def test_message_format_exact(self):
        minimal = 2010
        atual = 2025
        exception = InvalidFirstYear(minimal, atual)
        expected = (
            'Invalid first year. You must provide an integer value greater '
            'than or equal to '
            f'{minimal} and less than or equal to {atual}.'
        )
        assert str(exception) == expected

    def test_is_exception_subclass(self):
        exception = InvalidFirstYear(2010, 2025)
        assert isinstance(exception, Exception)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(InvalidFirstYear) as exc_info:
            raise InvalidFirstYear(2010, 2025)
        assert 'Invalid first year' in str(exc_info.value)

    def test_with_different_year_ranges(self):
        test_cases = [(2000, 2023), (1980, 2020), (2010, 2024), (1990, 2030)]
        for minimal, atual in test_cases:
            exception = InvalidFirstYear(minimal, atual)
            assert str(minimal) in str(exception)
            assert str(atual) in str(exception)

    def test_with_boundary_years(self):
        exc1 = InvalidFirstYear(1900, 2025)
        assert '1900' in str(exc1)
        exc2 = InvalidFirstYear(2024, 2025)
        assert '2024' in str(exc2)

    def test_message_contains_keywords(self):
        exception = InvalidFirstYear(2010, 2025)
        exc_str = str(exception).lower()
        assert 'greater than or equal to' in exc_str or '>=' in exc_str
        assert 'less than or equal to' in exc_str or '<=' in exc_str


@pytest.mark.unit
class TestInvalidLastYear:
    def test_message_format_exact(self):
        first_year = 2020
        atual = 2025
        exception = InvalidLastYear(first_year, atual)
        expected = (
            'Invalid last year. You must provide an integer value greater '
            'than or equal to '
            f'{first_year} and less than or equal to {atual}.'
        )
        assert str(exception) == expected

    def test_is_exception_subclass(self):
        exception = InvalidLastYear(2020, 2025)
        assert isinstance(exception, Exception)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(InvalidLastYear) as exc_info:
            raise InvalidLastYear(2020, 2025)
        assert 'Invalid last year' in str(exc_info.value)

    def test_with_different_year_ranges(self):
        test_cases = [(2000, 2023), (2010, 2020), (2015, 2024), (2000, 2030)]
        for first_year, atual in test_cases:
            exception = InvalidLastYear(first_year, atual)
            assert str(first_year) in str(exception)
            assert str(atual) in str(exception)

    def test_shows_first_year_reference(self):
        exception = InvalidLastYear(2010, 2025)
        assert '2010' in str(exception)

    def test_with_boundary_years(self):
        exc1 = InvalidLastYear(2000, 1999)
        assert '2000' in str(exc1)
        exc2 = InvalidLastYear(2024, 2024)
        assert '2024' in str(exc2)

    def test_message_contains_keywords(self):
        exception = InvalidLastYear(2020, 2025)
        exc_str = str(exception).lower()
        assert 'greater than or equal to' in exc_str or '>=' in exc_str
        assert 'less than or equal to' in exc_str or '<=' in exc_str


@pytest.mark.unit
class TestInvalidDocumentName:
    def test_message_format_exact(self):
        doc_name = 'INVALID_DOC'
        available_docs = ['DFP', 'ITR', 'FRE']
        exception = InvalidDocumentName(doc_name, available_docs)
        expected = (
            f'Invalid document name: {doc_name}. The document name must be a '
            f'string and one of the following: {available_docs}.'
        )
        assert str(exception) == expected

    def test_is_exception_subclass(self):
        exception = InvalidDocumentName('INVALID', ['DFP', 'ITR'])
        assert isinstance(exception, Exception)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(InvalidDocumentName) as exc_info:
            raise InvalidDocumentName('WRONG', ['DFP', 'ITR'])
        assert 'Invalid document name' in str(exc_info.value)
        assert 'WRONG' in str(exc_info.value)

    def test_shows_all_available_docs(self):
        available_docs = ['DFP', 'ITR', 'FRE', 'FCA']
        exception = InvalidDocumentName('INVALID', available_docs)
        for doc in available_docs:
            assert doc in str(exception)

    def test_with_empty_doc_name(self):
        exception = InvalidDocumentName('', ['DFP'])
        assert '' in str(exception)
        assert 'DFP' in str(exception)

    def test_with_empty_available_list(self):
        exception = InvalidDocumentName('TEST', [])
        assert 'TEST' in str(exception)
        assert '[]' in str(exception)

    def test_with_single_available_doc(self):
        exception = InvalidDocumentName('WRONG', ['DFP'])
        assert 'WRONG' in str(exception)
        assert 'DFP' in str(exception)

    def test_with_many_available_docs(self):
        available_docs = [f'DOC_{i}' for i in range(50)]
        exception = InvalidDocumentName('INVALID', available_docs)
        assert 'INVALID' in str(exception)
        assert 'DOC_' in str(exception)

    def test_with_special_characters(self):
        doc_name = 'DRE_AÇÃO_2023'
        available_docs = ['DRE', 'BPARMS']
        exception = InvalidDocumentName(doc_name, available_docs)
        assert doc_name in str(exception)

    def test_with_accented_characters(self):
        doc_name = 'AÇÚCAR'
        available_docs = ['DFP', 'ITR']
        exception = InvalidDocumentName(doc_name, available_docs)
        assert doc_name in str(exception)

    def test_with_numeric_doc_names(self):
        exception = InvalidDocumentName('DFP123', ['DFP', 'ITR'])
        assert 'DFP123' in str(exception)

    def test_message_contains_string_keyword(self):
        exception = InvalidDocumentName('WRONG', ['DFP'])
        assert 'string' in str(exception).lower()


@pytest.mark.unit
class TestInvalidDocumentType:
    def test_message_format_exact_with_string_input(self):
        doc_name = '123'
        exception = InvalidDocumentType(doc_name)
        expected = (
            f'Invalid document type: {doc_name}. The document name must be a '
            'string.'
        )
        assert str(exception) == expected

    def test_message_format_exact_with_int_input(self):
        doc_name = 123
        exception = InvalidDocumentType(doc_name)
        expected = (
            f'Invalid document type: {doc_name}. The document name must be a '
            'string.'
        )
        assert str(exception) == expected

    def test_is_exception_subclass(self):
        exception = InvalidDocumentType(123)
        assert isinstance(exception, Exception)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(InvalidDocumentType) as exc_info:
            raise InvalidDocumentType(123)
        assert 'Invalid document type' in str(exc_info.value)

    def test_with_integer_value(self):
        exception = InvalidDocumentType(42)
        assert '42' in str(exception)
        assert 'must be a string' in str(exception)

    def test_with_float_value(self):
        exception = InvalidDocumentType(3.14)
        assert '3.14' in str(exception)
        assert 'must be a string' in str(exception)

    def test_with_none_value(self):
        exception = InvalidDocumentType(None)
        assert 'None' in str(exception)
        assert 'must be a string' in str(exception)

    def test_with_list_value(self):
        value = [1, 2, 3]
        exception = InvalidDocumentType(value)
        assert '[1, 2, 3]' in str(exception)
        assert 'must be a string' in str(exception)

    def test_with_dict_value(self):
        value = {'key': 'value'}
        exception = InvalidDocumentType(value)
        assert 'must be a string' in str(exception)

    def test_with_boolean_true(self):
        exception = InvalidDocumentType(True)
        assert 'True' in str(exception)
        assert 'must be a string' in str(exception)

    def test_with_boolean_false(self):
        exception = InvalidDocumentType(False)
        assert 'False' in str(exception)
        assert 'must be a string' in str(exception)

    def test_with_empty_string(self):
        exception = InvalidDocumentType('')
        assert '' in str(exception)

    def test_message_always_mentions_string_requirement(self):
        values = [123, 3.14, None, [], {}, True, False]
        for value in values:
            exception = InvalidDocumentType(value)
            assert 'must be a string' in str(exception).lower()


@pytest.mark.unit
class TestEmptyDocumentListError:
    def test_message_format(self):
        exception = EmptyDocumentListError()
        assert 'document list cannot be empty' in str(exception).lower()

    def test_is_exception_subclass(self):
        exception = EmptyDocumentListError()
        assert isinstance(exception, Exception)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(EmptyDocumentListError):
            raise EmptyDocumentListError()

    def test_suggests_alternative(self):
        exception = EmptyDocumentListError()
        exc_str = str(exception)
        assert 'empty' in exc_str.lower()

    def test_message_mentions_document_list(self):
        exception = EmptyDocumentListError()
        assert (
            'Document list' in str(exception)
            or 'list' in str(exception).lower()
        )


@pytest.mark.unit
class TestDomainExceptionsIntegration:
    def test_all_domain_exceptions_are_exceptions(self):
        exceptions = [
            InvalidFirstYear(1990, 2023),
            InvalidLastYear(2000, 2023),
            InvalidDocumentName('INVALID', ['DRE']),
            InvalidDocumentType(123),
            EmptyDocumentListError(),
        ]
        for exc in exceptions:
            assert isinstance(exc, Exception), (
                f'{type(exc).__name__} is not an Exception'
            )

    def test_catch_all_as_generic_exception(self):
        exceptions = [
            InvalidFirstYear(1990, 2023),
            InvalidLastYear(2000, 2023),
            InvalidDocumentName('INVALID', ['DRE']),
            InvalidDocumentType(123),
            EmptyDocumentListError(),
        ]
        for exc in exceptions:
            with pytest.raises(type(exc)):
                raise exc

    def test_specific_exception_catching(self):
        with pytest.raises(InvalidLastYear):
            try:
                raise InvalidLastYear(2000, 2023)
            except InvalidFirstYear:
                pass

    def test_all_exceptions_have_non_empty_messages(self):
        exceptions = [
            InvalidFirstYear(1990, 2023),
            InvalidLastYear(2000, 2023),
            InvalidDocumentName('INVALID', ['DRE']),
            InvalidDocumentType(123),
            EmptyDocumentListError(),
        ]
        for exc in exceptions:
            exc_str = str(exc)
            assert len(exc_str) > 0, f'{type(exc).__name__} has empty message'
            assert isinstance(exc_str, str), (
                f'{type(exc).__name__} message is not string'
            )

    def test_validation_workflow(self):
        def validate_document_selection(
            first_year,
            last_year,
            doc_name,
            valid_years_range=(1990, 2023),
            valid_docs=None,
        ):
            # ...existing code...
            if valid_docs is None:
                valid_docs = ['DRE', 'BPARMS', 'DMPL']
            minimal_year, current_year = valid_years_range

            if (
                not isinstance(first_year, int)
                or first_year < minimal_year
                or first_year > current_year
            ):
                raise InvalidFirstYear(minimal_year, current_year)

            if (
                not isinstance(last_year, int)
                or last_year < first_year
                or last_year > current_year
            ):
                raise InvalidLastYear(first_year, current_year)

            if not isinstance(doc_name, str):
                raise InvalidDocumentType(doc_name)

            if doc_name not in valid_docs:
                raise InvalidDocumentName(doc_name, valid_docs)

            return True

        assert validate_document_selection(2000, 2023, 'DRE')

        with pytest.raises(InvalidFirstYear):
            validate_document_selection(1989, 2023, 'DRE')

        with pytest.raises(InvalidLastYear):
            validate_document_selection(2020, 2024, 'DRE')

        with pytest.raises(InvalidDocumentType):
            validate_document_selection(2000, 2023, 123)

        with pytest.raises(InvalidDocumentName):
            validate_document_selection(2000, 2023, 'INVALID')

    def test_year_boundary_conditions(self):
        exc1 = InvalidFirstYear(2023, 2023)
        assert '2023' in str(exc1)

        exc2 = InvalidFirstYear(1900, 2100)
        assert '1900' in str(exc2) and '2100' in str(exc2)

    def test_doc_exceptions_with_many_documents(self):
        docs = [f'DOC_{i}' for i in range(1000)]
        exc = InvalidDocumentName('INVALID', docs)
        assert 'INVALID' in str(exc)
