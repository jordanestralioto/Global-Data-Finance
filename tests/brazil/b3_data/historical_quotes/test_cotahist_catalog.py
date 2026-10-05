"""COTAHIST catalog validation contracts."""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.catalog import (
    index_cotahist_catalog,
    select_cotahist_file,
    validate_cotahist_catalog,
)
from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    CotahistCatalogError,
)
from tests.support.builders import (
    build_cotahist_header,
    build_cotahist_record,
    build_cotahist_trailer,
    build_long_cotahist_line,
    write_cotahist_txt,
    write_cotahist_zip,
    write_zip,
)

pytestmark = pytest.mark.integration


def test_manifest_index_defers_quote_validation_to_full_preflight(
    tmp_path: Path,
) -> None:
    """Indexed containers still undergo full quotation preflight."""
    source = write_cotahist_zip(
        tmp_path, year=2024, records=[build_cotahist_record(ticker='')]
    )

    assert index_cotahist_catalog(tmp_path) == {2024: [source]}
    with pytest.raises(CotahistCatalogError, match='ticker'):
        validate_cotahist_catalog(tmp_path)
    assert sorted(tmp_path.iterdir()) == [source]


@pytest.mark.parametrize('same_contents', [True, False])
def test_manifest_index_preserves_zip_txt_content_equivalence(
    tmp_path: Path, same_contents: bool
) -> None:
    """ZIP precedence requires identical complete source contents."""
    record = build_cotahist_record(year=2024)
    source = write_cotahist_zip(tmp_path, year=2024, records=[record])
    other = record if same_contents else build_cotahist_record(ticker='OTHER')
    write_cotahist_txt(tmp_path, year=2024, records=[other])

    if same_contents:
        assert index_cotahist_catalog(tmp_path) == {2024: [source]}
    else:
        with pytest.raises(
            CotahistCatalogError, match='Conflicting ZIP and TXT'
        ):
            index_cotahist_catalog(tmp_path)


@pytest.mark.parametrize('payload', [b'', b'not a zip'])
def test_manifest_index_rejects_invalid_containers(
    tmp_path: Path, payload: bytes
) -> None:
    """A source manifest cannot index an empty or unreadable archive."""
    (tmp_path / 'COTAHIST_A2024.ZIP').write_bytes(payload)

    with pytest.raises(CotahistCatalogError):
        index_cotahist_catalog(tmp_path)


def test_manifest_index_rejects_duplicate_names_and_selected_gaps(
    tmp_path: Path,
) -> None:
    """Transport indexing retains strict catalog identity and coverage."""
    source = write_cotahist_zip(
        tmp_path, year=2024, records=[build_cotahist_record()]
    )
    with pytest.raises(CotahistCatalogError, match='missing years'):
        index_cotahist_catalog(tmp_path, expected_years=(2023, 2024))
    source.with_name('cotahist_a2024.zip').write_bytes(source.read_bytes())
    with pytest.raises(CotahistCatalogError, match='Conflicting'):
        index_cotahist_catalog(tmp_path)


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


def test_catalog_rejects_missing_years_but_allows_unrequested_years(
    tmp_path: Path,
) -> None:
    """Requested gaps fail while unrelated annual inputs remain permitted."""
    record = build_cotahist_record(year=2024)
    write_cotahist_zip(tmp_path, year=2024, records=[record])

    with pytest.raises(CotahistCatalogError, match='missing years'):
        validate_cotahist_catalog(tmp_path, expected_years={2023, 2024})

    write_cotahist_zip(tmp_path, year=2023, records=[record])
    assert set(validate_cotahist_catalog(tmp_path, expected_years={2024})) == {
        2024
    }


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
            lambda path: path.write_bytes(
                (
                    build_cotahist_header(2024)
                    + '\n'
                    + build_cotahist_trailer(2024, 0)
                    + '\n'
                ).encode('latin-1')
            ),
        ),
        (
            'COTAHIST_A2024.ZIP',
            lambda path: write_zip(
                path,
                {
                    'COTAHIST_A2024.TXT': (
                        build_cotahist_header(2024)
                        + '\n'
                        + build_cotahist_trailer(2024, 0)
                        + '\n'
                    ).encode('latin-1')
                },
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

    with pytest.raises(CotahistCatalogError, match='has no quotes'):
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
        match=r'physical line 1 exceeds the COTAHIST physical-line limit',
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
