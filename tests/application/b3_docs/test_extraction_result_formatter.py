import pytest

from globaldatafinance.application.b3_docs.extraction_result_formatter import (
    ExtractionResultFormatter,
)

pytestmark = pytest.mark.unit


class TestExtractionResultFormatter:
    def test_initialization_with_colors_enabled(self):
        formatter = ExtractionResultFormatter(use_colors=True)
        assert formatter.use_colors is True

    def test_initialization_with_colors_disabled(self):
        formatter = ExtractionResultFormatter(use_colors=False)
        assert formatter.use_colors is False

    def test_initialization_default_colors_enabled(self):
        formatter = ExtractionResultFormatter()
        assert formatter.use_colors is True

    def test_colorize_applies_color_when_enabled(self):
        formatter = ExtractionResultFormatter(use_colors=True)
        result = formatter._colorize('test', formatter.GREEN)
        assert formatter.GREEN in result
        assert formatter.RESET in result
        assert 'test' in result

    def test_colorize_returns_plain_text_when_disabled(self):
        formatter = ExtractionResultFormatter(use_colors=False)
        result = formatter._colorize('test', formatter.GREEN)
        assert result == 'test'
        assert formatter.GREEN not in result
        assert formatter.RESET not in result

    def test_print_result_with_successful_extraction(self, capsys):
        formatter = ExtractionResultFormatter(use_colors=False)
        result = {
            'success': True,
            'message': 'All files processed successfully',
            'total_files': 10,
            'success_count': 10,
            'error_count': 0,
            'total_records': 50000,
            'output_file': '/path/to/output.parquet',
            'assets': ['ações'],
            'processing_mode': 'fast',
            'elapsed_time': 10.5,
        }
        formatter.print_result(result)
        captured = capsys.readouterr()
        assert 'Extraction completed successfully!' in captured.out
        assert '/path/to/output.parquet' in captured.out

    def test_print_result_with_errors(self, capsys):
        formatter = ExtractionResultFormatter(use_colors=False)
        result = {
            'success': False,
            'message': 'Extraction completed with errors',
            'total_files': 10,
            'success_count': 7,
            'error_count': 3,
            'total_records': 35000,
            'output_file': '/path/to/output.parquet',
            'errors': {
                'file1.zip': 'Corrupted file',
                'file2.zip': 'Network timeout',
            },
        }
        formatter.print_result(result)
        captured = capsys.readouterr()
        assert 'Extraction completed with errors!' in captured.out
        assert 'file1.zip' in captured.out
        assert 'Corrupted file' in captured.out

    def test_print_result_displays_header(self, capsys):
        formatter = ExtractionResultFormatter(use_colors=False)
        result = {
            'success': True,
            'message': 'Success',
            'total_files': 5,
            'success_count': 5,
            'error_count': 0,
            'total_records': 10000,
            'output_file': '/output.parquet',
        }
        formatter.print_result(result)
        captured = capsys.readouterr()
        assert '📊 B3 Historical Quotes Extraction' in captured.out
        assert (
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
            in captured.out
        )

    def test_print_result_displays_statistics_section(self, capsys):
        formatter = ExtractionResultFormatter(use_colors=False)
        result = {
            'success': True,
            'message': 'Success',
            'total_files': 8,
            'success_count': 8,
            'error_count': 0,
            'total_records': 40000,
            'output_file': '/output.parquet',
        }
        formatter.print_result(result)
        captured = capsys.readouterr()
        assert '📈 Summary:' in captured.out
        assert '8' in captured.out

    def test_print_result_shows_error_details_for_dict_errors(self, capsys):
        formatter = ExtractionResultFormatter(use_colors=False)
        result = {
            'success': False,
            'message': 'Errors occurred',
            'total_files': 5,
            'success_count': 3,
            'error_count': 2,
            'total_records': 15000,
            'output_file': '/output.parquet',
            'errors': {
                '/path/to/file1.zip': 'Connection timeout',
                '/path/to/file2.zip': 'Invalid data',
            },
        }
        formatter.print_result(result)
        captured = capsys.readouterr()
        assert (
            '/path/to/file1.zip' in captured.out or 'file1.zip' in captured.out
        )

    def test_print_result_shows_error_details_for_list_errors(self, capsys):
        formatter = ExtractionResultFormatter(use_colors=False)
        result = {
            'success': False,
            'message': 'Errors occurred',
            'total_files': 5,
            'success_count': 3,
            'error_count': 2,
            'total_records': 15000,
            'output_file': '/output.parquet',
            'errors': [
                'Error 1: Failed to read file',
                'Error 2: Network issue',
            ],
        }
        formatter.print_result(result)
        captured = capsys.readouterr()
        assert 'Error 1' in captured.out or 'Error 2' in captured.out

    def test_print_result_formats_large_record_count(self, capsys):
        formatter = ExtractionResultFormatter(use_colors=False)
        result = {
            'success': True,
            'message': 'Success',
            'total_files': 20,
            'success_count': 20,
            'error_count': 0,
            'total_records': 1500000,
            'output_file': '/output.parquet',
        }
        formatter.print_result(result)
        captured = capsys.readouterr()
        assert '1,500,000' in captured.out or '1500000' in captured.out

    def test_print_result_handles_missing_message(self, capsys):
        formatter = ExtractionResultFormatter(use_colors=False)
        result = {
            'success': True,
            'total_files': 5,
            'success_count': 5,
            'error_count': 0,
            'total_records': 10000,
            'output_file': '/output.parquet',
        }
        formatter.print_result(result)
        captured = capsys.readouterr()
        assert 'Extraction completed successfully!' in captured.out

    def test_print_result_handles_zero_records(self, capsys):
        formatter = ExtractionResultFormatter(use_colors=False)
        result = {
            'success': True,
            'message': 'No data found',
            'total_files': 5,
            'success_count': 5,
            'error_count': 0,
            'total_records': 0,
            'output_file': '/output.parquet',
        }
        formatter.print_result(result)
        captured = capsys.readouterr()
        assert '0' in captured.out

    def test_print_result_with_colors_contains_ansi_codes(self, capsys):
        formatter = ExtractionResultFormatter(use_colors=True)
        result = {
            'success': True,
            'message': 'Success',
            'total_files': 5,
            'success_count': 5,
            'error_count': 0,
            'total_records': 10000,
            'output_file': '/output.parquet',
        }
        formatter.print_result(result)
        captured = capsys.readouterr()
        assert '\033[' in captured.out

    def test_print_result_without_colors_no_ansi_codes(self, capsys):
        formatter = ExtractionResultFormatter(use_colors=False)
        result = {
            'success': True,
            'message': 'Success',
            'total_files': 5,
            'success_count': 5,
            'error_count': 0,
            'total_records': 10000,
            'output_file': '/output.parquet',
        }
        formatter.print_result(result)
        captured = capsys.readouterr()
        assert '\033[' not in captured.out

    def test_color_constants_are_defined(self):
        formatter = ExtractionResultFormatter()
        assert hasattr(formatter, 'GREEN')
        assert hasattr(formatter, 'RED')
        assert hasattr(formatter, 'YELLOW')
        assert hasattr(formatter, 'BLUE')
        assert hasattr(formatter, 'CYAN')
        assert hasattr(formatter, 'BOLD')
        assert hasattr(formatter, 'RESET')
