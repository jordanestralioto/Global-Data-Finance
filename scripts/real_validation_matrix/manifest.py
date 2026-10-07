"""Encode and validate resumable real-validation manifests."""

from __future__ import annotations

from typing import Any, Literal, cast

from ..real_validation_report import REPORT_SCHEMA_VERSION, ReportFormatError
from ..real_validation_types import ValidationCase, ValidationInputSnapshot
from .cases import Source, normalized_path


def manifest_for(
    cases: list[ValidationCase],
    *,
    source: Source,
    initial_year: int | None,
    last_year: int | None,
    document: str | None,
    cotahist_path: str | None,
    cvm_output: str | None,
    timeout: float,
) -> dict[str, Any]:
    """Create the deterministic manifest consumed by ``--resume``."""
    return {
        'schemaVersion': REPORT_SCHEMA_VERSION,
        'campaign': {
            'source': source,
            'cotahistPath': normalized_path(cotahist_path),
            'cvmOutput': normalized_path(cvm_output),
            'initialYear': initial_year,
            'lastYear': last_year,
            'document': document,
            'timeoutSeconds': timeout,
            'cotahistFrozenBaseline': any(
                case.frozen_baseline for case in cases
            ),
        },
        'cases': [case.to_manifest_dict() for case in cases],
    }


def cases_from_manifest(manifest: dict[str, Any]) -> list[ValidationCase]:
    """Decode and validate the sorted case list from a prior run."""
    raw_cases = manifest.get('cases')
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ReportFormatError('manifest cases must be a non-empty list')
    cases = [_case_from_dict(item) for item in raw_cases]
    ids = [case.case_id for case in cases]
    if ids != sorted(ids) or len(ids) != len(set(ids)):
        raise ReportFormatError('manifest cases must be unique and sorted')
    return cases


def _case_from_dict(value: object) -> ValidationCase:
    if not isinstance(value, dict):
        raise ReportFormatError('manifest case must be an object')
    source = _manifest_choice(value, 'source', {'cotahist', 'cvm'})
    mode = _manifest_choice(
        value, 'mode', {'fast', 'parity', 'multi_parity', 'cvm'}
    )
    if (source == 'cotahist') != (mode != 'cvm'):
        raise ReportFormatError(
            'manifest source and processing mode are inconsistent'
        )
    case_id = _manifest_string(value, 'caseId')
    year = _manifest_integer(value, 'year')
    input_path = _manifest_string(value, 'inputPath')
    output_root = _manifest_string(value, 'outputRoot')
    document = _manifest_optional_string(value, 'document')
    url = _manifest_optional_string(value, 'url')
    size = _manifest_optional_integer(value, 'inputSizeBytes')
    file_hash = _manifest_optional_string(value, 'inputSha256')
    initial_year = _manifest_optional_integer(value, 'initialYear')
    last_year = _manifest_optional_integer(value, 'lastYear')
    input_files = _manifest_input_files(value.get('inputFiles'))
    frozen_baseline = value.get('frozenBaseline', False)
    if not isinstance(frozen_baseline, bool):
        raise ReportFormatError('manifest frozenBaseline must be a boolean')
    if frozen_baseline and (source != 'cotahist' or mode != 'multi_parity'):
        raise ReportFormatError(
            'historical baseline requires a multi-year COTAHIST parity case'
        )
    return ValidationCase(
        case_id=case_id,
        source=cast(Literal['cotahist', 'cvm'], source),
        year=year,
        input_path=input_path,
        output_root=output_root,
        document=document,
        mode=cast(Literal['fast', 'parity', 'multi_parity', 'cvm'], mode),
        url=url,
        input_size_bytes=size,
        input_sha256=file_hash,
        initial_year=initial_year,
        last_year=last_year,
        input_files=input_files,
        frozen_baseline=frozen_baseline,
    )


def _manifest_input_files(
    candidate: object,
) -> tuple[ValidationInputSnapshot, ...]:
    if not isinstance(candidate, list):
        raise ReportFormatError('manifest inputFiles must be a list')
    snapshots: list[ValidationInputSnapshot] = []
    for item in candidate:
        if not isinstance(item, dict):
            raise ReportFormatError(
                'manifest inputFiles entries must be objects'
            )
        path = item.get('path')
        size = item.get('sizeBytes')
        file_hash = item.get('sha256')
        if not isinstance(path, str):
            raise ReportFormatError(
                'manifest inputFiles path must be a string'
            )
        if not isinstance(size, int) or isinstance(size, bool) or size < 0:
            raise ReportFormatError(
                'manifest inputFiles sizeBytes must be a non-negative integer'
            )
        if (
            not isinstance(file_hash, str)
            or len(file_hash) != 64
            or any(
                character not in '0123456789abcdef' for character in file_hash
            )
        ):
            raise ReportFormatError('manifest inputFiles sha256 is invalid')
        snapshots.append(ValidationInputSnapshot(path, size, file_hash))
    if snapshots != sorted(snapshots, key=lambda item: item.path):
        raise ReportFormatError('manifest inputFiles must be path-sorted')
    return tuple(snapshots)


def _manifest_choice(
    value: dict[object, object], key: str, choices: set[str]
) -> str:
    candidate = value.get(key)
    if not isinstance(candidate, str) or candidate not in choices:
        options = ', '.join(sorted(choices))
        raise ReportFormatError(f'manifest {key} must be one of: {options}')
    return candidate


def _manifest_string(value: dict[object, object], key: str) -> str:
    candidate = value.get(key)
    if not isinstance(candidate, str):
        raise ReportFormatError(f'manifest {key} must be a string')
    return candidate


def _manifest_optional_string(
    value: dict[object, object], key: str
) -> str | None:
    candidate = value.get(key)
    if candidate is not None and not isinstance(candidate, str):
        raise ReportFormatError(f'manifest {key} must be a string or null')
    return candidate


def _manifest_integer(value: dict[object, object], key: str) -> int:
    candidate = value.get(key)
    if not isinstance(candidate, int) or isinstance(candidate, bool):
        raise ReportFormatError(f'manifest {key} must be an integer')
    return candidate


def _manifest_optional_integer(
    value: dict[object, object], key: str
) -> int | None:
    candidate = value.get(key)
    if candidate is not None and (
        not isinstance(candidate, int) or isinstance(candidate, bool)
    ):
        raise ReportFormatError(f'manifest {key} must be an integer or null')
    return candidate
