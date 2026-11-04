import importlib
import pickle

import pytest

from globaldatafinance.macro_exceptions import (
    CorruptedZipError,
    DiskFullError,
    DownloadTimeoutError,
    EmptyDirectoryError,
    ExtractionError,
    FileWriteError,
    InvalidDestinationPathError,
    NetworkError,
    ParquetWriteError,
    PathCreationError,
    PathIsNotDirectoryError,
    PathPermissionError,
    SecurityError,
)

pytestmark = pytest.mark.unit


class TestEmptyDirectoryError:
    def test_initialization_with_path(self):
        path = '/home/user/empty_dir'
        error = EmptyDirectoryError(path)

        assert isinstance(error, Exception)
        assert path in str(error)
        assert 'Directory is empty' in str(error)

    def test_message_format(self):
        path = '/var/data/empty'
        error = EmptyDirectoryError(path)
        error_msg = str(error)

        assert f'Directory is empty: {path!r}' == error_msg

    def test_with_relative_path(self):
        path = './data/empty'
        error = EmptyDirectoryError(path)
        assert path in str(error)

    def test_with_special_characters_in_path(self):
        path = '/home/user/Programação/dados_ação'
        error = EmptyDirectoryError(path)
        assert path in str(error)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(EmptyDirectoryError) as exc_info:
            raise EmptyDirectoryError('/empty/path')

        assert 'empty/path' in str(exc_info.value)

    def test_inheritance(self):
        error = EmptyDirectoryError('/path')
        assert isinstance(error, Exception)

    def test_with_empty_string_path(self):
        error = EmptyDirectoryError('')
        assert isinstance(error, EmptyDirectoryError)

    def test_with_windows_path(self):
        path = 'C:\\Users\\Documents\\empty'
        error = EmptyDirectoryError(path)
        assert 'Users' in str(error) and 'Documents' in str(error)


class TestInvalidDestinationPathError:
    def test_initialization_with_reason(self):
        reason = 'Path does not exist'
        error = InvalidDestinationPathError(reason)

        assert isinstance(error, ValueError)
        assert reason in str(error)
        assert 'Invalid destination path' in str(error)

    def test_message_format(self):
        reason = 'Not a valid directory'
        error = InvalidDestinationPathError(reason)
        error_msg = str(error)

        assert f'Invalid destination path: {reason}' == error_msg

    def test_with_detailed_reason(self):
        reason = "No write permission for destination path '/protected'"
        error = InvalidDestinationPathError(reason)
        assert 'write permission' in str(error)

    def test_inheritance_from_value_error(self):
        error = InvalidDestinationPathError('reason')
        assert isinstance(error, ValueError)
        assert isinstance(error, Exception)

    def test_can_be_raised_and_caught_as_value_error(self):
        with pytest.raises(ValueError):
            raise InvalidDestinationPathError('Invalid path')

    def test_can_be_raised_and_caught_specifically(self):
        with pytest.raises(InvalidDestinationPathError) as exc_info:
            raise InvalidDestinationPathError('Test reason')

        assert 'Test reason' in str(exc_info.value)

    def test_with_empty_reason(self):
        error = InvalidDestinationPathError('')
        assert isinstance(error, InvalidDestinationPathError)

    def test_with_special_characters_in_reason(self):
        reason = 'Path contains invalid chars: @#$%^&*()'
        error = InvalidDestinationPathError(reason)
        assert reason in str(error)


class TestPathIsNotDirectoryError:
    def test_initialization_with_path(self):
        path = '/home/user/file.txt'
        error = PathIsNotDirectoryError(path)

        assert isinstance(error, ValueError)
        assert path in str(error)
        assert 'must be a directory' in str(error)

    def test_message_format(self):
        path = '/data/file.csv'
        error = PathIsNotDirectoryError(path)
        error_msg = str(error)

        assert (
            f"Destination path must be a directory, but '{path}' is a file."
            == error_msg
        )

    def test_message_for_missing_path(self):
        path = '/data/missing'
        error = PathIsNotDirectoryError(path, exists=False)

        assert str(error) == f"Destination path does not exist: '{path}'."

    def test_with_relative_path(self):
        path = './data/file.txt'
        error = PathIsNotDirectoryError(path)
        assert path in str(error)

    def test_inheritance_from_value_error(self):
        error = PathIsNotDirectoryError('/path')
        assert isinstance(error, ValueError)
        assert isinstance(error, Exception)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(PathIsNotDirectoryError) as exc_info:
            raise PathIsNotDirectoryError('/file.txt')

        assert 'file.txt' in str(exc_info.value)

    def test_with_windows_path(self):
        path = 'C:\\Documents\\file.docx'
        error = PathIsNotDirectoryError(path)
        assert 'Documents' in str(error) and 'file' in str(error)


class TestPathPermissionError:
    def test_initialization_with_path(self):
        path = '/root/protected'
        error = PathPermissionError(path)

        assert isinstance(error, OSError)
        assert path in str(error)
        assert 'Permission denied' in str(error)

    def test_message_format(self):
        path = '/protected/directory'
        error = PathPermissionError(path)
        error_msg = str(error)

        assert (
            f'Permission denied: No write permission for destination path '
            f"'{path}'" == error_msg
        )

    def test_with_relative_path(self):
        path = './protected/data'
        error = PathPermissionError(path)
        assert path in str(error)

    def test_inheritance_from_os_error(self):
        error = PathPermissionError('/path')
        assert isinstance(error, OSError)
        assert isinstance(error, Exception)

    def test_can_be_raised_and_caught_as_os_error(self):
        with pytest.raises(OSError):
            raise PathPermissionError('/protected')

    def test_can_be_raised_and_caught_specifically(self):
        with pytest.raises(PathPermissionError) as exc_info:
            raise PathPermissionError('/protected/path')

        assert 'protected' in str(exc_info.value)

    def test_with_special_characters_in_path(self):
        path = '/home/user/Área Restrita'
        error = PathPermissionError(path)
        assert path in str(error)


class TestNetworkError:
    def test_initialization_with_doc_name_only(self):
        doc_name = 'COTAHIST_2023.ZIP'
        error = NetworkError(doc_name)

        assert isinstance(error, Exception)
        assert doc_name in str(error)
        assert 'Network error' in str(error)

    def test_initialization_with_doc_name_and_message(self):
        doc_name = 'DATA.zip'
        message = 'Connection timeout'
        error = NetworkError(doc_name, message)

        assert doc_name in str(error)
        assert message in str(error)

    def test_message_format_without_optional_message(self):
        doc_name = 'file.zip'
        error = NetworkError(doc_name, None)
        error_msg = str(error)

        assert f"Network error while downloading '{doc_name}'. " == error_msg

    def test_message_format_with_optional_message(self):
        doc_name = 'file.zip'
        message = 'DNS resolution failed'
        error = NetworkError(doc_name, message)
        error_msg = str(error)

        assert (
            f"Network error while downloading '{doc_name}'. {message}"
            == error_msg
        )

    def test_can_be_raised_and_caught(self):
        with pytest.raises(NetworkError) as exc_info:
            raise NetworkError('data.zip', 'Connection refused')

        assert 'data.zip' in str(exc_info.value)
        assert 'Connection refused' in str(exc_info.value)

    def test_with_empty_doc_name(self):
        error = NetworkError('', 'Error message')
        assert isinstance(error, NetworkError)

    def test_with_special_characters_in_doc_name(self):
        doc_name = 'COTAHIST_A2023_ção.zip'
        error = NetworkError(doc_name, 'Failed')
        assert doc_name in str(error)

    def test_inheritance(self):
        error = NetworkError('file.zip')
        assert isinstance(error, Exception)


class TestDownloadTimeoutError:
    def test_initialization_with_doc_name_only(self):
        doc_name = 'COTAHIST_2023.ZIP'
        error = DownloadTimeoutError(doc_name)

        assert isinstance(error, Exception)
        assert doc_name in str(error)
        assert 'Timeout' in str(error)

    def test_initialization_with_doc_name_and_timeout(self):
        doc_name = 'data.zip'
        timeout = 30.5
        error = DownloadTimeoutError(doc_name, timeout)

        assert doc_name in str(error)
        assert '30.5' in str(error)

    def test_message_format_without_timeout(self):
        doc_name = 'file.zip'
        error = DownloadTimeoutError(doc_name, None)
        error_msg = str(error)

        assert f"Timeout while downloading '{doc_name}'." == error_msg

    def test_message_format_with_timeout(self):
        doc_name = 'file.zip'
        timeout = 60.0
        error = DownloadTimeoutError(doc_name, timeout)
        error_msg = str(error)

        expected = (
            f"Timeout while downloading '{doc_name}'. Timeout: {timeout}s."
        )
        assert expected == error_msg

    def test_with_integer_timeout(self):
        error = DownloadTimeoutError('file.zip', 30)
        assert '30' in str(error)

    def test_with_zero_timeout(self):
        error = DownloadTimeoutError('file.zip', 0)
        assert 'file.zip' in str(error)

    def test_with_large_timeout(self):
        error = DownloadTimeoutError('file.zip', 3600.0)
        assert '3600' in str(error)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(DownloadTimeoutError) as exc_info:
            raise DownloadTimeoutError('data.zip', 30.0)

        assert 'data.zip' in str(exc_info.value)

    def test_inheritance(self):
        error = DownloadTimeoutError('file.zip')
        assert isinstance(error, Exception)


def test_removed_custom_timeout_symbol_is_not_importable() -> None:
    """The breaking cut does not retain the old timeout import name."""
    import globaldatafinance.macro_exceptions as module

    assert not hasattr(module, 'TimeoutError')
    with pytest.raises(ImportError):
        importlib.import_module(
            'globaldatafinance.macro_exceptions.TimeoutError'
        )


class TestExtractionError:
    def test_initialization_with_path_and_message(self):
        path = '/data/file.zip'
        message = 'Invalid ZIP format'
        error = ExtractionError(path, message)

        assert isinstance(error, Exception)
        assert path in str(error)
        assert message in str(error)
        assert 'Extraction error' in str(error)

    def test_message_format(self):
        path = '/data/archive.zip'
        message = 'Corrupted data'
        error = ExtractionError(path, message)
        error_msg = str(error)

        assert f"Extraction error for '{path}': {message}" == error_msg

    def test_with_detailed_message(self):
        path = 'test-data/data.zip'
        message = 'Unable to decompress: invalid header checksum'
        error = ExtractionError(path, message)
        assert 'decompress' in str(error)
        assert 'checksum' in str(error)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(ExtractionError) as exc_info:
            raise ExtractionError('/path/to/file.zip', 'Extraction failed')

        assert 'file.zip' in str(exc_info.value)
        assert 'Extraction failed' in str(exc_info.value)

    def test_with_relative_path(self):
        path = './data/archive.zip'
        message = 'Error occurred'
        error = ExtractionError(path, message)
        assert path in str(error)

    def test_inheritance(self):
        error = ExtractionError('/path', 'message')
        assert isinstance(error, Exception)

    def test_pickle_roundtrip(self):
        error = ExtractionError('/path/to/data.zip', 'unexpected EOF')
        attr = 'loads'
        loaded = getattr(pickle, attr)(pickle.dumps(error))
        assert type(loaded) is ExtractionError
        assert str(loaded) == str(error)
        assert loaded.path == error.path
        assert loaded.message == error.message


class TestCorruptedZipError:
    def test_initialization_with_zip_path_and_message(self):
        zip_path = '/data/corrupted.zip'
        message = 'Bad CRC'
        error = CorruptedZipError(zip_path, message)

        assert isinstance(error, ExtractionError)
        assert zip_path in str(error)
        assert 'Corrupted ZIP' in str(error)
        assert message in str(error)

    def test_message_format(self):
        zip_path = '/data/bad.zip'
        message = 'Invalid header'
        error = CorruptedZipError(zip_path, message)
        error_msg = str(error)

        assert (
            f"Extraction error for '{zip_path}': Corrupted ZIP: {message}"
            == error_msg
        )

    def test_inheritance_from_extraction_error(self):
        error = CorruptedZipError('/path.zip', 'Corrupt')
        assert isinstance(error, ExtractionError)
        assert isinstance(error, Exception)

    def test_can_be_raised_and_caught_as_extraction_error(self):
        with pytest.raises(ExtractionError):
            raise CorruptedZipError('/bad.zip', 'Corrupted')

    def test_can_be_raised_and_caught_specifically(self):
        with pytest.raises(CorruptedZipError) as exc_info:
            raise CorruptedZipError('/corrupted.zip', 'Bad ZIP format')

        assert 'corrupted.zip' in str(exc_info.value)
        assert 'Bad ZIP format' in str(exc_info.value)

    def test_pickle_roundtrip(self):
        error = CorruptedZipError('/path/to/bad.zip', 'CRC check failed')
        attr = 'loads'
        loaded = getattr(pickle, attr)(pickle.dumps(error))
        assert type(loaded) is CorruptedZipError
        assert str(loaded) == str(error)
        assert loaded.path == error.path
        assert loaded.raw_message == error.raw_message

    def test_with_detailed_message(self):
        zip_path = '/data/file.zip'
        message = 'End-of-central-directory signature not found'
        error = CorruptedZipError(zip_path, message)
        assert 'signature' in str(error)


class TestDiskFullError:
    def test_initialization_with_path(self):
        path = '/mnt/data/file.parquet'
        error = DiskFullError(path)

        assert isinstance(error, OSError)
        assert path in str(error)
        assert 'Insufficient disk space' in str(error)

    def test_message_format(self):
        path = '/data/output.parquet'
        error = DiskFullError(path)
        error_msg = str(error)

        assert f"Insufficient disk space for saving '{path}'." == error_msg

    def test_with_relative_path(self):
        path = './output/data.parquet'
        error = DiskFullError(path)
        assert path in str(error)

    def test_inheritance_from_os_error(self):
        error = DiskFullError('/path')
        assert isinstance(error, OSError)
        assert isinstance(error, Exception)

    def test_can_be_raised_and_caught_as_os_error(self):
        with pytest.raises(OSError):
            raise DiskFullError('/full/disk/file.parquet')

    def test_can_be_raised_and_caught_specifically(self):
        with pytest.raises(DiskFullError) as exc_info:
            raise DiskFullError('/no/space/file.parquet')

        assert 'no/space' in str(exc_info.value)

    def test_with_windows_path(self):
        path = 'D:\\Data\\output.parquet'
        error = DiskFullError(path)
        assert 'Data' in str(error) or 'output' in str(error)


class TestSecurityError:
    def test_initialization_with_message_only(self):
        message = 'Path traversal detected'
        error = SecurityError(message)

        assert isinstance(error, Exception)
        assert message in str(error)
        assert 'Security violation' in str(error)

    def test_initialization_with_message_and_path(self):
        message = 'Access to system directory denied'
        path = '/etc/passwd'
        error = SecurityError(message, path)

        assert message in str(error)
        assert path in str(error)
        assert 'Security violation' in str(error)

    def test_message_format_without_path(self):
        message = 'Invalid operation'
        error = SecurityError(message, None)
        error_msg = str(error)

        assert f'Security violation: {message}' == error_msg

    def test_message_format_with_path(self):
        message = 'Unauthorized access'
        path = '/root/secret'
        error = SecurityError(message, path)
        error_msg = str(error)

        assert f"Security violation: {message} (path: '{path}')" == error_msg

    def test_with_path_traversal_message(self):
        message = 'Path traversal attempt detected'
        path = '../../../etc/passwd'
        error = SecurityError(message, path)
        assert 'traversal' in str(error)
        assert path in str(error)

    def test_can_be_raised_and_caught(self):
        with pytest.raises(SecurityError) as exc_info:
            raise SecurityError('Access denied', '/protected')

        assert 'Access denied' in str(exc_info.value)
        assert 'protected' in str(exc_info.value)

    def test_with_empty_message(self):
        error = SecurityError('', '/path')
        assert isinstance(error, SecurityError)

    def test_inheritance(self):
        error = SecurityError('message')
        assert isinstance(error, Exception)


class TestExceptionIntegration:
    def test_all_exceptions_inherit_from_exception(self):
        exceptions = [
            EmptyDirectoryError('/path'),
            InvalidDestinationPathError('reason'),
            PathIsNotDirectoryError('/file'),
            PathPermissionError('/protected'),
            NetworkError('doc'),
            DownloadTimeoutError('doc'),
            ExtractionError('/path', 'msg'),
            CorruptedZipError('/zip', 'msg'),
            DiskFullError('/path'),
            SecurityError('msg'),
        ]

        for exc in exceptions:
            assert isinstance(exc, Exception)

    def test_value_error_subclasses(self):
        value_errors = [
            InvalidDestinationPathError('reason'),
            PathIsNotDirectoryError('/file'),
        ]

        for exc in value_errors:
            assert isinstance(exc, ValueError)
            assert isinstance(exc, Exception)

    def test_os_error_subclasses(self):
        os_errors = [
            PathPermissionError('/path'),
            DiskFullError('/path'),
        ]

        for exc in os_errors:
            assert isinstance(exc, OSError)
            assert isinstance(exc, Exception)

    def test_extraction_error_hierarchy(self):
        base_error = ExtractionError('/path', 'msg')
        corrupted_error = CorruptedZipError('/zip', 'msg')

        assert isinstance(base_error, Exception)
        assert isinstance(corrupted_error, ExtractionError)
        assert isinstance(corrupted_error, Exception)

    def test_catch_specific_vs_generic_exception(self):
        with pytest.raises(NetworkError):
            raise NetworkError('doc', 'error')

        with pytest.raises(NetworkError):
            raise NetworkError('doc', 'error')

    def test_multiple_exception_handling_workflow(self):
        errors_caught = []

        def simulate_operation(operation_type):
            if operation_type == 'network':
                raise NetworkError('data.zip', 'Connection failed')
            elif operation_type == 'timeout':
                raise DownloadTimeoutError('data.zip', 30)
            elif operation_type == 'permission':
                raise PathPermissionError('/protected')
            elif operation_type == 'disk':
                raise DiskFullError('/full')
            elif operation_type == 'corrupt':
                raise CorruptedZipError('/bad.zip', 'Invalid')
            elif operation_type == 'security':
                raise SecurityError('Access denied', '/etc')

        operations = [
            'network',
            'timeout',
            'permission',
            'disk',
            'corrupt',
            'security',
        ]

        for op in operations:
            try:
                simulate_operation(op)
            except (
                NetworkError,
                DownloadTimeoutError,
                PathPermissionError,
                DiskFullError,
                CorruptedZipError,
                SecurityError,
            ) as e:
                errors_caught.append(type(e).__name__)

        assert len(errors_caught) == len(operations)
        assert 'NetworkError' in errors_caught
        assert 'DownloadTimeoutError' in errors_caught
        assert 'PathPermissionError' in errors_caught
        assert 'DiskFullError' in errors_caught
        assert 'CorruptedZipError' in errors_caught
        assert 'SecurityError' in errors_caught

    def test_exception_string_representations(self):
        exceptions = {
            'EmptyDirectoryError': EmptyDirectoryError('/empty'),
            'InvalidDestinationPathError': InvalidDestinationPathError(
                'invalid'
            ),
            'PathIsNotDirectoryError': PathIsNotDirectoryError('/file'),
            'PathPermissionError': PathPermissionError('/protected'),
            'NetworkError': NetworkError('doc', 'error'),
            'DownloadTimeoutError': DownloadTimeoutError('doc', 30),
            'ExtractionError': ExtractionError('/path', 'error'),
            'CorruptedZipError': CorruptedZipError('/zip', 'corrupt'),
            'DiskFullError': DiskFullError('/full'),
            'SecurityError': SecurityError('security', '/path'),
        }

        for _name, exc in exceptions.items():
            exc_str = str(exc)
            assert len(exc_str) > 0
            assert isinstance(exc_str, str)

    def test_exception_chaining(self):
        original_error = ValueError('Original error')

        with pytest.raises(ExtractionError) as exc_info:
            try:
                raise original_error
            except ValueError as e:
                raise ExtractionError('/path', 'Failed') from e

        assert exc_info.value.__cause__ is original_error

    def test_exception_with_context_manager(self):
        with pytest.raises(NetworkError) as exc_info:
            raise NetworkError('file.zip', 'Failed')

        assert 'Failed' in str(exc_info.value)


class TestNewOSErrorSubclasses:
    def test_path_creation_error(self):
        err = PathCreationError('/path', 'Permission denied')
        assert isinstance(err, OSError)
        assert 'Failed to create directory' in str(err)
        assert '/path' in str(err)

    def test_file_write_error(self):
        err = FileWriteError('/file.csv', 'Disk error')
        assert isinstance(err, OSError)
        assert 'Failed to write chunk' in str(err)

    def test_parquet_write_error(self):
        err = ParquetWriteError('/out.parquet', 'Corrupt schema')
        assert isinstance(err, OSError)
        assert 'Failed to write Parquet file' in str(err)
