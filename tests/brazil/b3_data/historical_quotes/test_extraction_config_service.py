"""Unit tests for ``ExtractionConfigServiceB3.validate_output_filename``.

Regression coverage for finding F1 (path traversal via ``output_filename``):
malicious values must fail with :class:`InvalidOutputFilename` before any
filesystem side effect; legitimate basenames must pass unchanged.
"""

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    InvalidOutputFilename,
)
from globaldatafinance.brazil.b3_data.historical_quotes.processing import (
    ExtractionConfigServiceB3,
)

pytestmark = pytest.mark.unit


class TestValidateOutputFilenameRejectsTraversal:
    def test_rejects_relative_dotdot_traversal(self):
        with pytest.raises(InvalidOutputFilename):
            ExtractionConfigServiceB3.validate_output_filename(
                '../../etc/passwd_pwn.parquet'
            )

    def test_rejects_subdirectory_in_filename(self):
        with pytest.raises(InvalidOutputFilename):
            ExtractionConfigServiceB3.validate_output_filename(
                'subdir/file.parquet'
            )

    def test_rejects_backslash_separator(self):
        with pytest.raises(InvalidOutputFilename):
            ExtractionConfigServiceB3.validate_output_filename('a\\b.parquet')

    def test_rejects_absolute_posix_path(self):
        with pytest.raises(InvalidOutputFilename):
            ExtractionConfigServiceB3.validate_output_filename(
                '/absolute/path/x.parquet'
            )

    def test_rejects_windows_drive_with_backslash(self):
        with pytest.raises(InvalidOutputFilename):
            ExtractionConfigServiceB3.validate_output_filename(
                'C:\\Windows\\x.parquet'
            )

    def test_rejects_windows_drive_with_forward_slash(self):
        with pytest.raises(InvalidOutputFilename):
            ExtractionConfigServiceB3.validate_output_filename(
                'C:/Windows/x.parquet'
            )

    def test_rejects_dotdot_alone(self):
        with pytest.raises(InvalidOutputFilename):
            ExtractionConfigServiceB3.validate_output_filename('..')

    def test_rejects_security_audit_poc_literal(self):
        """Regression: preserve the exact security audit PoC value."""
        with pytest.raises(InvalidOutputFilename):
            ExtractionConfigServiceB3.validate_output_filename(
                '../../../home/jordan/.bashrc_pwn_poc.parquet'
            )

    def test_rejects_empty_string(self):
        with pytest.raises(InvalidOutputFilename):
            ExtractionConfigServiceB3.validate_output_filename('')

    def test_rejects_whitespace_only(self):
        with pytest.raises(InvalidOutputFilename):
            ExtractionConfigServiceB3.validate_output_filename('   ')

    def test_rejects_non_string_input(self):
        with pytest.raises(TypeError):
            ExtractionConfigServiceB3.validate_output_filename(123)  # type: ignore[arg-type]


class TestValidateOutputFilenameAcceptsValid:
    def test_accepts_basename_with_parquet_suffix(self):
        assert (
            ExtractionConfigServiceB3.validate_output_filename(
                'custom.parquet'
            )
            == 'custom.parquet'
        )

    def test_accepts_basename_without_suffix_appends_parquet(self):
        assert (
            ExtractionConfigServiceB3.validate_output_filename(
                'cotahist_extracted'
            )
            == 'cotahist_extracted.parquet'
        )

    def test_accepts_basename_with_underscores_and_digits(self):
        assert (
            ExtractionConfigServiceB3.validate_output_filename(
                'with_underscores_123'
            )
            == 'with_underscores_123.parquet'
        )

    def test_accepts_multi_asset_history_basename(self):
        assert (
            ExtractionConfigServiceB3.validate_output_filename(
                'multi_asset_history'
            )
            == 'multi_asset_history.parquet'
        )
