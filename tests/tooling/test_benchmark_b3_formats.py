"""Deterministic synthetic containers for complete B3 measurements."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from scripts.benchmark_corpus import prepare_input
from scripts.benchmark_ingestion import _parser, _validate_arguments


@pytest.mark.unit
@pytest.mark.parametrize('scenario', ['b3_100k', 'b3_multi_4x25k'])
def test_zip_corpus_is_deterministic_and_has_no_txt_duplicates(
    tmp_path: Path, scenario: str
) -> None:
    """Equal corpora retain equal ZIP bytes and one annual representation."""
    roots = [tmp_path / name for name in ('first', 'second')]
    for root in roots:
        root.mkdir()
    sources = [
        prepare_input(scenario, root, 8, None, b3_input_format='zip')
        for root in roots
    ]
    assert sources[0].input_sha256 == sources[1].input_sha256
    assert sources[0].expected_digest == sources[1].expected_digest
    files = list(roots[0].rglob('*.ZIP'))
    assert len(files) == sources[0].source_count
    assert not list(roots[0].rglob('*.TXT'))
    for path in files:
        with zipfile.ZipFile(path) as archive:
            assert archive.namelist() == [path.with_suffix('.TXT').name]
            info = archive.infolist()[0]
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            content = archive.read(info)
            assert len(content.splitlines()[0]) == 245
            assert content.startswith(b'00') and content[-246:-244] == b'99'


@pytest.mark.unit
@pytest.mark.parametrize('scenario', ['b3_annual', 'cvm', 'import_root'])
@pytest.mark.parametrize('input_format', ['txt', 'zip'])
def test_cli_rejects_format_for_inapplicable_scenarios(
    scenario: str, input_format: str
) -> None:
    """An explicit format never converts caller-owned or unrelated inputs."""
    arguments = _parser().parse_args(
        ['--scenario', scenario, '--b3-input-format', input_format]
    )
    with pytest.raises(SystemExit, match='synthetic B3'):
        _validate_arguments(arguments, (scenario,))


@pytest.mark.unit
def test_programmatic_zip_format_cannot_convert_annual_input(
    tmp_path: Path,
) -> None:
    """The corpus API also rejects annual ZIP conversion."""
    with pytest.raises(ValueError, match='synthetic B3'):
        prepare_input(
            'b3_annual', tmp_path, None, tmp_path, b3_input_format='zip'
        )
