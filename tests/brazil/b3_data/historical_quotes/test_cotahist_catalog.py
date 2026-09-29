"""COTAHIST catalog validation contracts."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.catalog import (
    CotahistCatalogError,
    select_cotahist_file,
    validate_cotahist_catalog,
)
from tests.support.builders import (
    build_cotahist_record,
    build_long_cotahist_line,
    write_cotahist_txt,
    write_cotahist_zip,
    write_zip,
)

pytestmark = pytest.mark.integration


def test_catalog_accepts_exact_years_and_zip_precedence(
    tmp_path: Path,
) -> None:
    """A complete expected catalog accepts ZIP/TXT precedence explicitly."""
    record_2023 = build_cotahist_record(year=2023, ticker='YEAR2023')
    record_2024 = build_cotahist_record(year=2024, ticker='YEAR2024')
    zip_path = write_cotahist_zip(tmp_path, year=2023, records=[record_2023])
    write_cotahist_txt(tmp_path, year=2023, records=[record_2023])
    write_cotahist_zip(tmp_path, year=2024, records=[record_2024])

    catalog = validate_cotahist_catalog(tmp_path, expected_years={2023, 2024})

    assert set(catalog) == {2023, 2024}
    assert select_cotahist_file(catalog, 2023) == zip_path


def test_catalog_rejects_missing_and_unexpected_years(tmp_path: Path) -> None:
    """An exact campaign catalog cannot silently omit or add official years."""
    record = build_cotahist_record(year=2024)
    write_cotahist_zip(tmp_path, year=2024, records=[record])

    with pytest.raises(CotahistCatalogError, match='missing years'):
        validate_cotahist_catalog(tmp_path, expected_years={2023, 2024})

    write_cotahist_zip(tmp_path, year=2023, records=[record])
    with pytest.raises(CotahistCatalogError, match='unexpected years'):
        validate_cotahist_catalog(tmp_path, expected_years={2024})


def test_catalog_rejects_duplicate_same_extension(tmp_path: Path) -> None:
    """Two candidates without a precedence rule must fail closed."""
    record = build_cotahist_record(year=2024)
    payload = (record + '\n').encode('latin-1')
    write_zip(
        tmp_path / 'COTAHIST_A2024.ZIP',
        {
            'COTAHIST_A2024.TXT': payload,
        },
    )
    write_zip(
        tmp_path / 'cotahist_a2024.zip',
        {
            'COTAHIST_A2024.TXT': payload,
        },
    )

    with pytest.raises(CotahistCatalogError, match='Conflicting'):
        validate_cotahist_catalog(tmp_path)


def test_catalog_rejects_empty_and_invalid_inputs(tmp_path: Path) -> None:
    """Empty plain text and malformed ZIP files are not catalog entries."""
    (tmp_path / 'COTAHIST_A2023.TXT').touch()

    with pytest.raises(CotahistCatalogError, match='empty'):
        validate_cotahist_catalog(tmp_path)


@pytest.mark.parametrize(
    ('filename', 'writer'),
    [
        (
            'COTAHIST_A2024.TXT',
            lambda path: path.write_bytes(b'00HEADER\n99TRAILER\n'),
        ),
        (
            'COTAHIST_A2024.ZIP',
            lambda path: write_zip(
                path, {'COTAHIST_A2024.TXT': b'00HEADER\n99TRAILER\n'}
            ),
        ),
    ],
)
def test_catalog_rejects_inputs_without_quote_data_records(
    tmp_path: Path,
    filename: str,
    writer,
) -> None:
    """Header/trailer-only candidates cannot enter a processable catalog."""
    writer(tmp_path / filename)

    with pytest.raises(CotahistCatalogError, match='no type-01 quote data'):
        validate_cotahist_catalog(tmp_path)


@pytest.mark.parametrize('extension', ['TXT', 'ZIP'])
def test_catalog_rejects_overwide_physical_lines_before_decoding(
    tmp_path: Path, extension: str
) -> None:
    """Catalog validation reads at most one bounded COTAHIST line at once."""
    path = tmp_path / f'COTAHIST_A2024.{extension}'
    oversized_line = build_long_cotahist_line(1_000_002)
    payload = oversized_line + b'\n'
    if extension == 'TXT':
        path.write_bytes(payload)
    else:
        write_zip(path, {'COTAHIST_A2024.TXT': payload})

    with pytest.raises(
        CotahistCatalogError,
        match=r'oversized physical line.*physical line 1',
    ):
        validate_cotahist_catalog(tmp_path)


def test_catalog_rejects_invalid_zip(tmp_path: Path) -> None:
    """A named ZIP must be readable before it can enter the catalog."""
    (tmp_path / 'COTAHIST_A2024.ZIP').write_bytes(b'not a zip')

    with pytest.raises(CotahistCatalogError, match='Invalid COTAHIST ZIP'):
        validate_cotahist_catalog(tmp_path)


@pytest.mark.parametrize(
    ('member_name', 'reason'),
    [
        ('nested/COTAHIST_A2024.TXT', 'archive root'),
        ('COTAHIST_A2023.TXT', 'does not match its internal member'),
    ],
)
def test_catalog_rejects_unsafe_member_resolution(
    tmp_path: Path, member_name: str, reason: str
) -> None:
    """Nested and mismatched internal member names cannot be selected."""
    write_zip(
        tmp_path / 'COTAHIST_A2024.ZIP',
        {member_name: b'not a complete market record'},
    )

    with pytest.raises(CotahistCatalogError, match=reason):
        validate_cotahist_catalog(tmp_path)


def test_catalog_rejects_multiple_internal_candidates(tmp_path: Path) -> None:
    """An archive with two historical member layouts is ambiguous."""
    with zipfile.ZipFile(tmp_path / 'COTAHIST_A2024.ZIP', 'w') as archive:
        archive.writestr('COTAHIST_A2024.TXT', b'first')
        archive.writestr('COTAHIST.A2024', b'second')

    with pytest.raises(CotahistCatalogError, match='Ambiguous'):
        validate_cotahist_catalog(tmp_path)
