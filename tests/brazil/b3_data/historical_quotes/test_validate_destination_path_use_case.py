import os
from pathlib import Path
from unittest.mock import patch

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.client import (
    VerifyDestinationPathsUseCaseB3,
)
from globaldatafinance.macro_exceptions import (
    InvalidDestinationPathError,
    PathIsNotDirectoryError,
    PathPermissionError,
    SecurityError,
)

pytestmark = pytest.mark.unit


class TestVerifyDestinationPathsUseCaseB3:
    def test_execute_with_valid_existing_directory(self, tmp_path):
        test_dir = tmp_path / 'test_output'
        test_dir.mkdir()

        result = VerifyDestinationPathsUseCaseB3.execute(str(test_dir))

        assert result == test_dir.resolve()

    def test_execute_creates_non_existing_directory(self, tmp_path):
        test_dir = tmp_path / 'new_output'
        assert not test_dir.exists()

        VerifyDestinationPathsUseCaseB3.execute(str(test_dir))

        assert test_dir.exists()
        assert test_dir.is_dir()

    def test_execute_creates_nested_directories(self, tmp_path):
        nested_dir = tmp_path / 'level1' / 'level2' / 'level3'
        assert not nested_dir.exists()

        VerifyDestinationPathsUseCaseB3.execute(str(nested_dir))

        assert nested_dir.exists()
        assert nested_dir.is_dir()

    def test_execute_raises_type_error_for_non_string(self):
        with pytest.raises(TypeError) as exc_info:
            VerifyDestinationPathsUseCaseB3.execute(123)

        assert 'must be a string' in str(exc_info.value)

    def test_execute_raises_type_error_for_none(self):
        with pytest.raises(TypeError) as exc_info:
            VerifyDestinationPathsUseCaseB3.execute(None)

        assert 'must be a string' in str(exc_info.value)

    def test_execute_raises_type_error_for_list(self):
        with pytest.raises(TypeError) as exc_info:
            VerifyDestinationPathsUseCaseB3.execute(['/path/to/output'])

        assert 'must be a string' in str(exc_info.value)

    def test_execute_raises_invalid_destination_path_for_empty_string(self):
        with pytest.raises(InvalidDestinationPathError) as exc_info:
            VerifyDestinationPathsUseCaseB3.execute('')

        assert 'cannot be empty' in str(exc_info.value)

    def test_execute_raises_invalid_destination_path_for_whitespace(self):
        with pytest.raises(InvalidDestinationPathError) as exc_info:
            VerifyDestinationPathsUseCaseB3.execute('   ')

        assert 'cannot be empty or whitespace' in str(exc_info.value)

    @pytest.mark.parametrize(
        'blocked_path',
        ['/etc', '/root', '/sys', '/proc', '/dev', '/boot'],
    )
    def test_execute_blocks_sensitive_paths(self, blocked_path):
        with pytest.raises(SecurityError):
            VerifyDestinationPathsUseCaseB3.execute(blocked_path)

    @pytest.mark.parametrize(
        'blocked_path',
        ['/', 'D:\\', 'D:\\Windows', '\\\\server\\share\\output'],
    )
    def test_execute_blocks_unsafe_roots_before_directory_creation(
        self,
        blocked_path,
    ):
        """Unsafe POSIX, drive, and UNC roots never reach ``mkdir``."""
        with (
            patch.object(Path, 'mkdir') as mkdir,
            pytest.raises(SecurityError),
        ):
            VerifyDestinationPathsUseCaseB3.execute(blocked_path)

        mkdir.assert_not_called()

    def test_execute_raises_path_is_not_directory_for_file(self, tmp_path):
        test_file = tmp_path / 'test_file.txt'
        test_file.write_text('content')

        with pytest.raises(PathIsNotDirectoryError) as exc_info:
            VerifyDestinationPathsUseCaseB3.execute(str(test_file))

        assert 'must be a directory' in str(exc_info.value)
        assert str(test_file) in str(exc_info.value)

    @patch('os.access')
    def test_execute_raises_path_permission_error_for_no_write_permission(
        self, mock_access, tmp_path
    ):
        test_dir = tmp_path / 'no_write'
        test_dir.mkdir()
        mock_access.return_value = False

        with pytest.raises(PathPermissionError) as exc_info:
            VerifyDestinationPathsUseCaseB3.execute(str(test_dir))

        assert 'Permission denied' in str(exc_info.value)
        assert 'No write permission' in str(exc_info.value)

    def test_execute_expands_user_home_directory(self, tmp_path):
        with patch.object(Path, 'expanduser') as mock_expand:
            mock_expand.return_value = tmp_path / 'expanded'
            (tmp_path / 'expanded').mkdir()

            result = VerifyDestinationPathsUseCaseB3.execute('~/test_output')

            mock_expand.assert_called()
        assert result == tmp_path / 'expanded'

    def test_execute_resolves_relative_paths(self, tmp_path):
        test_dir = tmp_path / 'relative'
        test_dir.mkdir()

        with patch.object(Path, 'resolve') as mock_resolve:
            mock_resolve.return_value = test_dir

            result = VerifyDestinationPathsUseCaseB3.execute('./relative/path')

            mock_resolve.assert_called()
        assert result == test_dir

    def test_execute_handles_path_with_spaces(self, tmp_path):
        test_dir = tmp_path / 'path with spaces'
        test_dir.mkdir()

        result = VerifyDestinationPathsUseCaseB3.execute(str(test_dir))

        assert result == test_dir.resolve()

    def test_execute_handles_path_with_special_characters(self, tmp_path):
        test_dir = tmp_path / 'path-with_special.chars'
        test_dir.mkdir()

        result = VerifyDestinationPathsUseCaseB3.execute(str(test_dir))

        assert result == test_dir.resolve()

    def test_execute_returns_normalized_path(self, tmp_path):
        test_dir = tmp_path / 'static_test'
        test_dir.mkdir()

        result = VerifyDestinationPathsUseCaseB3.execute(str(test_dir))

        assert result == test_dir.resolve()

    def test_execute_with_existing_writable_directory(self, tmp_path):
        test_dir = tmp_path / 'writable'
        test_dir.mkdir()
        assert os.access(str(test_dir), os.W_OK)

        result = VerifyDestinationPathsUseCaseB3.execute(str(test_dir))

        assert result == test_dir.resolve()

    @patch('pathlib.Path.mkdir')
    def test_execute_raises_permission_error_on_mkdir_failure(
        self, mock_mkdir, tmp_path
    ):
        test_dir = tmp_path / 'no_create_permission'
        mock_mkdir.side_effect = PermissionError('Cannot create directory')

        with pytest.raises(PathPermissionError):
            VerifyDestinationPathsUseCaseB3.execute(str(test_dir))

    @patch('pathlib.Path.mkdir')
    def test_execute_raises_os_error_on_mkdir_failure(
        self, mock_mkdir, tmp_path
    ):
        test_dir = tmp_path / 'os_error'
        mock_mkdir.side_effect = OSError('Generic OS error')

        with pytest.raises(OSError) as exc_info:
            VerifyDestinationPathsUseCaseB3.execute(str(test_dir))

        assert 'Failed to create directory' in str(exc_info.value)

    def test_execute_does_not_modify_existing_directory(self, tmp_path):
        test_dir = tmp_path / 'existing'
        test_dir.mkdir()
        test_file = test_dir / 'existing_file.txt'
        test_file.write_text('content')

        original_mtime = test_file.stat().st_mtime

        VerifyDestinationPathsUseCaseB3.execute(str(test_dir))

        assert test_file.exists()
        assert test_file.read_text() == 'content'
        assert test_file.stat().st_mtime == original_mtime

    def test_execute_with_absolute_path(self, tmp_path):
        test_dir = tmp_path / 'absolute'
        test_dir.mkdir()

        result = VerifyDestinationPathsUseCaseB3.execute(
            str(test_dir.absolute())
        )

        assert result == test_dir.absolute()

    def test_execute_normalizes_path(self, tmp_path):
        test_dir = tmp_path / 'normalize'
        test_dir.mkdir()

        result = VerifyDestinationPathsUseCaseB3.execute(str(test_dir))

        assert result == test_dir.resolve()
