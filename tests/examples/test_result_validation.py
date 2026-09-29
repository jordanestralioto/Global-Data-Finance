from types import SimpleNamespace

import pytest

from examples.result_validation import (
    require_b3_output,
    require_cvm_download_success,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ('errors', 'successes', 'failed_downloads', 'should_fail'),
    [
        (0, 1, {}, False),
        (1, 1, {'DFP_2023': 'network error'}, True),
        (0, 0, {}, True),
    ],
)
def test_cvm_result_must_have_successes_and_no_errors(
    errors, successes, failed_downloads, should_fail, capsys
):
    result = SimpleNamespace(
        error_count_downloads=errors,
        success_count_downloads=successes,
        failed_downloads=failed_downloads,
    )

    if should_fail:
        with pytest.raises(SystemExit) as error:
            require_cvm_download_success(result)

        assert error.value.code == 1
        error_output = capsys.readouterr().err
        assert 'did not complete successfully' in error_output
        if failed_downloads:
            assert 'DFP_2023: network error' in error_output
    else:
        assert require_cvm_download_success(result) is None


def test_b3_result_requires_a_nonempty_output_file(tmp_path):
    output_file = tmp_path / 'quotes.parquet'
    output_file.write_bytes(b'parquet data')

    result = {
        'success': True,
        'total_files': 1,
        'total_records': 1,
        'output_file': str(output_file),
        'errors': {},
    }

    assert require_b3_output(result) is None


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
        require_b3_output(result)

    assert error.value.code == 1
    error_output = capsys.readouterr().err
    assert 'did not produce a non-empty Parquet file' in error_output
    assert 'COTAHIST_A2023.ZIP: invalid data' in error_output


def test_b3_result_rejects_empty_output_file(tmp_path):
    output_file = tmp_path / 'quotes.parquet'
    output_file.touch()
    result = {
        'success': True,
        'total_files': 1,
        'total_records': 1,
        'output_file': str(output_file),
        'errors': {},
    }

    with pytest.raises(SystemExit):
        require_b3_output(result)
