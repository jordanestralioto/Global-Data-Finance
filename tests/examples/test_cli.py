"""Behavior checks for the examples' common command-line interface."""

import pytest

from examples.cli import parse_arguments, run_example, year_label
from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    InvalidFirstYear as B3InvalidFirstYear,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.errors import (
    InvalidFirstYear as CvmInvalidFirstYear,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('source', ['cvm', 'b3'])
def test_initial_year_alone_selects_exactly_one_year(source):
    args = parse_arguments(
        'Example', source=source, argv=['--initial-year', '2022']
    )

    assert (args.initial_year, args.last_year) == (2022, 2022)


@pytest.mark.parametrize(
    ('argv', 'diagnostic'),
    [
        (
            ['--initial-year', '2024', '--last-year', '2023'],
            '--last-year must be greater than or equal to --initial-year',
        ),
        (['--initial-year', 'invalid'], 'invalid int value'),
        (['--processing-mode', 'invalid'], 'invalid choice'),
    ],
)
def test_invalid_options_have_actionable_usage_errors(
    argv, diagnostic, capsys
):
    with pytest.raises(SystemExit) as error:
        parse_arguments('Example', source='b3', argv=argv)

    assert error.value.code == 2
    assert diagnostic in capsys.readouterr().err


@pytest.mark.parametrize(
    ('initial_year', 'last_year', 'expected'),
    [(2023, 2023, '2023'), (2022, 2023, '2022_2023')],
)
def test_output_names_describe_the_selected_period(
    initial_year, last_year, expected
):
    assert year_label(initial_year, last_year) == expected


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
