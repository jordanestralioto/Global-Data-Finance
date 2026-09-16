"""Centralized logging configuration for Global-Data-Finance library.

This module provides a unified, production-ready logging system with lazy
initialization, console/file handlers, configurable log levels, execution
timing utilities, and structured context formatting.

"""

import logging
import os
import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Any, Literal

from pydantic import AliasChoices, Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .logging_redaction import format_structured_message

# Log formats

DEFAULT_FORMAT = '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
DETAILED_FORMAT = (
    '%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | '
    '%(funcName)s | %(message)s'
)
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'
_LOGGING_ENV_PREFIX = 'DATAFIN_LOG_'
_KNOWN_LOGGING_ENV_NAMES = frozenset(
    {
        'DATAFIN_LOG_LEVEL',
        'DATAFIN_LOG_FORMAT',
        'DATAFIN_LOG_FILE',
        'DATAFIN_LOG_LOG_FILE',
        'DATAFIN_LOG_DETAILED_FORMAT',
    }
)


class LoggingSettings(BaseSettings):
    """Global logging configuration with environment variable support."""

    def __init__(self, **data: Any) -> None:
        """Reject unknown logging environment variables before resolution."""
        unknown_environment = tuple(
            sorted(
                name
                for name in os.environ
                if name.upper().startswith(_LOGGING_ENV_PREFIX)
                and name.upper() not in _KNOWN_LOGGING_ENV_NAMES
            )
        )
        if unknown_environment:
            data = {
                **data,
                '__unknown_logging_environment__': ', '.join(
                    unknown_environment
                ),
            }
        super().__init__(**data)

    level: Literal['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'] = Field(
        default='INFO', description='Global logging level'
    )
    format: str = Field(
        default=DEFAULT_FORMAT, description='Log message format'
    )
    log_file: str | None = Field(
        default=None,
        description='Path to log file (None = console only)',
        validation_alias=AliasChoices(
            'log_file', 'DATAFIN_LOG_FILE', 'DATAFIN_LOG_LOG_FILE'
        ),
    )
    detailed_format: bool = Field(
        default=False, description='Include line numbers and function names'
    )

    model_config = SettingsConfigDict(
        env_prefix='DATAFIN_LOG_',
        case_sensitive=False,
        extra='forbid',
        frozen=True,
    )

    @field_validator('level', mode='before')
    @classmethod
    def validate_level(cls, v: Any) -> Any:
        """Normalize logging level to uppercase."""
        if v is None:
            return v
        if isinstance(v, str):
            return v.upper()
        return v

    @field_validator('log_file', mode='before')
    @classmethod
    def validate_log_file(cls, v: Any) -> Any:
        """Convert Path instances to string."""
        if isinstance(v, Path):
            return str(v)
        return v


_LIBRARY_LOGGER_NAME = 'globaldatafinance'
_MANAGED_HANDLER_ATTR = '_gdf_managed'
_logging_lock = threading.Lock()
_package_logger = logging.getLogger(_LIBRARY_LOGGER_NAME)
if not any(
    isinstance(handler, logging.NullHandler)
    for handler in _package_logger.handlers
):
    _package_logger.addHandler(logging.NullHandler())
_package_logger.propagate = False


class ContextFilter(logging.Filter):
    """Add contextual information to log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        """Add custom fields to log record if not present."""
        if not hasattr(record, 'extra_data'):
            record.extra_data = {}
        return True


class StructuredFormatter(logging.Formatter):
    """Custom formatter that handles extra data from log calls."""

    def format(self, record: logging.LogRecord) -> str:
        """Format log record with extra data if present."""
        return format_structured_message(super().format(record), record)


def setup_logging(
    settings: LoggingSettings | None = None,
) -> LoggingSettings:
    """Setup logging for Global-Data-Finance library.

    Configures only loggers under the ``globaldatafinance`` hierarchy, leaving
    the application-owned root logger and external handlers undisturbed.
    Can be called multiple times to atomically reconfigure library logging;
    only library-managed handlers are replaced, while externally attached
    handlers on the package logger are preserved.

    Args:
        settings: Immutable LoggingSettings snapshot. If None, instantiates
            a fresh snapshot from environment variables or defaults.

    Returns:
        The resolved immutable LoggingSettings snapshot.

    Example:
        >>> from globaldatafinance.core.logging_config import (
        ...     LoggingSettings, setup_logging
        ... )
        >>> setup_logging(LoggingSettings(level="INFO"))
        >>> setup_logging(
        ...     LoggingSettings(level="DEBUG", log_file="/tmp/datafin.log")
        ... )
    """
    if settings is None:
        settings = LoggingSettings()

    candidates = _build_managed_handlers(settings)
    with _logging_lock:
        package_logger = logging.getLogger(_LIBRARY_LOGGER_NAME)
        previous_handlers = list(package_logger.handlers)
        previous_level = package_logger.level
        previous_propagate = package_logger.propagate
        previous_managed = [
            handler
            for handler in previous_handlers
            if getattr(handler, _MANAGED_HANDLER_ATTR, False)
        ]
        try:
            for handler in previous_managed:
                package_logger.removeHandler(handler)
            for handler in candidates:
                package_logger.addHandler(handler)
            package_logger.setLevel(getattr(logging, settings.level))
            package_logger.propagate = False
        except Exception:
            package_logger.handlers[:] = previous_handlers
            package_logger.setLevel(previous_level)
            package_logger.propagate = previous_propagate
            _close_handlers(candidates)
            raise

        _close_handlers(previous_managed)

    return settings


def _build_managed_handlers(
    settings: LoggingSettings,
) -> list[logging.Handler]:
    """Build fully configured handlers without touching the package logger."""
    level = getattr(logging, settings.level)
    log_format = (
        DETAILED_FORMAT if settings.detailed_format else settings.format
    )
    candidates: list[logging.Handler] = []
    try:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(level)
        console_handler.setFormatter(
            StructuredFormatter(log_format, datefmt=DATE_FORMAT)
        )
        console_handler.addFilter(ContextFilter())
        setattr(console_handler, _MANAGED_HANDLER_ATTR, True)
        candidates.append(console_handler)

        if settings.log_file:
            log_file_path = Path(settings.log_file)
            from .utils.path_safety import assert_path_not_sensitive

            assert_path_not_sensitive(
                log_file_path.expanduser().resolve(), settings.log_file
            )
            log_file_path.parent.mkdir(parents=True, exist_ok=True)
            file_handler = logging.FileHandler(log_file_path, encoding='utf-8')
            file_handler.setLevel(level)
            file_handler.setFormatter(
                StructuredFormatter(log_format, datefmt=DATE_FORMAT)
            )
            file_handler.addFilter(ContextFilter())
            setattr(file_handler, _MANAGED_HANDLER_ATTR, True)
            candidates.append(file_handler)
    except Exception:
        _close_handlers(candidates)
        raise
    return candidates


def _close_handlers(handlers: list[logging.Handler]) -> None:
    """Close candidate handlers while retaining the preparation failure."""
    for handler in handlers:
        with suppress(Exception):
            handler.close()


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance for a specific module.

    This is the standard way to get a logger in any module.
    Always use __name__ as the logger name for proper hierarchical naming.
    Note that ``setup_logging()`` configures only the ``globaldatafinance.*``
    logger hierarchy, not arbitrary application loggers outside this namespace.

    Args:
        name: Logger name (typically __name__ from calling module)

    Returns:
        Configured logger instance

    Example:
        >>> from globaldatafinance.core.logging_config import get_logger
        >>> logger.info("Processing file", extra={"file_target": "data.csv"})
        >>> logger.debug("Record count", extra={"count": 1000})
    """
    return logging.getLogger(name)


@contextmanager
def log_execution_time(
    logger: logging.Logger, operation: str, **context: Any
) -> Iterator[None]:
    """Context manager to log execution time of operations.

    Logs the start of the operation, measures execution time, and logs
    completion with elapsed time. If an exception occurs, logs the error
    with execution time and re-raises.

    Args:
        logger: Logger instance to use
        operation: Description of the operation being timed
        **context: Additional context to include in logs

    Yields:
        None

    Example:
        >>> from globaldatafinance.core.logging_config import (
        ...     log_execution_time, get_logger
        ... )
        >>>
        >>> logger = get_logger(__name__)
        >>> with log_execution_time(
        ...     logger, "Parse ZIP file", file_target="data.zip"
        ... ):
        ...     parse_file()
        ...
        >>> # Output:
        >>> # Starting: Parse ZIP file | operation=Parse ZIP file |
        >>> # file_target=data.zip
        >>> # Completed: Parse ZIP file | operation=Parse ZIP file |
        >>> # elapsed_seconds=2.45 | file_target=data.zip
    """
    start_time = time.perf_counter()
    logger.info(
        f'Starting: {operation}',
        extra={'operation': operation, **context},
    )

    try:
        yield
    except Exception as e:
        elapsed = time.perf_counter() - start_time
        logger.error(
            f'Failed: {operation}',
            extra={
                'operation': operation,
                'elapsed_seconds': f'{elapsed:.2f}',
                'error': str(e),
                **context,
            },
            exc_info=True,
        )
        raise
    else:
        elapsed = time.perf_counter() - start_time
        logger.info(
            f'Completed: {operation}',
            extra={
                'operation': operation,
                'elapsed_seconds': f'{elapsed:.2f}',
                **context,
            },
        )


def log_with_context(
    logger: logging.Logger,
    level: str,
    message: str,
    **context: Any,
) -> None:
    """Log a message with structured context data.

    Convenience function for logging with extra context fields.

    Args:
        logger: Logger instance
        level: Log level (debug, info, warning, error, critical)
        message: Log message
        **context: Additional context fields

    Example:
        >>> from globaldatafinance.core.logging_config import (
        ...     log_with_context, get_logger
        ... )
        >>>
        >>> logger = get_logger(__name__)
        >>> log_with_context(
        ...     logger,
        ...     "info",
        ...     "File processed successfully",
        ...     file_target="data.csv",
        ...     records=1000,
        ...     elapsed_ms=250
        ... )
    """
    log_method = getattr(logger, level.lower())
    log_method(message, extra=context)


def is_logging_configured() -> bool:
    """Check if library logging has been configured with managed handlers.

    Returns:
        True if library-managed handlers are attached to the
        ``globaldatafinance`` logger hierarchy, False otherwise.

    Example:
        >>> from globaldatafinance.core.logging_config import (
        ...     LoggingSettings, is_logging_configured, setup_logging
        ... )
        >>> if not is_logging_configured():
        ...     setup_logging(LoggingSettings(level="INFO"))
    """
    package_logger = logging.getLogger(_LIBRARY_LOGGER_NAME)
    return any(
        getattr(h, _MANAGED_HANDLER_ATTR, False)
        for h in package_logger.handlers
    )
