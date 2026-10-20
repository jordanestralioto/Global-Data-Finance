"""Canonical record bytes stay identical with Arrow batch hashing."""

from __future__ import annotations

import hashlib

import pyarrow as pa
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    content_fingerprint,
)

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('batch_size', [1, 2, 3])
def test_batch_digest_preserves_sliced_unicode_and_empty_fields(
    batch_size: int,
) -> None:
    """Hash only the selected rows, with exact field and record separators."""
    batch = pa.record_batch(
        [
            pa.array(['outside', '0001', '', '-0', 'outside']),
            pa.array(['outside', 'ação 🧪', '', '\x00control', 'outside']),
            pa.array(['outside', 'N/A', 'NULL', ' 1.50 ', 'outside']),
        ],
        names=['id', 'descrição', 'value'],
    ).slice(1, 3)
    expected = hashlib.sha256(
        (
            'exact-text-v1\x00id;descrição;value\n'
            '0001;ação 🧪;N/A\n;;NULL\n-0;\x00control; 1.50 \n'
        ).encode()
    ).hexdigest()
    digest = content_fingerprint.RecordDigest(batch.schema.names)

    for offset in range(0, batch.num_rows, batch_size):
        digest.update_batch(batch.slice(offset, batch_size))

    assert digest.hexdigest() == expected


def test_single_column_batch_preserves_blank_records() -> None:
    """Every blank record contributes its own newline to the fingerprint."""
    digest = content_fingerprint.RecordDigest(['value'])

    digest.update_batch(
        pa.record_batch([['', 'ação', '', 'NULL']], names=['value'])
    )

    assert (
        digest.hexdigest()
        == hashlib.sha256(
            'exact-text-v1\x00value\n\nação\n\nNULL\n'.encode()
        ).hexdigest()
    )


def test_empty_batch_does_not_add_a_record() -> None:
    """Header-only output has the same fingerprint with an empty batch."""
    digest = content_fingerprint.RecordDigest(['value'])

    digest.update_batch(
        pa.record_batch([pa.array([], type=pa.string())], names=['value'])
    )

    assert (
        digest.hexdigest()
        == hashlib.sha256(b'exact-text-v1\x00value\n').hexdigest()
    )


def test_row_and_batch_updates_share_the_same_digest_stream() -> None:
    """Input rows and output batches use the same ordered canonical format."""
    digest = content_fingerprint.RecordDigest(['value'])
    digest.update(['before'])
    digest.update_batch(pa.record_batch([['0001', '-0']], names=['value']))
    digest.update(['after'])

    assert (
        digest.hexdigest()
        == hashlib.sha256(
            b'exact-text-v1\x00value\nbefore\n0001\n-0\nafter\n'
        ).hexdigest()
    )


def test_null_batch_is_rejected_without_changing_the_digest() -> None:
    """A rejected null cannot silently contribute partial content."""
    digest = content_fingerprint.RecordDigest(['value'])
    digest.update(['original'])
    expected = digest.hexdigest()
    batch = pa.record_batch(
        [pa.array(['replacement', None], type=pa.string())], names=['value']
    )

    with pytest.raises(
        ValueError, match='Exact-text CVM Parquet contains nulls'
    ):
        digest.update_batch(batch)

    assert digest.hexdigest() == expected
