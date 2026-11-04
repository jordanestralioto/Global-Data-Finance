"""Validate persisted inputs before resuming a real-validation campaign."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from globaldatafinance.macro_exceptions import SecurityError

from .real_validation_matrix.cases import canonical_cvm_case
from .real_validation_matrix.manifest import cases_from_manifest
from .real_validation_report import (
    REPORT_SCHEMA_VERSION,
    ReportFormatError,
    read_json,
)
from .real_validation_types import ValidationCase, ValidationInputSnapshot
from .real_validation_utils import validate_external_directory


def resume_cases(
    report_path: Path, *, hash_file: Callable[[Path], str]
) -> list[ValidationCase]:
    """Read a manifest and fail before execution if inputs drifted."""
    manifest = read_json(report_path / 'manifest.json')
    if manifest.get('schemaVersion') != REPORT_SCHEMA_VERSION:
        raise ReportFormatError('unsupported real-validation manifest version')
    decoded_cases = cases_from_manifest(manifest)
    cvm_output = _resume_cvm_output(manifest, decoded_cases)
    cases = _rebuild_resume_cvm_cases(decoded_cases, cvm_output)
    cotahist_cases = [case for case in cases if case.source == 'cotahist']
    if cotahist_cases:
        _validate_resume_cotahist_inputs(cotahist_cases, hash_file)
    return cases


def _rebuild_resume_cvm_cases(
    cases: list[ValidationCase], expected_output_root: str | None
) -> list[ValidationCase]:
    """Replace persisted CVM cases with code-owned canonical cases."""
    rebuilt: list[ValidationCase] = []
    for case in cases:
        if case.source != 'cvm':
            rebuilt.append(case)
            continue
        if expected_output_root is None:
            raise ReportFormatError(
                'manifest campaign must contain cvmOutput for CVM resume'
            )
        try:
            rebuilt.append(canonical_cvm_case(case, expected_output_root))
        except ValueError as error:
            raise ReportFormatError(
                f'resume CVM case is not in the official matrix for '
                f'caseId={case.case_id}: {error}'
            ) from error
    return rebuilt


def _resume_cvm_output(
    manifest: dict[str, Any], cases: list[ValidationCase]
) -> str | None:
    """Validate the persisted CVM destination before reconstruction."""
    if not any(case.source == 'cvm' for case in cases):
        return None
    campaign = manifest.get('campaign')
    if not isinstance(campaign, dict):
        raise ReportFormatError(
            'manifest campaign must contain cvmOutput for CVM resume'
        )
    raw_output = campaign.get('cvmOutput')
    if not isinstance(raw_output, str) or not raw_output.strip():
        raise ReportFormatError(
            'manifest campaign cvmOutput must be a non-empty directory'
        )
    try:
        return str(validate_external_directory(raw_output, '--cvm-output'))
    except (OSError, SecurityError, ValueError) as error:
        raise ReportFormatError(
            f'invalid manifest campaign cvmOutput: {error}'
        ) from error


def _validate_resume_cotahist_inputs(
    cases: list[ValidationCase], hash_file: Callable[[Path], str]
) -> None:
    normalized_paths, snapshots_by_path = _collect_resume_snapshots(cases)
    year_by_path = _validate_resume_catalog_identity(cases, snapshots_by_path)
    _validate_resume_case_identity(cases, normalized_paths, year_by_path)
    _validate_current_resume_snapshots(cases, snapshots_by_path, hash_file)


def _collect_resume_snapshots(
    cases: list[ValidationCase],
) -> tuple[dict[str, tuple[Path, ...]], dict[Path, ValidationInputSnapshot]]:
    normalized_paths: dict[str, tuple[Path, ...]] = {}
    snapshots_by_path: dict[Path, ValidationInputSnapshot] = {}
    for case in cases:
        snapshots = case.input_files
        if not snapshots:
            raise ReportFormatError(
                _resume_input_error(
                    case, 'manifest_metadata', 'inputFiles is empty'
                )
            )
        paths = tuple(
            Path(item.path).expanduser().resolve() for item in snapshots
        )
        normalized_paths[case.case_id] = paths
        if Path(case.input_path).expanduser().resolve() != paths[0]:
            raise ReportFormatError(
                _resume_input_error(
                    case,
                    'identity',
                    'inputPath does not match the first inputFiles entry',
                )
            )
        for path, snapshot in zip(paths, snapshots, strict=True):
            existing = snapshots_by_path.get(path)
            if existing is not None and existing != snapshot:
                raise ReportFormatError(
                    _resume_input_error(
                        case,
                        'manifest_metadata',
                        f'conflicting input snapshots for {path}',
                    )
                )
            snapshots_by_path[path] = snapshot
            if not path.is_file():
                raise ReportFormatError(
                    _resume_input_error(case, 'missing', str(path))
                )
    return normalized_paths, snapshots_by_path


def _validate_resume_catalog_identity(
    cases: list[ValidationCase],
    snapshots_by_path: dict[Path, ValidationInputSnapshot],
) -> dict[Path, int]:
    parents = {path.parent for path in snapshots_by_path}
    if len(parents) != 1:
        raise ReportFormatError(
            'resume manifest contains COTAHIST inputs from multiple '
            'directories'
        )
    requested_years = sorted(
        {
            year
            for case in cases
            for year in range(
                case.initial_year
                if case.initial_year is not None
                else case.year,
                (case.last_year if case.last_year is not None else case.year)
                + 1,
            )
        }
    )
    catalog = _resume_catalog(cases[0], parents.pop(), requested_years)
    year_by_path = {
        path.resolve(): year
        for year, paths in catalog.items()
        for path in paths
    }
    expected_paths = set(year_by_path)
    if expected_paths != set(snapshots_by_path):
        raise ReportFormatError(
            _resume_input_error(
                cases[0],
                'catalog_identity',
                'manifest inputs do not match the selected annual catalog',
            )
        )
    return year_by_path


def _validate_resume_case_identity(
    cases: list[ValidationCase],
    normalized_paths: dict[str, tuple[Path, ...]],
    year_by_path: dict[Path, int],
) -> None:
    for case in cases:
        paths = normalized_paths[case.case_id]
        first = (
            case.initial_year if case.initial_year is not None else case.year
        )
        last = case.last_year if case.last_year is not None else case.year
        actual_years = [year_by_path.get(path) for path in paths]
        expected_id = (
            f'cotahist-multi-parity-{first}-{last}'
            if case.mode == 'multi_parity'
            else f'cotahist-{case.mode}-{case.year}'
        )
        first_snapshot = case.input_files[0]
        identity_matches = (
            actual_years == list(range(first, last + 1)),
            case.year == first,
            case.case_id == expected_id,
            case.output_root == '',
            case.document is None,
            case.url is None,
            case.input_size_bytes == first_snapshot.size_bytes,
            case.input_sha256 == first_snapshot.sha256,
        )
        if not all(identity_matches):
            raise ReportFormatError(
                _resume_input_error(
                    case,
                    'identity',
                    'case range, input files, snapshot, or source fields do '
                    'not match the COTAHIST matrix',
                )
            )


def _validate_current_resume_snapshots(
    cases: list[ValidationCase],
    snapshots_by_path: dict[Path, ValidationInputSnapshot],
    hash_file: Callable[[Path], str],
) -> None:
    for path, snapshot in snapshots_by_path.items():
        try:
            current_size = path.stat().st_size
            current_hash = hash_file(path)
        except OSError as error:
            case = cases[0]
            raise ReportFormatError(
                _resume_input_error(case, 'unreadable', f'{path}: {error}')
            ) from error
        if (
            current_size != snapshot.size_bytes
            or current_hash.casefold() != snapshot.sha256.casefold()
        ):
            raise ReportFormatError(
                _resume_input_error(
                    cases[0],
                    'changed',
                    f'{path}: size or sha256 differs from the manifest',
                )
            )


def _resume_catalog(
    case: ValidationCase, parent: Path, requested_years: list[int]
) -> dict[int, list[Path]]:
    """Load the selected catalog and preserve its diagnostic cause."""
    from globaldatafinance.brazil.b3_data.historical_quotes.catalog import (
        index_cotahist_catalog,
    )
    from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
        CotahistCatalogError,
    )

    try:
        return index_cotahist_catalog(parent, expected_years=requested_years)
    except CotahistCatalogError as error:
        raise ReportFormatError(
            _resume_input_error(case, 'catalog_validation', str(error))
        ) from error


def _resume_input_error(
    case: ValidationCase, drift_type: str, detail: str
) -> str:
    """Build stable resume guidance without modifying existing results."""
    return (
        f'resume input drift for caseId={case.case_id}: '
        f'{drift_type} ({detail}). Start a new campaign; '
        'existing results were not modified.'
    )
