"""Deterministic tests for the real-validation case matrix."""

from __future__ import annotations

from dataclasses import replace
from os import sep
from pathlib import Path

import pytest

from scripts import real_validation as cli
from scripts.real_validation_matrix import build_cases, manifest_for
from scripts.real_validation_matrix.cases import (
    canonical_cvm_case,
    normalized_path,
    selected_documents,
)
from scripts.real_validation_matrix.manifest import cases_from_manifest
from scripts.real_validation_report import ReportFormatError, write_json
from scripts.real_validation_types import ValidationCase
from tests.support.builders import build_cotahist_record, write_cotahist_zip

pytestmark = pytest.mark.unit


def test_cotahist_matrix_builds_fast_parity_and_all_modes(
    tmp_path: Path,
) -> None:
    """Each requested B3 mode points at the catalogued annual input."""
    archive = write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024)],
    )

    fast = build_cases(
        source='cotahist',
        initial_year=2024,
        last_year=2024,
        document=None,
        cotahist_path=str(tmp_path),
        cvm_output=None,
        cotahist_modes='fast',
    )
    parity = build_cases(
        source='cotahist',
        initial_year=2024,
        last_year=2024,
        document=None,
        cotahist_path=str(tmp_path),
        cvm_output=None,
        cotahist_modes='parity',
    )
    all_modes = build_cases(
        source='cotahist',
        initial_year=2024,
        last_year=2024,
        document=None,
        cotahist_path=str(tmp_path),
        cvm_output=None,
        cotahist_modes='all',
    )

    assert [case.case_id for case in fast] == ['cotahist-fast-2024']
    assert [case.case_id for case in parity] == ['cotahist-parity-2024']
    assert {case.case_id for case in all_modes} == {
        'cotahist-fast-2024',
        'cotahist-parity-2024',
        'cotahist-multi-parity-2024-2024',
    }
    assert all(case.input_path == str(archive) for case in all_modes)
    assert all(
        case.input_size_bytes == archive.stat().st_size for case in fast
    )
    assert all(case.input_sha256 for case in all_modes)


def test_cotahist_matrix_rejects_missing_selected_year(tmp_path: Path) -> None:
    """A selected year must exist even when the catalog has another year."""
    write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record(year=2024)],
    )

    with pytest.raises(ValueError, match='missing years'):
        build_cases(
            source='cotahist',
            initial_year=2023,
            last_year=2023,
            document=None,
            cotahist_path=str(tmp_path),
            cvm_output=None,
        )


@pytest.mark.parametrize(
    ('initial_year', 'last_year', 'message'),
    [
        (1985, 2024, '1986..'),
        (2024, 2027, '1986..'),
        (2024, 2023, '1986..'),
    ],
)
def test_cotahist_matrix_rejects_invalid_year_ranges(
    tmp_path: Path,
    initial_year: int,
    last_year: int,
    message: str,
) -> None:
    """The B3 matrix rejects ranges outside its supported annual window."""
    with pytest.raises(ValueError, match=message):
        build_cases(
            source='cotahist',
            initial_year=initial_year,
            last_year=last_year,
            document=None,
            cotahist_path=str(tmp_path),
            cvm_output=None,
        )


def test_all_matrix_combines_one_b3_case_with_one_cvm_case(
    tmp_path: Path,
) -> None:
    """The all-source request keeps both owners in one stable matrix."""
    input_directory = tmp_path / 'inputs'
    input_directory.mkdir()
    write_cotahist_zip(
        input_directory,
        year=2024,
        records=[build_cotahist_record(year=2024)],
    )

    cases = build_cases(
        source='all',
        initial_year=2024,
        last_year=2024,
        document='DFP',
        cotahist_path=str(input_directory),
        cvm_output=str(tmp_path / 'cvm-output'),
    )

    assert [case.case_id for case in cases] == [
        'cotahist-fast-2024',
        'cotahist-multi-parity-2024-2024',
        'cotahist-parity-2024',
        'cvm-DFP-2024',
    ]
    assert cases[-1].output_root == str((tmp_path / 'cvm-output').resolve())


def test_manifest_round_trip_normalizes_campaign_paths(tmp_path: Path) -> None:
    """Manifest serialization preserves case data and canonical paths."""
    case = ValidationCase(
        case_id='cvm-DFP-2024',
        source='cvm',
        year=2024,
        input_path='https://example.test/dfp.zip',
        output_root=str(tmp_path / 'output'),
        document='DFP',
        mode='cvm',
        url='https://example.test/dfp.zip',
    )

    manifest = manifest_for(
        [case],
        source='cvm',
        initial_year=2024,
        last_year=2024,
        document='DFP',
        cotahist_path=None,
        cvm_output=str(tmp_path / 'output'),
        timeout=12.5,
    )
    decoded = cases_from_manifest(manifest)

    assert manifest['campaign']['cotahistPath'] is None
    assert manifest['campaign']['cvmOutput'] == str(
        (tmp_path / 'output').resolve()
    )
    assert decoded == [case]
    assert normalized_path(None) is None


def test_selected_documents_accepts_case_insensitive_names() -> None:
    """Document selection accepts the public spelling and preserves order."""
    assert selected_documents(None)[0] == 'CGVN'
    assert selected_documents('all')[-1] == 'VLMO'
    assert selected_documents('dfp') == ('DFP',)


def test_selected_documents_rejects_unknown_document() -> None:
    """An unknown document cannot silently produce an empty matrix."""
    with pytest.raises(ValueError, match='unsupported CVM document'):
        selected_documents('unknown')


def test_cvm_matrix_rejects_missing_output_and_invalid_years() -> None:
    """CVM cases require an output root and supported year bounds."""
    with pytest.raises(ValueError, match='--cvm-output'):
        build_cases(
            source='cvm',
            initial_year=None,
            last_year=None,
            document=None,
            cotahist_path=None,
            cvm_output=None,
        )
    with pytest.raises(ValueError, match=r'2003\.\.2026'):
        build_cases(
            source='cvm',
            initial_year=2002,
            last_year=2026,
            document=None,
            cotahist_path=None,
            cvm_output=str(Path(sep, 'tmp')),
        )


def test_cvm_matrix_can_have_no_cases_before_document_start(
    tmp_path: Path,
) -> None:
    """A valid global request may be empty for a document's later start."""
    cases = build_cases(
        source='cvm',
        initial_year=2010,
        last_year=2017,
        document='CGVN',
        cotahist_path=None,
        cvm_output=str(tmp_path),
    )

    assert cases == []


def test_canonical_cvm_case_rebuilds_and_compares_every_network_identity_field(
    tmp_path: Path,
) -> None:
    """A persisted CVM case cannot override code-owned document/year rules."""
    case = build_cases(
        source='cvm',
        initial_year=2024,
        last_year=2024,
        document='DFP',
        cotahist_path=None,
        cvm_output=str(tmp_path / 'output'),
    )[0]

    assert canonical_cvm_case(case, str(tmp_path / 'output')) == case

    tampered = replace(
        case,
        input_path='http://127.0.0.1/private',
        url='http://127.0.0.1/private',
    )
    with pytest.raises(ValueError, match='inputPath, url'):
        canonical_cvm_case(tampered, str(tmp_path / 'output'))

    with pytest.raises(ValueError, match='outputRoot'):
        canonical_cvm_case(case, str(tmp_path / 'other-output'))


def test_cases_from_manifest_rejects_corrupt_case_order_and_values() -> None:
    """Manifest decoding fails closed on structural matrix corruption."""
    case = ValidationCase(
        case_id='cvm-DFP-2024',
        source='cvm',
        year=2024,
        input_path='https://example.test/dfp.zip',
        output_root=str(Path(sep, 'tmp', 'output')),
        document='DFP',
        mode='cvm',
    )
    raw = case.to_manifest_dict()

    with pytest.raises(ReportFormatError, match='non-empty list'):
        cases_from_manifest({'cases': []})
    with pytest.raises(ReportFormatError, match='must be an object'):
        cases_from_manifest({'cases': [None]})
    with pytest.raises(ReportFormatError, match='unique and sorted'):
        cases_from_manifest({'cases': [raw, raw]})
    with pytest.raises(ReportFormatError, match='source must be one of'):
        cases_from_manifest({'cases': [{**raw, 'source': 'unknown'}]})


def test_cases_from_manifest_rejects_inconsistent_source_and_mode() -> None:
    """A COTAHIST case cannot use the CVM processing mode."""
    case = ValidationCase(
        case_id='cotahist-fast-2024',
        source='cotahist',
        year=2024,
        input_path=str(Path(sep, 'tmp', 'COTAHIST_A2024.ZIP')),
        output_root='',
        mode='fast',
    )

    with pytest.raises(ReportFormatError, match='inconsistent'):
        cases_from_manifest(
            {'cases': [{**case.to_manifest_dict(), 'mode': 'cvm'}]}
        )


@pytest.mark.parametrize('value', ['true', 1, None])
def test_historical_baseline_manifest_requires_boolean_intent(
    tmp_path: Path, value
) -> None:
    """A malformed baseline flag cannot silently change acceptance."""
    case = ValidationCase(
        case_id='cotahist-multi-parity-2000-2026',
        source='cotahist',
        year=2000,
        input_path=str(tmp_path / 'COTAHIST_A2000.ZIP'),
        output_root='',
        mode='multi_parity',
    )

    with pytest.raises(ReportFormatError, match='must be a boolean'):
        cases_from_manifest(
            {'cases': [{**case.to_manifest_dict(), 'frozenBaseline': value}]}
        )


def test_legacy_manifest_defaults_to_generic_acceptance(
    tmp_path: Path,
) -> None:
    """Older manifests remain readable without an implicit historical pin."""
    case = ValidationCase(
        case_id='cotahist-fast-2024',
        source='cotahist',
        year=2024,
        input_path=str(tmp_path / 'COTAHIST_A2024.ZIP'),
        output_root='',
        mode='fast',
    )
    legacy = case.to_manifest_dict()
    legacy.pop('frozenBaseline')

    assert cases_from_manifest({'cases': [legacy]}) == [case]


def test_historical_baseline_cannot_be_attached_to_annual_case(
    tmp_path: Path,
) -> None:
    """Historical acceptance belongs to the complete multi-year proof."""
    case = ValidationCase(
        case_id='cotahist-fast-2024',
        source='cotahist',
        year=2024,
        input_path=str(tmp_path / 'COTAHIST_A2024.ZIP'),
        output_root='',
        mode='fast',
        frozen_baseline=True,
    )

    with pytest.raises(ReportFormatError, match='multi-year COTAHIST parity'):
        cases_from_manifest({'cases': [case.to_manifest_dict()]})


@pytest.mark.parametrize('historical', [False, True])
@pytest.mark.parametrize(
    'evidence',
    ['manifest.json', 'results.jsonl', 'summary.json', 'logs', 'work'],
)
def test_new_campaign_rejects_existing_evidence_without_modifying_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    evidence: str,
    historical: bool,
) -> None:
    """An old generic pass cannot become a new historical acceptance."""
    report = tmp_path / 'report'
    report.mkdir()
    stored = report / evidence
    if evidence in {'logs', 'work'}:
        stored.mkdir()
        stored = stored / 'existing.txt'
    stored.write_bytes(b'previous campaign evidence\n')
    previous = stored.read_bytes()

    def unexpected_call(*_args, **_kwargs):
        pytest.fail('Existing evidence must be rejected before campaign work')

    monkeypatch.setattr(cli, 'build_cases', unexpected_call)
    monkeypatch.setattr(cli, 'run_campaign', unexpected_call)
    args = ['--source', 'cotahist', '--report', str(report)]
    if historical:
        args.append('--cotahist-frozen-baseline')

    assert cli.main(args) == 3
    assert 'already contains campaign evidence' in capsys.readouterr().err
    assert stored.read_bytes() == previous
    assert sorted(path.name for path in report.iterdir()) == [evidence]


def test_resume_cannot_upgrade_a_generic_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A historical resume flag cannot overwrite the persisted intent."""
    archive = write_cotahist_zip(
        tmp_path, year=2024, records=[build_cotahist_record()]
    )
    cases = build_cases(
        source='cotahist',
        initial_year=2024,
        last_year=2024,
        document=None,
        cotahist_path=str(archive.parent),
        cvm_output=None,
        cotahist_modes='all',
    )
    report = tmp_path / 'report'
    write_json(
        report / 'manifest.json',
        manifest_for(
            cases,
            source='cotahist',
            initial_year=2024,
            last_year=2024,
            document=None,
            cotahist_path=str(archive.parent),
            cvm_output=None,
            timeout=300,
        ),
    )
    previous = (report / 'manifest.json').read_bytes()

    def unexpected_run(*_args, **_kwargs):
        pytest.fail('A generic campaign cannot resume as historical')

    monkeypatch.setattr(cli, 'run_campaign', unexpected_run)

    assert (
        cli.main(
            [
                '--resume',
                '--report',
                str(report),
                '--cotahist-frozen-baseline',
            ]
        )
        == 3
    )
    assert (report / 'manifest.json').read_bytes() == previous
