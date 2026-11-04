import io
import logging
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

import globaldatafinance.core.logging_config as logging_config_module
from globaldatafinance.core.logging_config import (
    LoggingSettings,
    StructuredFormatter,
    get_logger,
    is_logging_configured,
    log_execution_time,
    log_with_context,
    setup_logging,
)
from globaldatafinance.core.utils.files import remove_file
from globaldatafinance.macro_exceptions import SecurityError

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def restore_logging_state():
    """Restore package and root handlers after each test."""
    package_logger = logging.getLogger('globaldatafinance')
    orig_pkg_handlers = list(package_logger.handlers)
    orig_pkg_level = package_logger.level
    orig_pkg_propagate = package_logger.propagate

    root_logger = logging.getLogger()
    orig_root_handlers = list(root_logger.handlers)
    orig_root_level = root_logger.level

    yield

    for handler in list(package_logger.handlers):
        if handler not in orig_pkg_handlers:
            package_logger.removeHandler(handler)
            handler.close()
    package_logger.handlers[:] = orig_pkg_handlers
    package_logger.setLevel(orig_pkg_level)
    package_logger.propagate = orig_pkg_propagate

    for handler in list(root_logger.handlers):
        if handler not in orig_root_handlers:
            root_logger.removeHandler(handler)
            handler.close()
    root_logger.handlers[:] = orig_root_handlers
    root_logger.setLevel(orig_root_level)


class TestLoggingConfiguration:
    def test_library_logger_is_quiet_before_explicit_setup(self):
        package_logger = logging.getLogger('globaldatafinance')
        root_logger = logging.getLogger()
        root_buffer = io.StringIO()
        root_handler = logging.StreamHandler(root_buffer)
        root_logger.addHandler(root_handler)

        for handler in list(package_logger.handlers):
            package_logger.removeHandler(handler)
        package_logger.addHandler(logging.NullHandler())
        package_logger.setLevel(logging.NOTSET)
        package_logger.propagate = False

        logger = get_logger('globaldatafinance.before_setup')
        logger.info('info must remain quiet')
        logger.warning('warning must remain quiet')

        assert not is_logging_configured()
        assert root_buffer.getvalue() == ''

    def test_get_logger_returns_logger(self):
        logger = get_logger('test_module')

        assert isinstance(logger, logging.Logger)
        assert logger.name == 'test_module'

    def test_setup_logging_creates_handlers_on_package_logger(self):
        root_logger = logging.getLogger()
        root_handlers_count = len(root_logger.handlers)

        snapshot = setup_logging(LoggingSettings(level='INFO'))
        pkg_logger = logging.getLogger('globaldatafinance')

        assert len(pkg_logger.handlers) > 0
        assert pkg_logger.level == logging.INFO
        assert snapshot.level == 'INFO'
        assert len(root_logger.handlers) == root_handlers_count

    def test_setup_logging_with_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / 'test.log'

            setup_logging(LoggingSettings(level='DEBUG', log_file=log_file))
            logger = get_logger('globaldatafinance.test_module')

            logger.debug('Debug message')
            logger.info('Info message')

            assert log_file.exists()
            content = log_file.read_text()
            assert 'Debug message' in content
            assert 'Info message' in content

    def test_log_with_context_emits_context_and_level(self, caplog):
        logger = get_logger('test_module')

        with caplog.at_level(logging.INFO, logger='test_module'):
            log_with_context(
                logger,
                'warning',
                'Processing file',
                file_path='data.csv',
                records=1000,
            )

        assert len(caplog.records) == 1
        record = caplog.records[0]
        assert record.levelno == logging.WARNING
        assert record.message == 'Processing file'
        assert record.file_path == 'data.csv'
        assert record.records == 1000

    def test_structured_formatter_renders_extra_data_and_safe_context(self):
        formatter = StructuredFormatter('%(message)s')
        record = logging.LogRecord(
            name='test_module',
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg='Processing file',
            args=(),
            exc_info=None,
        )
        record.extra_data = {'phase': 'download'}
        record.file_target = 'COTAHIST_A2023.ZIP'

        formatted = formatter.format(record)

        assert formatted.startswith('Processing file')
        assert 'phase=download' in formatted
        assert 'file_target=COTAHIST_A2023.ZIP' in formatted

    def test_structured_formatter_redacts_sensitive_context_and_urls(self):
        formatter = StructuredFormatter('%(message)s')
        record = logging.LogRecord(
            name='test_module',
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg='Request https://example.com/file?access_token=url-secret',
            args=(),
            exc_info=None,
        )
        record.extra_data = {
            'Authorization': 'Bearer header-secret',
            'headers': {'Cookie': 'cookie-secret', 'Accept': 'text/plain'},
            'phase': 'download',
        }

        formatted = formatter.format(record)

        assert 'url-secret' not in formatted
        assert 'header-secret' not in formatted
        assert 'cookie-secret' not in formatted
        assert formatted.count('[REDACTED]') == 3
        assert 'phase=download' in formatted

    def test_filename_remains_reserved_by_standard_logging(self):
        logger = get_logger('test_reserved_logrecord_attribute')
        original_level = logger.level
        logger.setLevel(logging.INFO)

        try:
            with pytest.raises(KeyError, match='filename'):
                logger.info('Invalid context', extra={'filename': 'data.csv'})
        finally:
            logger.setLevel(original_level)

    @patch(
        'globaldatafinance.core.logging_config.time.perf_counter',
        side_effect=[10.0, 12.5],
    )
    def test_log_execution_time_success_emits_timing(
        self, mock_perf_counter, caplog
    ):
        logger = get_logger('test_module')

        with (
            caplog.at_level(logging.INFO, logger='test_module'),
            log_execution_time(logger, 'Test operation', file_path='data.csv'),
        ):
            pass

        assert mock_perf_counter.call_count == 2
        assert [record.message for record in caplog.records] == [
            'Starting: Test operation',
            'Completed: Test operation',
        ]
        completed = caplog.records[-1]
        assert completed.levelno == logging.INFO
        assert completed.operation == 'Test operation'
        assert completed.elapsed_seconds == '2.50'
        assert completed.file_path == 'data.csv'

    @patch(
        'globaldatafinance.core.logging_config.time.perf_counter',
        side_effect=[10.0, 11.25],
    )
    def test_log_execution_time_failure_emits_error_and_reraises(
        self, _mock_perf_counter, caplog
    ):
        logger = get_logger('test_module')

        with (
            caplog.at_level(logging.INFO, logger='test_module'),
            pytest.raises(ValueError, match='Test error'),
            log_execution_time(logger, 'Failing operation'),
        ):
            raise ValueError('Test error')

        failed = caplog.records[-1]
        assert failed.levelno == logging.ERROR
        assert failed.message == 'Failed: Failing operation'
        assert failed.operation == 'Failing operation'
        assert failed.elapsed_seconds == '1.25'
        assert failed.error == 'Test error'

    def test_different_log_levels_emit_exact_levels(self, caplog):
        logger = get_logger('test_module')

        with caplog.at_level(logging.DEBUG, logger='test_module'):
            logger.debug('Debug message')
            logger.info('Info message')
            logger.warning('Warning message')
            logger.error('Error message')

        assert [record.levelno for record in caplog.records] == [
            logging.DEBUG,
            logging.INFO,
            logging.WARNING,
            logging.ERROR,
        ]
        assert [record.message for record in caplog.records] == [
            'Debug message',
            'Info message',
            'Warning message',
            'Error message',
        ]

    def test_log_execution_time_success_body_is_observed(self, caplog):
        logger = get_logger('test_module')

        with (
            caplog.at_level(logging.INFO, logger='test_module'),
            log_execution_time(logger, 'Observed operation'),
        ):
            logger.info('operation body')

        assert any(
            record.message == 'operation body' for record in caplog.records
        )

    def test_setup_logging_with_detailed_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / 'detailed.log'

            setup_logging(
                LoggingSettings(
                    level='DEBUG',
                    log_file=log_file,
                    detailed_format=True,
                )
            )
            logger = get_logger('globaldatafinance.test_module')

            logger.info('Test with detailed format')

            content = log_file.read_text()
            assert 'test_setup_logging_with_detailed_format' in content

    def test_setup_logging_rejects_protected_log_destination(self):
        with pytest.raises(SecurityError):
            setup_logging(LoggingSettings(log_file='/var/log/datafinance.log'))

    def test_remove_file_removes_existing_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / 'to_remove.txt'
            file_path.write_text('test')
            assert file_path.exists()
            remove_file(str(file_path))
            assert not file_path.exists()

    def test_remove_file_nonexistent_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = Path(tmpdir) / 'does_not_exist.txt'
            remove_file(str(file_path))
            assert not file_path.exists()

    def test_remove_file_logs_permission_failure_without_raising(
        self, tmp_path, monkeypatch, caplog
    ):
        file_path = tmp_path / 'protected.txt'
        file_path.write_text('content')

        def deny_unlink(_path: Path) -> None:
            raise PermissionError('permission denied')

        monkeypatch.setattr(Path, 'unlink', deny_unlink)

        with caplog.at_level(logging.WARNING):
            remove_file(str(file_path))

        assert file_path.exists()
        assert any(
            record.exc_info is not None
            and 'Failed to remove file' in record.message
            for record in caplog.records
        )

    def test_remove_file_accepts_path_instance_and_logs_debug(
        self, tmp_path, caplog
    ):
        file_path = tmp_path / 'direct_path.txt'
        file_path.write_text('content')
        assert file_path.exists()

        with caplog.at_level(logging.DEBUG):
            remove_file(file_path)

        assert not file_path.exists()
        assert any(
            'Removed file:' in record.message for record in caplog.records
        )

    def test_setup_logging_marks_configuration_and_applies_level(self):
        pkg_logger = logging.getLogger('globaldatafinance')
        for h in list(pkg_logger.handlers):
            pkg_logger.removeHandler(h)

        assert is_logging_configured() is False

        snapshot = setup_logging(LoggingSettings(level='WARNING'))

        managed_handlers = [
            handler
            for handler in pkg_logger.handlers
            if getattr(handler, '_gdf_managed', False)
        ]
        assert is_logging_configured() is True
        assert snapshot.level == 'WARNING'
        assert pkg_logger.level == logging.WARNING
        assert len(managed_handlers) == 1
        assert managed_handlers[0].level == logging.WARNING

    def test_setup_logging_preserves_external_handlers_and_replaces_managed(
        self,
    ):
        pkg_logger = logging.getLogger('globaldatafinance')
        for h in list(pkg_logger.handlers):
            pkg_logger.removeHandler(h)

        external_handler = logging.StreamHandler()
        external_handler.setLevel(logging.ERROR)
        pkg_logger.addHandler(external_handler)

        setup_logging(LoggingSettings(level='INFO'))
        assert external_handler in pkg_logger.handlers
        assert is_logging_configured() is True

        setup_logging(LoggingSettings(level='DEBUG'))
        assert external_handler in pkg_logger.handlers
        managed_handlers = [
            h for h in pkg_logger.handlers if getattr(h, '_gdf_managed', False)
        ]
        assert len(managed_handlers) == 1
        assert managed_handlers[0].level == logging.DEBUG

    def test_setup_logging_restores_state_when_handler_preparation_fails(
        self, tmp_path, monkeypatch
    ):
        package_logger = logging.getLogger('globaldatafinance')
        external_handler = logging.StreamHandler(io.StringIO())
        old_managed = logging.StreamHandler(io.StringIO())
        old_managed.__dict__['_gdf_managed'] = True
        package_logger.addHandler(external_handler)
        package_logger.addHandler(old_managed)
        package_logger.setLevel(logging.ERROR)
        package_logger.propagate = True
        previous_handlers = list(package_logger.handlers)

        def fail_mkdir(*_args, **_kwargs):
            raise OSError('cannot create log directory')

        monkeypatch.setattr(logging_config_module.Path, 'mkdir', fail_mkdir)
        with (
            patch.object(
                old_managed, 'close', wraps=old_managed.close
            ) as close,
            pytest.raises(OSError, match='cannot create log directory'),
        ):
            setup_logging(
                LoggingSettings(log_file=tmp_path / 'logs' / 'data.log')
            )

        assert package_logger.handlers == previous_handlers
        assert package_logger.level == logging.ERROR
        assert package_logger.propagate is True
        close.assert_not_called()

    def test_setup_logging_restores_state_when_handler_swap_fails(
        self, monkeypatch
    ):
        package_logger = logging.getLogger('globaldatafinance')
        external_handler = logging.StreamHandler(io.StringIO())
        old_managed = logging.StreamHandler(io.StringIO())
        old_managed.__dict__['_gdf_managed'] = True
        package_logger.addHandler(external_handler)
        package_logger.addHandler(old_managed)
        package_logger.setLevel(logging.ERROR)
        package_logger.propagate = True
        previous_handlers = list(package_logger.handlers)
        original_add_handler = package_logger.addHandler

        def fail_managed_add(handler):
            if getattr(handler, '_gdf_managed', False):
                raise OSError('cannot install managed handler')
            original_add_handler(handler)

        monkeypatch.setattr(package_logger, 'addHandler', fail_managed_add)
        with (
            patch.object(
                old_managed, 'close', wraps=old_managed.close
            ) as close,
            pytest.raises(OSError, match='cannot install managed handler'),
        ):
            setup_logging(LoggingSettings())

        assert package_logger.handlers == previous_handlers
        assert package_logger.level == logging.ERROR
        assert package_logger.propagate is True
        close.assert_not_called()

    def test_logging_settings_immutability_and_field_absence(self):
        settings = LoggingSettings()
        with pytest.raises(ValidationError):
            settings.level = 'DEBUG'

        assert not hasattr(settings, 'structured')
        with pytest.raises(ValidationError):
            LoggingSettings(structured=True)

    @pytest.mark.parametrize(
        'environment_name',
        ['DATAFIN_LOG_FILE', 'DATAFIN_LOG_LOG_FILE'],
    )
    def test_logging_settings_accepts_documented_and_derived_file_env_names(
        self, monkeypatch, tmp_path, environment_name
    ):
        monkeypatch.delenv('DATAFIN_LOG_FILE', raising=False)
        monkeypatch.delenv('DATAFIN_LOG_LOG_FILE', raising=False)
        log_file = tmp_path / 'environment.log'
        monkeypatch.setenv(environment_name, str(log_file))

        assert LoggingSettings().log_file == str(log_file)

    def test_logging_settings_rejects_unknown_environment_fields(
        self, monkeypatch
    ):
        monkeypatch.setenv('DATAFIN_LOG_STRUCTURED', 'true')

        with pytest.raises(
            ValidationError, match='unknown_logging_environment'
        ):
            LoggingSettings()

    def test_get_logging_settings_is_absent(self):
        assert not hasattr(logging_config_module, 'get_logging_settings')

    def test_setup_logging_disables_propagation_to_root(self):
        root_logger = logging.getLogger()
        root_buffer = io.StringIO()
        root_handler = logging.StreamHandler(root_buffer)
        root_handler.setLevel(logging.DEBUG)
        root_logger.addHandler(root_handler)

        with tempfile.TemporaryDirectory() as tmpdir:
            log_file = Path(tmpdir) / 'package.log'
            setup_logging(LoggingSettings(level='INFO', log_file=log_file))

            pkg_logger = logging.getLogger('globaldatafinance')
            assert pkg_logger.propagate is False

            child_logger = get_logger('globaldatafinance.test_isolation')
            child_logger.info('Unique library event message')

            # Library managed file handler received the event
            assert log_file.exists()
            assert 'Unique library event message' in log_file.read_text(
                encoding='utf-8'
            )

            # Consuming application root logger received no event
            assert 'Unique library event message' not in root_buffer.getvalue()
