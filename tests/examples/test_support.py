"""Behavior checks for the editable examples' shared helpers."""

import sys

import pytest

from examples.support import (
    print_b3_summary,
    print_cvm_summary,
    run_example,
    year_label,
)
from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    InvalidFirstYear as B3InvalidFirstYear,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.core import (
    DownloadResultCVM,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.errors import (
    InvalidFirstYear as CvmInvalidFirstYear,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def example_invocation(monkeypatch):
    """Use the same argument list as a normal example invocation."""
    monkeypatch.setattr(sys, 'argv', ['example.py'])


@pytest.mark.parametrize(
    ('initial_year', 'last_year', 'expected'),
    [(2023, 2023, '2023'), (2022, 2023, '2022_2023')],
)
def test_output_names_describe_the_selected_period(
    initial_year, last_year, expected
):
    assert year_label(initial_year, last_year) == expected


def test_a_normal_invocation_runs_the_example_once():
    calls = []

    run_example(lambda: calls.append('ran'))

    assert calls == ['ran']


@pytest.mark.parametrize('options', [['--help'], ['--initial-year', '2023']])
def test_terminal_options_stop_before_processing(options, monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['example.py', *options])
    calls = []

    with pytest.raises(SystemExit) as error:
        run_example(lambda: calls.append('ran'))

    assert error.value.code == 2
    assert calls == []
    output = capsys.readouterr()
    assert output.out == ''
    assert 'Edit SETTINGS' in output.err


@pytest.mark.parametrize(
    'failure',
    [
        ValueError('Input directory does not exist'),
        OSError('Output directory is not writable'),
        B3InvalidFirstYear(1986, 2026),
        CvmInvalidFirstYear(2010, 2026),
    ],
)
def test_expected_failures_keep_the_diagnostic_and_exit_nonzero(
    failure, capsys
):
    def failing_main():
        raise failure

    with pytest.raises(SystemExit) as error:
        run_example(failing_main)

    assert error.value.code == 1
    assert error.value.__cause__ is failure
    diagnostic = capsys.readouterr().err
    assert str(failure) in diagnostic
    assert 'Traceback' not in diagnostic


def test_unexpected_failures_remain_visible():
    def failing_main():
        raise RuntimeError('Unexpected implementation defect')

    with pytest.raises(RuntimeError, match='implementation defect'):
        run_example(failing_main)


@pytest.mark.parametrize(
    ('successful_downloads', 'failed_downloads', 'should_fail'),
    [
        (['DFP_2023'], {}, False),
        (['DFP_2022'], {'DFP_2023': 'network error'}, True),
        ([], {}, True),
    ],
)
def test_cvm_result_must_have_successes_and_no_errors(
    successful_downloads, failed_downloads, should_fail, capsys
):
    result = DownloadResultCVM(
        successful_downloads=successful_downloads,
        failed_downloads=failed_downloads,
    )

    if should_fail:
        with pytest.raises(SystemExit) as error:
            print_cvm_summary(result, destination_path='./dados_cvm')

        assert error.value.code == 1
        output = capsys.readouterr()
        assert output.out == ''
        assert 'did not complete successfully' in output.err
        if failed_downloads:
            assert 'DFP_2023: network error' in output.err
    else:
        assert (
            print_cvm_summary(result, destination_path='./dados_cvm') is None
        )
        output = capsys.readouterr()
        assert 'completed successfully' in output.out
        assert 'Output directory: ./dados_cvm' in output.out
        assert 'Downloaded files count: 1' in output.out
        assert output.err == ''


def test_b3_result_requires_a_nonempty_output_file(tmp_path, capsys):
    output_file = tmp_path / 'quotes.parquet'
    output_file.write_bytes(b'parquet data')
    result = {
        'success': True,
        'total_files': 1,
        'total_records': 1,
        'output_file': str(output_file),
        'errors': {},
    }

    assert print_b3_summary(result, verbose=False) is None
    output = capsys.readouterr()
    assert 'completed successfully' in output.out
    assert str(output_file) in output.out
    assert 'Quote records: 1' in output.out
    assert output.err == ''


@pytest.mark.parametrize(
    ('success', 'total_files', 'total_records', 'create_output'),
    [
        (False, 1, 1, True),
        (True, 0, 1, True),
        (True, 1, 0, True),
        (True, 1, 1, False),
    ],
)
def test_b3_result_rejects_failure_empty_or_missing_output(
    tmp_path, success, total_files, total_records, create_output, capsys
):
    output_file = tmp_path / 'quotes.parquet'
    if create_output:
        output_file.write_bytes(b'parquet data')
    result = {
        'success': success,
        'total_files': total_files,
        'total_records': total_records,
        'output_file': str(output_file),
        'errors': {'COTAHIST_A2023.ZIP': 'invalid data'},
    }

    with pytest.raises(SystemExit) as error:
        print_b3_summary(result, verbose=False)

    assert error.value.code == 1
    output = capsys.readouterr()
    assert output.out == ''
    assert 'did not produce a non-empty Parquet file' in output.err
    assert 'COTAHIST_A2023.ZIP: invalid data' in output.err


def test_b3_result_rejects_empty_output_file(tmp_path, capsys):
    output_file = tmp_path / 'quotes.parquet'
    output_file.touch()
    result = {
        'success': True,
        'total_files': 1,
        'total_records': 1,
        'output_file': str(output_file),
        'errors': {},
    }

    with pytest.raises(SystemExit) as error:
        print_b3_summary(result, verbose=False)

    assert error.value.code == 1
    output = capsys.readouterr()
    assert output.out == ''
    assert 'did not produce a non-empty Parquet file' in output.err
