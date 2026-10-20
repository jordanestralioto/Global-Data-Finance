"""Verify the persisted canonical digest against an independent vector."""

from __future__ import annotations

import base64
import hashlib

import pyarrow as pa
import pytest

from globaldatafinance.brazil.b3_data.historical_quotes.layout import (
    B3_FIELD_NAMES,
    B3_LAYOUT_VERSION,
)
from globaldatafinance.brazil.b3_data.historical_quotes.row_digest import (
    B3OrderedRowDigest,
)

pytestmark = pytest.mark.unit


def test_canonical_digest_encodes_original_bytes_as_base64() -> None:
    """The version 2 vector covers field framing, null, and Base64 bytes."""
    row: list[str | bytes | None] = [''] * 31 + [bytes(range(245))]
    row[16] = None
    digest = B3OrderedRowDigest()

    digest.update(row)

    assert digest.rows == 1
    assert digest.hexdigest() == (
        # pragma: allowlist nextline secret
        'b6787fdcc39c5f60ccf5d873c352b7d3c7aac39386efb85c1be5f7ac44a4b9dd'
    )


def _reference_digest(rows: list[list[str | bytes | None]]) -> str:
    """Hash the version 2 stream one primitive at a time, independently."""
    stream = hashlib.sha256()
    stream.update(b'GLOBALDATAFINANCE-B3-ROW-DIGEST\x00')
    stream.update(B3_LAYOUT_VERSION.to_bytes(4, 'big'))
    stream.update(len(B3_FIELD_NAMES).to_bytes(2, 'big'))
    for name in B3_FIELD_NAMES:
        encoded = name.encode('utf-8')
        stream.update(b'N')
        stream.update(len(encoded).to_bytes(8, 'big'))
        stream.update(encoded)
    for row in rows:
        stream.update(b'R')
        for value in row:
            if value is None:
                stream.update(b'Z')
                continue
            kind, payload = (
                (b'B', base64.b64encode(value))
                if isinstance(value, bytes)
                else (b'S', value.encode('utf-8'))
            )
            stream.update(kind)
            stream.update(len(payload).to_bytes(8, 'big'))
            stream.update(payload)
    return stream.hexdigest()


def test_batched_framing_matches_primitive_stream_across_rows() -> None:
    """Batching bytes per row must not change the persisted digest."""
    width = len(B3_FIELD_NAMES)
    multilingual_row: list[str | bytes | None] = []
    multilingual_row.extend(['ação', 'PETR4', '0.01'] * (width // 3))
    multilingual_row.extend(['x'] * (width % 3))
    rows: list[list[str | bytes | None]] = [
        [''] * width,
        [None] * width,
        multilingual_row,
        ['é' * 300] * (width - 1) + [b'\x00\xff' * 200],
        [str(index) for index in range(width - 1)] + [b''],
    ]
    digest = B3OrderedRowDigest()

    for row in rows:
        digest.update(row)

    assert digest.rows == len(rows)
    assert digest.hexdigest() == _reference_digest(rows)


@pytest.mark.parametrize('width', [0, 31, 33])
def test_incompatible_row_width_is_rejected_without_touching_the_stream(
    width: int,
) -> None:
    """A malformed row raises before any byte enters the running digest."""
    digest = B3OrderedRowDigest()
    before = digest.hexdigest()

    with pytest.raises(ValueError, match='row width must be 32'):
        digest.update([''] * width)

    assert digest.rows == 0
    assert digest.hexdigest() == before


@pytest.mark.parametrize('byte_length', [0, 1, 511, 512, 513, 4096])
def test_length_header_boundaries_preserve_the_primitive_stream(
    byte_length: int,
) -> None:
    """Header reuse and large-value fallback preserve exact typed framing."""
    row: list[str | bytes | None] = ['x' * byte_length] * 32
    row[0] = 'é' * byte_length
    row[16] = None
    row[31] = b'\x00\xff' * byte_length
    rows: list[list[str | bytes | None]] = [row, row, [''] * 32]
    digest = B3OrderedRowDigest()

    for values in rows:
        digest.update(values)

    assert digest.rows == 3
    assert digest.hexdigest() == _reference_digest(rows)


@pytest.mark.parametrize('large_offsets', [False, True])
def test_arrow_segments_match_primitive_framing_and_scalar_updates(
    large_offsets: bool,
) -> None:
    """Slices preserve ordered duplicate, Unicode, binary and null values."""
    rows: list[list[str | bytes | None]] = [
        [''] * 31 + [b''],
        ['ação'] * 31 + [bytes(range(245))],
        [None] * 32,
        ['é' * 513] * 31 + [b'\x00\xff' * 513],
        ['ação'] * 31 + [bytes(range(245))],
    ]
    text_type = pa.large_string() if large_offsets else pa.string()
    binary_type = pa.large_binary() if large_offsets else pa.binary()
    columns = [
        pa.array(
            [row[index] for row in rows],
            type=binary_type if index == 31 else text_type,
        )
        for index in range(32)
    ]
    digest = B3OrderedRowDigest()

    digest.update(rows[0])
    digest.update_columns([column.slice(1, 2) for column in columns])
    digest.update_columns([column.slice(3) for column in columns])

    assert digest.rows == len(rows)
    assert digest.hexdigest() == _reference_digest(rows)
    assert digest.hexdigest() != _reference_digest(list(reversed(rows)))


def test_empty_arrow_segment_preserves_the_existing_stream() -> None:
    """A source with no selected rows contributes no quotation frame."""
    digest = B3OrderedRowDigest()
    digest.update(['x'] * 32)
    before = digest.hexdigest()

    digest.update_columns([pa.array([], type=pa.large_string())] * 32)

    assert digest.rows == 1
    assert digest.hexdigest() == before


@pytest.mark.parametrize('nullable', [False, True])
def test_fixed_binary_slices_keep_offsets_nulls_duplicates_and_batch_order(
    nullable: bool,
) -> None:
    """Buffer framing preserves primitive Base64 framing at nonzero offsets."""
    binaries: list[bytes | None] = [
        bytes(245),
        bytes(range(245)),
        b'\xff' * 245,
        bytes(range(245)),
    ]
    if nullable:
        binaries.insert(2, None)
    rows = [['ação'] * 31 + [value] for value in binaries]
    columns = [pa.array(['ação'] * len(rows), type=pa.large_string())] * 31
    columns.append(pa.array(binaries, type=pa.binary(245)))
    digest = B3OrderedRowDigest()
    digest.update(rows[0])
    digest.update_columns([column.slice(1, 2) for column in columns])
    digest.update_columns([column.slice(3) for column in columns])
    digest.update_columns([column.slice(1, 0) for column in columns])
    assert digest.rows == len(rows)
    assert digest.hexdigest() == _reference_digest(rows)


@pytest.mark.parametrize('mutation', ['width', 'height', 'type'])
def test_invalid_arrow_segment_is_rejected_before_touching_the_stream(
    mutation: str,
) -> None:
    """Malformed columns cannot partially append bytes or row counts."""
    columns = [pa.array(['x', 'y'], type=pa.large_string())] * 32
    if mutation == 'width':
        columns = columns[:-1]
    elif mutation == 'height':
        columns = [*columns[:-1], columns[-1].slice(0, 1)]
    else:
        columns = [*columns[:-1], pa.array([1, 2], type=pa.int64())]
    digest = B3OrderedRowDigest()
    digest.update(['before'] * 32)
    before = digest.hexdigest()

    with pytest.raises((TypeError, ValueError)):
        digest.update_columns(columns)

    assert digest.rows == 1
    assert digest.hexdigest() == before
