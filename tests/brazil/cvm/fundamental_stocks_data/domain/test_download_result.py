import pytest

from globaldatafinance.brazil.cvm.ingestion.models import DownloadResultCVM


@pytest.mark.unit
class TestDownloadResultInitialization:
    def test_init_with_defaults(self):
        result = DownloadResultCVM()

        assert result.successful_downloads == []
        assert result.failed_downloads == {}
        assert result.success_count_downloads == 0
        assert result.error_count_downloads == 0

    def test_init_with_successful_downloads_list(self):
        downloads = ['DFP_2020', 'DFP_2021']
        result = DownloadResultCVM(successful_downloads=downloads)

        assert result.successful_downloads == downloads
        assert result.success_count_downloads == 2

    def test_init_with_failed_downloads(self):
        failures = {
            'DFP_2020': 'Connection timeout',
            'ITR_2021': 'File not found',
        }
        result = DownloadResultCVM(failed_downloads=failures)

        assert result.failed_downloads == failures
        assert result.error_count_downloads == 2

    def test_init_with_both_parameters(self):
        downloads = ['DFP_2020']
        failures = {'ITR_2020': 'Error message'}
        result = DownloadResultCVM(
            successful_downloads=downloads, failed_downloads=failures
        )

        assert result.successful_downloads == downloads
        assert result.failed_downloads == failures


@pytest.mark.unit
class TestDownloadResultProperties:
    def test_success_count_downloads_with_empty_result(self):
        result = DownloadResultCVM()
        assert result.success_count_downloads == 0

    def test_success_count_downloads_calculation(self):
        downloads = ['DFP_2020', 'DFP_2021', 'ITR_2020']
        result = DownloadResultCVM(successful_downloads=downloads)

        assert result.success_count_downloads == 3

    def test_error_count_with_empty_result(self):
        result = DownloadResultCVM()
        assert result.error_count_downloads == 0

    def test_error_count_calculation(self):
        failures = {
            'DFP_2020': 'Error 1',
            'ITR_2021': 'Error 2',
            'FRE_2020': 'Error 3',
        }
        result = DownloadResultCVM(failed_downloads=failures)

        assert result.error_count_downloads == 3

    def test_success_count_downloads_is_readonly_property(self):
        result = DownloadResultCVM(successful_downloads=['DFP'])
        assert result.success_count_downloads == 1
        # Trying to set would raise AttributeError
        with pytest.raises(AttributeError):
            result.success_count_downloads = 5

    def test_error_count_is_readonly_property(self):
        result = DownloadResultCVM(failed_downloads={'DFP': 'Error'})
        assert result.error_count_downloads == 1
        # Trying to set would raise AttributeError
        with pytest.raises(AttributeError):
            result.error_count_downloads = 5


@pytest.mark.unit
class TestDownloadResultHasErrors:
    def test_has_errors_is_false_on_empty_result(self):
        result = DownloadResultCVM()
        assert result.has_errors() is False

    def test_has_errors_is_false_with_only_successes(self):
        result = DownloadResultCVM(successful_downloads=['DFP_2020'])
        assert result.has_errors() is False

    def test_has_errors_is_true_with_failures(self):
        result = DownloadResultCVM(failed_downloads={'DFP_2020': 'timeout'})
        assert result.has_errors() is True

    def test_has_errors_tracks_added_failures(self):
        result = DownloadResultCVM()
        assert result.has_errors() is False

        result.add_error_downloads('ITR_2021', 'File not found')
        assert result.has_errors() is True


@pytest.mark.unit
class TestDownloadResultAddSuccess:
    def test_add_success_to_empty_result(self):
        result = DownloadResultCVM()
        result.add_success_downloads('DFP_2020')

        assert 'DFP_2020' in result.successful_downloads
        assert result.success_count_downloads == 1

    def test_add_success_to_existing_result(self):
        result = DownloadResultCVM(successful_downloads=['DFP_2020'])
        result.add_success_downloads('DFP_2021')

        assert result.successful_downloads == ['DFP_2020', 'DFP_2021']
        assert result.success_count_downloads == 2

    def test_add_success_prevents_duplicates(self):
        result = DownloadResultCVM(successful_downloads=['DFP_2020'])
        result.add_success_downloads('DFP_2020')

        assert result.successful_downloads.count('DFP_2020') == 1
        assert result.success_count_downloads == 1

    def test_add_success_multiple_items(self):
        result = DownloadResultCVM()
        result.add_success_downloads('DFP_2020')
        result.add_success_downloads('ITR_2020')
        result.add_success_downloads('FRE_2020')

        assert result.success_count_downloads == 3
        assert 'DFP_2020' in result.successful_downloads
        assert 'ITR_2020' in result.successful_downloads
        assert 'FRE_2020' in result.successful_downloads


@pytest.mark.unit
class TestDownloadResultAddError:
    def test_add_error_to_empty_result(self):
        result = DownloadResultCVM()
        result.add_error_downloads('DFP_2020', 'Connection timeout')

        assert result.failed_downloads['DFP_2020'] == 'Connection timeout'
        assert result.error_count_downloads == 1

    def test_add_error_to_existing_result(self):
        result = DownloadResultCVM(failed_downloads={'DFP_2020': 'Error 1'})
        result.add_error_downloads('ITR_2021', 'Error 2')

        assert result.failed_downloads['DFP_2020'] == 'Error 1'
        assert result.failed_downloads['ITR_2021'] == 'Error 2'
        assert result.error_count_downloads == 2

    def test_add_error_overwrites_previous_error(self):
        result = DownloadResultCVM(failed_downloads={'DFP_2020': 'Error 1'})
        result.add_error_downloads('DFP_2020', 'Error 2')

        assert result.failed_downloads['DFP_2020'] == 'Error 2'
        assert result.error_count_downloads == 1

    def test_add_multiple_errors(self):
        result = DownloadResultCVM()
        result.add_error_downloads('DFP_2020', 'Error 1')
        result.add_error_downloads('ITR_2021', 'Error 2')
        result.add_error_downloads('FRE_2022', 'Error 3')

        assert result.error_count_downloads == 3


@pytest.mark.unit
class TestDownloadResultStringRepresentation:
    def test_str_format_with_data(self):
        result = DownloadResultCVM(
            successful_downloads=['DFP_2020', 'DFP_2021'],
            failed_downloads={'ITR_2020': 'Error'},
        )
        str_repr = str(result)

        assert 'success=2' in str_repr
        assert 'errors=1' in str_repr

    def test_str_format_with_empty_result(self):
        result = DownloadResultCVM()
        str_repr = str(result)

        assert 'success=0' in str_repr
        assert 'errors=0' in str_repr

    def test_str_format_only_successes(self):
        result = DownloadResultCVM(
            successful_downloads=['DFP_2020', 'DFP_2021', 'ITR_2020']
        )
        str_repr = str(result)

        assert 'success=3' in str_repr
        assert 'errors=0' in str_repr

    def test_str_format_only_errors(self):
        result = DownloadResultCVM(
            failed_downloads={'DFP_2020': 'E1', 'ITR_2020': 'E2'}
        )
        str_repr = str(result)

        assert 'success=0' in str_repr
        assert 'errors=2' in str_repr


@pytest.mark.unit
class TestDownloadResultIntegration:
    def test_mixed_operations(self):
        result = DownloadResultCVM()

        # Add successes
        result.add_success_downloads('DFP_2020')
        result.add_success_downloads('DFP_2021')
        result.add_success_downloads('ITR_2020')

        # Add errors
        result.add_error_downloads('FRE_2020', 'Connection timeout')
        result.add_error_downloads('VLMO_2020', 'File not found')

        # Verify state
        assert result.success_count_downloads == 3
        assert result.error_count_downloads == 2
        assert 'DFP_2020' in result.successful_downloads
        assert 'FRE_2020' in result.failed_downloads

    def test_result_as_return_value(self):
        def simulate_download(
            should_succeed: bool, item: str
        ) -> DownloadResultCVM:
            result = DownloadResultCVM()

            if should_succeed:
                result.add_success_downloads(item)
            else:
                result.add_error_downloads(item, 'Download failed')

            return result

        success_result = simulate_download(True, 'DFP_2020')
        assert success_result.success_count_downloads == 1
        assert success_result.error_count_downloads == 0

        failure_result = simulate_download(False, 'DFP_2020')
        assert failure_result.success_count_downloads == 0
        assert failure_result.error_count_downloads == 1

    def test_complete_workflow(self):
        result = DownloadResultCVM()

        # Simulate downloading multiple documents and years
        documents = ['DFP', 'ITR', 'FRE']
        years = [2020, 2021, 2022]

        for doc in documents:
            for year in years:
                item = f'{doc}_{year}'
                if year == 2021 and doc == 'ITR':
                    # Simulate one failure
                    result.add_error_downloads(item, 'Network error')
                else:
                    result.add_success_downloads(item)

        # Verify counts
        assert (
            result.success_count_downloads == 8
        )  # 3 docs * 3 years - 1 failure
        assert result.error_count_downloads == 1

        # Verify specific items
        assert 'DFP_2020' in result.successful_downloads
        assert 'ITR_2021' in result.failed_downloads
        assert 'FRE_2022' in result.successful_downloads

    def test_error_messages_are_preserved(self):
        result = DownloadResultCVM()
        error_msg = 'Network error: Connection timeout after 30 seconds'
        result.add_error_downloads('DFP_2020', error_msg)

        assert result.failed_downloads['DFP_2020'] == error_msg

    def test_large_scale_operations(self):
        result = DownloadResultCVM()

        # Add 100 successes
        for i in range(100):
            result.add_success_downloads(f'DOC_{i}')

        assert result.success_count_downloads == 100
        assert result.error_count_downloads == 0

        # Add 50 errors
        for i in range(50):
            result.add_error_downloads(f'ERR_{i}', f'Error message {i}')

        assert result.success_count_downloads == 100
        assert result.error_count_downloads == 50

    def test_adding_same_success_multiple_times(self):
        result = DownloadResultCVM()

        result.add_success_downloads('DFP_2020')
        result.add_success_downloads('DFP_2020')
        result.add_success_downloads('DFP_2020')

        assert result.success_count_downloads == 1
        assert result.successful_downloads.count('DFP_2020') == 1

    def test_adding_same_error_multiple_times_overwrites(self):
        result = DownloadResultCVM()

        result.add_error_downloads('DFP_2020', 'First error')
        result.add_error_downloads('DFP_2020', 'Second error')
        result.add_error_downloads('DFP_2020', 'Third error')

        assert result.error_count_downloads == 1
        assert result.failed_downloads['DFP_2020'] == 'Third error'

    def test_interleaving_success_and_error_for_different_items(self):
        result = DownloadResultCVM()

        result.add_success_downloads('DFP_2020')
        result.add_error_downloads('ITR_2020', 'Error 1')
        result.add_success_downloads('DFP_2021')
        result.add_error_downloads('FRE_2020', 'Error 2')
        result.add_success_downloads('DFP_2022')

        assert result.success_count_downloads == 3
        assert result.error_count_downloads == 2

    def test_empty_string_as_item_name(self):
        result = DownloadResultCVM()

        result.add_success_downloads('')
        result.add_error_downloads('', 'Empty item error')

        assert result.success_count_downloads == 1
        assert result.error_count_downloads == 1
        assert '' in result.successful_downloads
        assert '' in result.failed_downloads

    def test_unicode_in_item_names_and_errors(self):
        result = DownloadResultCVM()

        result.add_success_downloads('文档_2020')
        result.add_error_downloads('документ_2021', 'Ошибка загрузки')

        assert result.success_count_downloads == 1
        assert result.error_count_downloads == 1
        assert '文档_2020' in result.successful_downloads
        assert 'Ошибка загрузки' in result.failed_downloads.values()

    def test_long_error_messages(self):
        result = DownloadResultCVM()
        long_error = 'A' * 10000  # 10k character error message

        result.add_error_downloads('DFP_2020', long_error)

        assert result.failed_downloads['DFP_2020'] == long_error
        assert len(result.failed_downloads['DFP_2020']) == 10000

    def test_dataclass_equality(self):
        result1 = DownloadResultCVM(
            successful_downloads=['DFP_2020', 'ITR_2020'],
            failed_downloads={'FRE_2020': 'Error'},
        )

        result2 = DownloadResultCVM(
            successful_downloads=['DFP_2020', 'ITR_2020'],
            failed_downloads={'FRE_2020': 'Error'},
        )

        assert result1 == result2

    def test_dataclass_inequality(self):
        result1 = DownloadResultCVM(successful_downloads=['DFP_2020'])
        result2 = DownloadResultCVM(successful_downloads=['ITR_2020'])

        assert result1 != result2

    def test_result_is_mutable(self):
        result = DownloadResultCVM(successful_downloads=['DFP_2020'])

        # Should allow adding more items
        result.add_success_downloads('ITR_2020')
        result.add_error_downloads('FRE_2020', 'Error')

        assert result.success_count_downloads == 2
        assert result.error_count_downloads == 1

    def test_clearing_lists_affects_counts(self):
        result = DownloadResultCVM(
            successful_downloads=['DFP_2020', 'ITR_2020'],
            failed_downloads={'FRE_2020': 'Error'},
        )

        result.successful_downloads.clear()
        result.failed_downloads.clear()

        assert result.success_count_downloads == 0
        assert result.error_count_downloads == 0

    def test_handling_very_long_item_names(self):
        result = DownloadResultCVM()
        long_name = 'A' * 1000  # 1000 character name

        result.add_success_downloads(long_name)
        result.add_error_downloads(long_name + '_error', 'Error message')

        assert long_name in result.successful_downloads
        assert (long_name + '_error') in result.failed_downloads

    def test_adding_none_as_item_raises_no_error(self):
        result = DownloadResultCVM()

        # This should work without raising TypeError
        result.add_success_downloads(None)
        result.add_error_downloads(None, 'Error for None')

        assert None in result.successful_downloads
        assert None in result.failed_downloads

    def test_error_message_with_newlines(self):
        result = DownloadResultCVM()
        multiline_error = 'Error line 1\nError line 2\nError line 3'

        result.add_error_downloads('DFP_2020', multiline_error)

        assert result.failed_downloads['DFP_2020'] == multiline_error
        assert '\n' in result.failed_downloads['DFP_2020']

    def test_concurrent_modifications_simulation(self):
        result = DownloadResultCVM()

        # Add items rapidly
        for i in range(100):
            result.add_success_downloads(f'item_{i}')
            if i % 2 == 0:
                result.add_error_downloads(f'error_{i}', f'Error {i}')

        assert result.success_count_downloads == 100
        assert result.error_count_downloads == 50

    def test_special_characters_in_error_messages(self):
        result = DownloadResultCVM()
        special_chars_error = 'Error: <>&"\'`\t\r\n\x00'

        result.add_error_downloads('DFP_2020', special_chars_error)

        assert result.failed_downloads['DFP_2020'] == special_chars_error

    def test_mixed_types_in_successful_downloads(self):
        result = DownloadResultCVM()

        result.add_success_downloads('regular_string')
        result.add_success_downloads('string_with_números_123')
        result.add_success_downloads('string-with-dashes')
        result.add_success_downloads('string_with_underscores')
        result.add_success_downloads('String.With.Dots')

        assert result.success_count_downloads == 5

    def test_repr_or_str_doesnt_include_sensitive_data(self):
        result = DownloadResultCVM(
            successful_downloads=['source_file_1', 'source_file_2'],
            failed_downloads={
                'source_file_3': 'Download details unavailable.'
            },
        )

        str_repr = str(result)

        assert 'source_file_3' not in str_repr
        assert 'Download details unavailable.' not in str_repr
        assert 'success=2' in str_repr
        assert 'errors=1' in str_repr

    def test_add_success_with_same_item_different_case(self):
        result = DownloadResultCVM()

        result.add_success_downloads('DFP_2020')
        result.add_success_downloads('dfp_2020')  # lowercase
        result.add_success_downloads('DfP_2020')  # mixed case

        # These are different strings, so all should be added
        assert result.success_count_downloads == 3

    def test_error_message_preservation_with_quotes(self):
        result = DownloadResultCVM()
        error_with_quotes = 'Error: "Connection timeout" at \'line 42\''

        result.add_error_downloads('DFP_2020', error_with_quotes)

        assert result.failed_downloads['DFP_2020'] == error_with_quotes

    def test_batch_operations_maintain_consistency(self):
        result = DownloadResultCVM()

        # Batch add successes
        items = [f'DFP_{year}' for year in range(2010, 2025)]
        for item in items:
            result.add_success_downloads(item)

        # Batch add errors
        for year in range(2010, 2015):
            result.add_error_downloads(f'ITR_{year}', f'Error for {year}')

        assert result.success_count_downloads == 15
        assert result.error_count_downloads == 5

        # Verify data integrity
        assert all(
            f'DFP_{year}' in result.successful_downloads
            for year in range(2010, 2025)
        )
        assert all(
            f'ITR_{year}' in result.failed_downloads
            for year in range(2010, 2015)
        )
