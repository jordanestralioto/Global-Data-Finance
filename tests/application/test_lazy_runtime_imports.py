"""Fresh-process guarantees for the package's lazy runtime import graph."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from scripts.process_runner import run_process

pytestmark = pytest.mark.integration

_ROOT = Path(__file__).resolve().parents[2]
_ENGINES = ('pandas', 'numpy', 'pyarrow', 'polars')


def _run_probe(program: str) -> dict[str, bool]:
    """Run one exact import scenario in a clean Python interpreter."""
    result = run_process(['python', '-c', program], cwd=_ROOT)
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    return cast(dict[str, bool], json.loads(lines[-1]))


def _engine_state() -> str:
    """Return child-process code that serializes loaded engine module roots."""
    return (
        'import json, sys\n'
        "roots = ('pandas', 'numpy', 'pyarrow', 'polars')\n"
        'sys.stdout.write(json.dumps({root: any((name == root or '
        "name.startswith(root + '.')) and sys.modules[name] is not None "
        'for name in sys.modules) for root in roots}) + "\\n")\n'
    )


def _program(*lines: str) -> str:
    """Build a readable child-process program with a final newline."""
    return '\n'.join(lines) + '\n'


def test_root_and_facade_imports_are_engine_free() -> None:
    """Discovery stays cheap until an extraction operation is chosen."""
    state = _run_probe(
        _program(
            'import globaldatafinance',
            'from globaldatafinance import (',
            '    FundamentalStocksDataCVM,',
            '    HistoricalQuotesB3,',
            ')',
            'FundamentalStocksDataCVM()',
            'HistoricalQuotesB3()',
        )
        + _engine_state()
    )

    assert state == dict.fromkeys(_ENGINES, False)


def test_cvm_csv_pipeline_instantiation_is_engine_free() -> None:
    """Importing and constructing the CVM pipeline remains engine-free."""
    state = _run_probe(
        _program(
            'from globaldatafinance.brazil.cvm.fundamental_stocks_data.'
            'csv_pipeline import CvmCsvParquetPipeline',
            "pipeline = CvmCsvParquetPipeline('dummy.zip', 'dummy.csv')",
        )
        + _engine_state()
    )

    assert state == dict.fromkeys(_ENGINES, False)


def test_lookup_and_non_extracting_download_are_engine_free() -> None:
    """Read-only lookup and download orchestration stay light."""
    state = _run_probe(
        _program(
            'from globaldatafinance import (',
            '    FundamentalStocksDataCVM,',
            '    HistoricalQuotesB3,',
            ')',
            'from unittest.mock import patch',
            'from globaldatafinance.brazil.cvm import fundamental_stocks_data',
            'b3 = HistoricalQuotesB3()',
            'b3.get_available_assets()',
            'b3.get_available_years()',
            'cvm = FundamentalStocksDataCVM()',
            'with patch.object(',
            '    fundamental_stocks_data.DownloadDocumentsUseCaseCVM,',
            "    'execute',",
            '    return_value=fundamental_stocks_data.DownloadResultCVM(),',
            '):',
            "    cvm.download('/tmp', list_docs=['DFP'],",
            '        initial_year=2024,',
            '        last_year=2024,',
            '        automatic_extractor=False,',
            '    )',
        )
        + _engine_state()
    )

    assert state == dict.fromkeys(_ENGINES, False)


def test_legacy_pandas_adapter_loads_only_pandas_on_first_csv_read() -> None:
    """The retained legacy API loads pandas locally and never Arrow engines."""
    state = _run_probe(
        _program(
            'import io, sys',
            "sys.modules['pyarrow'] = None",
            'from globaldatafinance.macro_infra import ReadFilesAdapter',
            "source = io.StringIO('value\\n1\\n')",
            'list(ReadFilesAdapter.read_csv_chunk_size(source, 1))',
        )
        + _engine_state()
    )

    assert state == {
        'pandas': True,
        'numpy': True,
        'pyarrow': False,
        'polars': False,
    }


def test_cvm_and_b3_extractions_load_arrow_but_not_pandas_or_polars() -> None:
    """Both productive paths activate their single Arrow engine on demand."""
    cvm_state = _run_probe(
        _program(
            'import tempfile, zipfile',
            'from pathlib import Path',
            'from globaldatafinance.brazil.cvm import fundamental_stocks_data',
            'with tempfile.TemporaryDirectory() as directory:',
            '    root = Path(directory)',
            "    with zipfile.ZipFile(root / 'source.zip', 'w') as archive:",
            "        archive.writestr('source.csv', b'value\\n1\\n')",
            '    extractor_type = (',
            '        fundamental_stocks_data.ParquetExtractorAdapterCVM',
            '    )',
            '    extractor = extractor_type()',
            "    extractor.extract(str(root / 'source.zip'), str(root))",
        )
        + _engine_state()
    )
    b3_state = _run_probe(
        _program(
            'import tempfile',
            'from pathlib import Path',
            'from globaldatafinance import HistoricalQuotesB3',
            'from tests.support.builders import (',
            '    build_cotahist_record,',
            '    write_cotahist_zip,',
            ')',
            'with tempfile.TemporaryDirectory() as directory:',
            '    root = Path(directory)',
            '    write_cotahist_zip(',
            '        root, year=2024, records=[build_cotahist_record()]',
            '    )',
            '    HistoricalQuotesB3().extract(',
            '        str(root),',
            "        ['ações'],",
            '        2024, 2024, str(root),',
            "        'result', 'slow', False,",
            '    )',
        )
        + _engine_state()
    )

    assert cvm_state['pandas'] is False
    assert cvm_state['pyarrow'] is True
    assert cvm_state['polars'] is False
    assert b3_state['pandas'] is False
    assert b3_state['pyarrow'] is True
    assert b3_state['polars'] is False
