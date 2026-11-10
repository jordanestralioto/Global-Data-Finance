import pytest

from globaldatafinance.application.cvm_docs.download_result_formatter import (
    DownloadResultFormatter,
)
from globaldatafinance.brazil.cvm.ingestion.models import DownloadResultCVM
from tests.support.console import legacy_code_page_stdout

pytestmark = pytest.mark.unit


class TestDownloadResultFormatter:
    def test_initialization_with_colors_enabled(self):
        formatter = DownloadResultFormatter(use_colors=True)
        assert formatter.use_colors is True

    def test_initialization_with_colors_disabled(self):
        formatter = DownloadResultFormatter(use_colors=False)
        assert formatter.use_colors is False

    def test_initialization_default_colors_enabled(self):
        formatter = DownloadResultFormatter()
        assert formatter.use_colors is True

    def test_colorize_applies_color_when_enabled(self):
        formatter = DownloadResultFormatter(use_colors=True)
        result = formatter._colorize('test', formatter.GREEN)
        assert formatter.GREEN in result
        assert formatter.RESET in result
        assert 'test' in result

    def test_colorize_returns_plain_text_when_disabled(self):
        formatter = DownloadResultFormatter(use_colors=False)
        result = formatter._colorize('test', formatter.GREEN)
        assert result == 'test'
        assert formatter.GREEN not in result

    def test_format_result_all_successful(self):
        formatter = DownloadResultFormatter(use_colors=False)
        result = DownloadResultCVM()
        result.add_success_downloads('DFP_2023.zip')
        result.add_success_downloads('ITR_2023.zip')
        output = formatter.format_result(result)
        assert 'Documents downloaded successfully!' in output
        assert 'Summary:' in output
        assert 'Total files: 2' in output
        assert 'Success: 2' in output
        assert 'CVM Documents Download' in output

    def test_format_result_with_failures(self):
        formatter = DownloadResultFormatter(use_colors=False)
        result = DownloadResultCVM()
        result.add_success_downloads('DFP_2023.zip')
        result.add_error_downloads('ITR_2023.zip', 'Connection timeout')
        output = formatter.format_result(result)
        assert 'Download completed with some errors.' in output
        assert 'Errors:' in output
        assert 'ITR - 2023.zip' in output
        assert 'Connection timeout' in output
        assert 'Summary:' in output
        assert 'Success: 1' in output
        assert 'Errors: 1' in output

    def test_format_result_only_failures(self):
        formatter = DownloadResultFormatter(use_colors=False)
        result = DownloadResultCVM()
        result.add_error_downloads('DFP_2023.zip', 'Network error')
        result.add_error_downloads('ITR_2023.zip', 'File not found')
        output = formatter.format_result(result)
        assert 'Document download failed.' in output
        assert 'Errors:' in output
        assert 'DFP - 2023.zip' in output
        assert 'ITR - 2023.zip' in output
        assert 'Network error' in output
        assert 'File not found' in output
        assert 'Summary:' in output
        assert 'Success: 0' in output
        assert 'Errors: 2' in output

    def test_format_result_displays_header(self):
        formatter = DownloadResultFormatter(use_colors=False)
        result = DownloadResultCVM()
        result.add_success_downloads('DFP_2023.zip')
        output = formatter.format_result(result)
        assert 'CVM Documents Download' in output
        assert (
            '━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━'
            in output
        )

    def test_format_result_empty_result(self):
        formatter = DownloadResultFormatter(use_colors=False)
        result = DownloadResultCVM()
        output = formatter.format_result(result)
        assert 'CVM Documents Download' in output
        assert 'Document download failed.' in output

    def test_format_result_multiple_failures(self):
        formatter = DownloadResultFormatter(use_colors=False)
        result = DownloadResultCVM()
        result.add_success_downloads('DFP_2022.zip')
        result.add_error_downloads('ITR_2022.zip', 'Network error')
        result.add_error_downloads('FCA_2022.zip', 'File corrupted')
        result.add_error_downloads('FRE_2022.zip', 'Timeout')
        output = formatter.format_result(result)
        assert 'Download completed with some errors.' in output
        assert 'Errors:' in output
        assert 'ITR - 2022.zip' in output
        assert 'Network error' in output
        assert 'FCA - 2022.zip' in output
        assert 'File corrupted' in output
        assert 'FRE - 2022.zip' in output
        assert 'Timeout' in output

    def test_format_result_with_colors_contains_ansi_codes(self):
        formatter = DownloadResultFormatter(use_colors=True)
        result = DownloadResultCVM()
        result.add_success_downloads('DFP_2023.zip')
        output = formatter.format_result(result)
        assert '\033[' in output

    def test_format_result_without_colors_no_ansi_codes(self):
        formatter = DownloadResultFormatter(use_colors=False)
        result = DownloadResultCVM()
        result.add_success_downloads('DFP_2023.zip')
        output = formatter.format_result(result)
        assert '\033[' not in output

    def test_print_result_calls_format_and_prints(self, capsys):
        formatter = DownloadResultFormatter(use_colors=False)
        result = DownloadResultCVM()
        result.add_success_downloads('DFP_2023.zip')
        formatter.print_result(result)
        captured = capsys.readouterr()
        assert 'CVM Documents Download' in captured.out
        assert 'Documents downloaded successfully!' in captured.out

    def test_print_result_with_errors(self, capsys):
        formatter = DownloadResultFormatter(use_colors=False)
        result = DownloadResultCVM()
        result.add_success_downloads('DFP_2023.zip')
        result.add_error_downloads('ITR_2023.zip', 'Error')
        formatter.print_result(result)
        captured = capsys.readouterr()
        assert 'CVM Documents Download' in captured.out
        assert 'Download completed with some errors.' in captured.out

    def test_color_constants_are_defined(self):
        formatter = DownloadResultFormatter()
        assert hasattr(formatter, 'GREEN')
        assert hasattr(formatter, 'RED')
        assert hasattr(formatter, 'YELLOW')
        assert hasattr(formatter, 'BLUE')
        assert hasattr(formatter, 'CYAN')
        assert hasattr(formatter, 'BOLD')
        assert hasattr(formatter, 'RESET')

    def test_format_result_preserves_newlines(self):
        formatter = DownloadResultFormatter(use_colors=False)
        result = DownloadResultCVM()
        result.add_success_downloads('file.zip')
        output = formatter.format_result(result)
        assert '\n' in output
        assert output.count('\n') > 3

    def test_format_result_summary_calculation_accuracy(self):
        formatter = DownloadResultFormatter(use_colors=False)
        result = DownloadResultCVM()
        for i in range(7):
            result.add_success_downloads(f'success_{i}.zip')
        for i in range(3):
            result.add_error_downloads(f'error_{i}.zip', f'Error {i}')
        output = formatter.format_result(result)
        assert 'Total files: 10' in output
        assert 'Success: 7' in output
        assert 'Errors: 3' in output

    def test_format_result_displays_error_indicators(self):
        formatter = DownloadResultFormatter(use_colors=False)
        result = DownloadResultCVM()
        result.add_error_downloads('file.zip', 'Test error')
        output = formatter.format_result(result)
        assert '•' in output

    def test_print_result_survives_legacy_code_page(self) -> None:
        """A finished download summary cannot fail after the work is done."""
        result = DownloadResultCVM()
        result.add_success_downloads('DFP_2023.zip')
        result.add_error_downloads('ITR_2023.zip', 'Connection timeout')

        with legacy_code_page_stdout() as written:
            DownloadResultFormatter(use_colors=False).print_result(result)

        output = written()
        assert 'Download completed with some errors.' in output
        assert 'ITR - 2023.zip' in output
        assert 'Connection timeout' in output
        assert 'Success: 1' in output
