"""Dispatch isolated real-validation cases and preserve their evidence."""

from __future__ import annotations

import contextlib
import time
import traceback
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa

from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    EmptyAssetListError,
    InvalidAssetsName,
    InvalidOutputFilename,
    InvalidProcessingMode,
)
from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    InvalidFirstYear as InvalidB3FirstYear,
)
from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    InvalidLastYear as InvalidB3LastYear,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.errors import (
    CvmError,
)
from globaldatafinance.macro_exceptions import (
    ExtractionError,
    NetworkError,
    SecurityError,
)
from globaldatafinance.macro_exceptions import (
    TimeoutError as MacroTimeoutError,
)

from .real_validation_b3 import execute_cotahist_case
from .real_validation_cvm import execute_cvm_case
from .real_validation_report import REPORT_SCHEMA_VERSION
from .real_validation_types import (
    ExternalFailure,
    NotPublished,
    ValidationCase,
)
from .real_validation_utils import temporary_paths

_CASE_FAILURES = (
    ArithmeticError,
    AssertionError,
    AttributeError,
    CvmError,
    EmptyAssetListError,
    EOFError,
    ExtractionError,
    ImportError,
    IndexError,
    InvalidAssetsName,
    InvalidB3FirstYear,
    InvalidB3LastYear,
    InvalidOutputFilename,
    InvalidProcessingMode,
    KeyError,
    LookupError,
    MemoryError,
    NetworkError,
    OSError,
    OverflowError,
    RuntimeError,
    SecurityError,
    SyntaxError,
    TypeError,
    UnicodeError,
    ValueError,
    MacroTimeoutError,
    httpx.HTTPError,
    pa.ArrowException,
)


def execute_case(
    case: ValidationCase,
    *,
    timeout: float,
    workspace: Path,
    log_path: Path,
) -> dict[str, Any]:
    """Execute one case and return a complete, classified evidence record."""
    workspace.mkdir(parents=True, exist_ok=True)
    start_time = time.perf_counter()
    result = _base_result(case)
    try:
        with (
            log_path.open('w', encoding='utf-8') as log_handle,
            contextlib.redirect_stdout(log_handle),
            contextlib.redirect_stderr(log_handle),
        ):
            if case.source == 'cotahist':
                details = execute_cotahist_case(case, workspace)
            else:
                details = execute_cvm_case(case, workspace, timeout)
            result.update(details)
    except NotPublished as error:
        result.update({'status': 'not_published', 'message': str(error)})
    except ExternalFailure as error:
        result.update({'status': 'external_failure', 'message': str(error)})
    except _CASE_FAILURES as error:
        with log_path.open('a', encoding='utf-8') as log_handle:
            traceback.print_exc(file=log_handle)
        result.update(
            {
                'status': 'failed',
                'message': f'{type(error).__name__}: {error}',
            }
        )
    finally:
        result['durationSeconds'] = round(
            max(time.perf_counter() - start_time, 0.0), 6
        )
        result['temporaryFiles'] = temporary_paths(workspace)
    return result


def _base_result(case: ValidationCase) -> dict[str, Any]:
    return {
        'schemaVersion': REPORT_SCHEMA_VERSION,
        'caseId': case.case_id,
        'source': case.source,
        'document': case.document,
        'year': case.year,
        'inputPath': case.input_path,
        'inputSizeBytes': case.input_size_bytes,
        'inputSha256': case.input_sha256,
        'command': case.command(),
        'published': None,
        'publicResult': None,
        'artifactCount': 0,
        'artifacts': [],
        'recordCount': 0,
        'schema': {},
        'temporaryFiles': [],
        'temporaryFilesAfterCleanup': [],
        'status': 'failed',
        'message': 'case did not produce a result',
        'durationSeconds': 0.0,
    }
