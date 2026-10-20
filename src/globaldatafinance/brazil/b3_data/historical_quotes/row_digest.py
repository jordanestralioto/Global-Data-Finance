"""Canonical ordered digest for B3 logical quotation rows."""

from __future__ import annotations

import base64
import hashlib
from collections.abc import Sequence
from functools import lru_cache
from typing import TYPE_CHECKING, Protocol

from .layout import B3_FIELD_NAMES, B3_LAYOUT_VERSION

if TYPE_CHECKING:
    from pyarrow import Array

_PREFIX_LIMIT = 512
_STRING_PREFIXES = tuple(
    b'S' + length.to_bytes(8, 'big') for length in range(_PREFIX_LIMIT)
)
_BINARY_PREFIXES = tuple(
    b'B' + length.to_bytes(8, 'big') for length in range(_PREFIX_LIMIT)
)


class _HashDigest(Protocol):
    """Minimal digest surface used for testable canonical framing."""

    def update(self, data: bytes | memoryview, /) -> None: ...

    def hexdigest(self) -> str: ...


class B3OrderedRowDigest:
    """Hash schema-ordered values with explicit types and length framing."""

    def __init__(self) -> None:
        """Initialize a SHA-256 stream with the versioned logical layout."""
        self._digest: _HashDigest = hashlib.sha256()
        self._digest.update(b'GLOBALDATAFINANCE-B3-ROW-DIGEST\x00')
        self._digest.update(B3_LAYOUT_VERSION.to_bytes(4, 'big'))
        self._digest.update(len(B3_FIELD_NAMES).to_bytes(2, 'big'))
        for name in B3_FIELD_NAMES:
            _update_frame(self._digest, b'N', name.encode('utf-8'))
        self.rows = 0

    def update(self, row: Sequence[str | bytes | None]) -> None:
        """Append one row while preserving order and duplicate occurrences."""
        if len(row) != len(B3_FIELD_NAMES):
            raise ValueError(
                f'B3 digest row width must be {len(B3_FIELD_NAMES)}'
            )
        frames = [b'R']
        for value in row:
            if value is None:
                frames.append(b'Z')
            else:
                kind, payload, prefixes = (
                    (b'B', base64.b64encode(value), _BINARY_PREFIXES)
                    if isinstance(value, bytes)
                    else (b'S', value.encode('utf-8'), _STRING_PREFIXES)
                )
                size = len(payload)
                prefix = (
                    prefixes[size]
                    if size < _PREFIX_LIMIT
                    else kind + size.to_bytes(8, 'big')
                )
                frames.extend((prefix, payload))
        self._digest.update(b''.join(frames))
        self.rows += 1

    def update_columns(self, columns: Sequence[Array]) -> None:
        """Append a bounded Arrow segment with exact canonical row framing."""
        import pyarrow as pa
        import pyarrow.compute as pc

        if len(columns) != len(B3_FIELD_NAMES):
            raise ValueError(
                f'B3 digest row width must be {len(B3_FIELD_NAMES)}'
            )
        row_count = len(columns[0])
        if any(len(column) != row_count for column in columns):
            raise ValueError('B3 digest columns must have equal row counts')
        if not row_count:
            return
        framed = [_frame_arrow_column(column) for column in columns]
        rows = pc.binary_join_element_wise(
            pa.scalar(b'R', type=pa.large_binary()),
            *framed,
            pa.scalar(b'', type=pa.large_binary()),
        )
        _, offsets, payload = rows.buffers()
        positions = pa.Array.from_buffers(
            pa.int64(), row_count + 1, [None, offsets], offset=rows.offset
        )
        start, end = positions[0].as_py(), positions[-1].as_py()
        self._digest.update(memoryview(payload)[start:end])
        self.rows += row_count

    def hexdigest(self) -> str:
        """Return the current lowercase SHA-256 digest."""
        return self._digest.hexdigest()


def _update_frame(digest: _HashDigest, kind: bytes, value: bytes) -> None:
    """Hash one typed payload with an unambiguous 64-bit byte length."""
    digest.update(kind)
    digest.update(len(value).to_bytes(8, 'big'))
    digest.update(value)


@lru_cache(maxsize=2)
def _arrow_prefixes(binary: bool) -> Array:
    """Build immutable constant header arrays independently of data values."""
    import pyarrow as pa

    return pa.array(
        _BINARY_PREFIXES if binary else _STRING_PREFIXES,
        type=pa.large_binary(),
    )


def _frame_arrow_column(column: Array) -> Array:
    """Frame canonical values with native joins and explicit null markers."""
    import pyarrow as pa
    import pyarrow.compute as pc

    kind = column.type
    binary = (
        pa.types.is_binary(kind)
        or pa.types.is_large_binary(kind)
        or pa.types.is_fixed_size_binary(kind)
    )
    if pa.types.is_fixed_size_binary(kind) and column.null_count == 0:
        data = memoryview(column.buffers()[1])
        width = kind.byte_width
        start = column.offset * width
        values = pa.array(
            [
                base64.b64encode(data[offset : offset + width])
                for offset in range(start, start + len(column) * width, width)
            ],
            type=pa.large_binary(),
        )
    elif binary:
        values = pa.array(
            [
                base64.b64encode(value) if value is not None else None
                for value in column.to_pylist()
            ],
            type=pa.large_binary(),
        )
    elif pa.types.is_string(kind) or pa.types.is_large_string(kind):
        values = pc.cast(column, pa.large_binary(), safe=True)
    else:
        raise TypeError(f'Unsupported canonical B3 digest column type: {kind}')
    lengths = pc.binary_length(values)
    maximum = pc.max(lengths).as_py()
    if maximum is None or maximum < _PREFIX_LIMIT:
        prefixes = pc.take(_arrow_prefixes(binary), lengths)
    else:
        tag = b'B' if binary else b'S'
        prefixes = pa.array(
            [
                tag + size.to_bytes(8, 'big') if size is not None else None
                for size in lengths.to_pylist()
            ],
            type=pa.large_binary(),
        )
    framed = pc.binary_join_element_wise(
        prefixes, values, pa.scalar(b'', type=pa.large_binary())
    )
    return pc.fill_null(framed, b'Z')
