"""Property-based invariants for the CVM global Arrow CSV pipeline."""

from __future__ import annotations

import tempfile
import zipfile
from pathlib import Path

import pyarrow.parquet as pq
import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data.csv_pipeline import (
    CvmCsvParquetPipeline,
)

try:
    from hypothesis import given, settings
    from hypothesis import strategies as st
except ModuleNotFoundError:
    pytest.skip(
        'hypothesis is installed through the development dependency group',
        allow_module_level=True,
    )

pytestmark = pytest.mark.integration

_TEXT_ALPHABET = (
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789 '
)


@settings(max_examples=30, deadline=None)
@given(
    rows=st.lists(
        st.tuples(
            st.integers(min_value=-(2**31), max_value=2**31 - 1),
            st.text(alphabet=_TEXT_ALPHABET, min_size=0, max_size=20).map(
                lambda value: f'x{value}'
            ),
        ),
        min_size=1,
        max_size=40,
    )
)
def test_arrow_pipeline_preserves_generated_logical_rows(
    rows: list[tuple[int, str]],
) -> None:
    """Global inference writes generated values in source order."""
    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        archive = root / 'source.zip'
        staging = root / 'staging'
        output = staging / 'source.parquet'
        staging.mkdir()
        payload = 'id;text\n' + ''.join(
            f'{identifier};{text}\n' for identifier, text in rows
        )
        with zipfile.ZipFile(archive, 'w') as source:
            source.writestr('source.csv', payload.encode('utf-8'))

        result = CvmCsvParquetPipeline(archive, 'source.csv').convert(
            staged_path=output,
            staging_dir=staging,
        )

        assert result.rows == len(rows)
        assert pq.read_table(output).to_pylist() == [
            {'id': identifier, 'text': text} for identifier, text in rows
        ]
