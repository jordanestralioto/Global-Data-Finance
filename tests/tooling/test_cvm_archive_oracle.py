"""Independent CVM source reconciliation against real persisted artifacts."""

from __future__ import annotations

import csv
import hashlib
import zipfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from scripts.cvm_archive_oracle import reconcile_archive

pytestmark = pytest.mark.integration


def _inputs(root: Path, payload: bytes, rows: list[dict[str, object]]) -> Path:
    """Create oracle inputs without invoking the product's conversion path."""
    source = root / 'source.zip'
    with zipfile.ZipFile(source, 'w') as archive:
        archive.writestr('nested/data.csv', payload)
        archive.writestr('attachment.bin', b'\xef\xbb\xbf\xff')
    schema = pa.schema([('id', pa.string()), ('value', pa.string())])
    pq.write_table(
        pa.Table.from_pylist(rows, schema=schema), root / 'data.parquet'
    )
    return source


@pytest.mark.parametrize(
    'encoding', ['utf-8', 'utf-8-sig', 'cp1252', 'latin-1']
)
def test_oracle_compares_every_field_and_retains_attachment_fingerprints(
    tmp_path: Path, encoding: str
) -> None:
    """Compare all source values and fingerprint opaque attachments."""
    note = (
        '€'
        if encoding == 'cp1252'
        else '\x81'
        if encoding == 'latin-1'
        else 'ação'
    )
    contents = f'id;value\n0001;{note}\n0002;N/A\n;\n'.encode(encoding)
    source = _inputs(
        tmp_path,
        contents,
        [
            {'id': '0001', 'value': note},
            {'id': '0002', 'value': 'N/A'},
            {'id': '', 'value': ''},
        ],
    )
    previous_limit = csv.field_size_limit()

    evidence = reconcile_archive(source, tmp_path)

    assert evidence['status'] == 'passed'
    assert evidence['recordCount'] == 3
    assert evidence['comparedFieldCount'] == 6
    assert evidence['csvCount'] == 1
    assert evidence['attachmentCount'] == 1
    assert (
        evidence['members'][0]['sha256']
        == hashlib.sha256(contents).hexdigest()
    )
    assert (
        evidence['members'][1]['sha256']
        == hashlib.sha256(b'\xef\xbb\xbf\xff').hexdigest()
    )
    assert csv.field_size_limit() == previous_limit


@pytest.mark.parametrize(
    ('rows', 'message'),
    [
        ([{'id': '0001', 'value': 'rounded'}], 'field mismatch'),
        ([], 'record count mismatch'),
        (
            [
                {'id': '0001', 'value': '1.234567890123456789'},
                {'id': '0001', 'value': '1.234567890123456789'},
            ],
            'record count mismatch',
        ),
        ([{'id': '0001', 'value': None}], 'field mismatch'),
    ],
)
def test_oracle_rejects_modified_missing_extra_and_null_values(
    tmp_path: Path, rows: list[dict[str, object]], message: str
) -> None:
    """Readable output cannot conceal value changes or lost records."""
    source = _inputs(tmp_path, b'id;value\n0001;1.234567890123456789\n', rows)
    previous_limit = csv.field_size_limit()

    with pytest.raises(ValueError, match=message):
        reconcile_archive(source, tmp_path)

    assert csv.field_size_limit() == previous_limit
    assert source.exists()


def test_oracle_rejects_reordered_rows(tmp_path: Path) -> None:
    """A correct count cannot conceal an output ordering change."""
    source = _inputs(
        tmp_path,
        b'id;value\n0001;a\n0002;b\n',
        [{'id': '0002', 'value': 'b'}, {'id': '0001', 'value': 'a'}],
    )
    with pytest.raises(ValueError, match='record=1'):
        reconcile_archive(source, tmp_path)


def test_oracle_rejects_unexpected_and_missing_artifacts(
    tmp_path: Path,
) -> None:
    """The directory must account for every CSV in the exact source ZIP."""
    source = _inputs(tmp_path, b'id;value\n', [])
    extra = tmp_path / 'extra.parquet'
    pq.write_table(pa.table({'unexpected': ['x']}), extra)
    with pytest.raises(ValueError, match='artifact inventory'):
        reconcile_archive(source, tmp_path)
    extra.unlink()
    (tmp_path / 'data.parquet').unlink()
    with pytest.raises(FileNotFoundError):
        reconcile_archive(source, tmp_path)
