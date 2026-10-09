"""Typed logical, schema, and input digests for benchmarks."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Iterator, Mapping
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any

from scripts.file_digests import sha256_file

from .models import ScenarioInput


def directory_digest(path: Path) -> str:
    """Hash accepted external COTAHIST input names and bytes."""
    digest = hashlib.sha256()
    for child in sorted(path.glob('COTAHIST_A*'), key=lambda item: item.name):
        if child.is_file():
            digest.update(child.name.encode('utf-8'))
            digest.update(sha256_file(child).encode('ascii'))
    return digest.hexdigest()


def verify_input_digest(source: ScenarioInput) -> None:
    """Reject a source changed after the parent recorded its checksum."""
    if source.path is None or not source.input_sha256:
        return
    actual = (
        directory_digest(source.path)
        if source.path.is_dir()
        else sha256_file(source.path)
    )
    if actual != source.input_sha256:
        raise ValueError('Benchmark input checksum changed before measurement')


def schema_fingerprint(schema: Any) -> str:
    """Fingerprint an Arrow schema without depending on physical encoding."""
    return hashlib.sha256(schema.to_string().encode('utf-8')).hexdigest()


def logical_digest(rows: Iterable[Mapping[str, Any]]) -> str:
    """Hash typed logical rows without depending on Parquet encoding.

    The digest deliberately includes the Python value type and, for decimals,
    the exact ``Decimal.as_tuple()`` representation.  This catches changes to
    values, nulls, ordering, and decimal precision while keeping validation
    bounded to one row at a time.
    """
    digest = hashlib.sha256()
    for row in rows:
        canonical = {
            str(key): _canonical_value(value)
            for key, value in sorted(
                row.items(), key=lambda item: str(item[0])
            )
        }
        encoded = json.dumps(
            canonical,
            ensure_ascii=False,
            allow_nan=False,
            separators=(',', ':'),
            sort_keys=True,
        ).encode('utf-8')
        digest.update(encoded)
        digest.update(b'\n')
    return digest.hexdigest()


def digest_parquet_rows(
    parquet: Any,
    *,
    batch_size: int,
    boundary_column: str,
    columns: list[str] | None = None,
) -> tuple[str, str, str]:
    """Digest Arrow rows one at a time and retain boundary values."""
    first = ''
    last = ''

    def rows() -> Iterator[dict[str, Any]]:
        nonlocal first, last
        for batch in parquet.iter_batches(
            batch_size=batch_size, columns=columns
        ):
            names = batch.schema.names
            arrays = [batch.column(idx) for idx in range(batch.num_columns)]
            for r_idx in range(batch.num_rows):
                row = {
                    name: arrays[c_idx][r_idx].as_py()
                    for c_idx, name in enumerate(names)
                }
                val = row.get(boundary_column)
                text = '' if val is None else str(val)
                if not first:
                    first = text
                last = text
                yield row

    return logical_digest(rows()), first, last


def _canonical_value(value: Any) -> dict[str, Any]:
    """Represent one supported logical value with an explicit type tag."""
    if value is None:
        return {'type': 'null', 'value': None}
    if isinstance(value, Decimal):
        decimal_tuple = value.as_tuple()
        return {
            'type': 'decimal',
            'value': [
                decimal_tuple.sign,
                list(decimal_tuple.digits),
                decimal_tuple.exponent,
            ],
        }
    if isinstance(value, date):
        return {'type': 'date', 'value': value.isoformat()}
    if isinstance(value, bool):
        return {'type': 'bool', 'value': value}
    if isinstance(value, (int, float, str)):
        return {'type': type(value).__name__, 'value': value}
    if isinstance(value, bytes):
        return {'type': 'bytes', 'value': value.hex()}
    raise TypeError(f'Unsupported benchmark logical value: {type(value)!r}')
