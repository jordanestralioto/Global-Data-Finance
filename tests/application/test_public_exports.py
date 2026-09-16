"""Tests for the package's public exports."""

from __future__ import annotations

import importlib
import runpy
import sys
from pathlib import Path

import pytest

from scripts.process_runner import run_process

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = REPOSITORY_ROOT / 'src'
EXPECTED_ROOT_EXPORTS = [
    'ExtractionResultB3',
    'FundamentalStocksDataCVM',
    'HistoricalQuotesB3',
]
EXPORT_MODULES = (
    'globaldatafinance',
    'globaldatafinance.application',
    'globaldatafinance.application.b3_docs',
    'globaldatafinance.application.b3_docs.result_formatters',
    'globaldatafinance.application.cvm_docs',
    'globaldatafinance.brazil.b3_data.historical_quotes',
    'globaldatafinance.brazil.b3_data.historical_quotes.extraction_service',
    'globaldatafinance.brazil.b3_data.historical_quotes.parquet_writer',
    'globaldatafinance.brazil.cvm.fundamental_stocks_data',
    'globaldatafinance.core',
    'globaldatafinance.core.utils',
    'globaldatafinance.macro_exceptions',
    'globaldatafinance.macro_infra',
)


pytestmark = pytest.mark.unit


def _load_settings_from_directory(
    directory: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[int, bool]:
    saved_modules = {
        name: module
        for name, module in sys.modules.items()
        if name == 'globaldatafinance' or name.startswith('globaldatafinance.')
    }
    saved_path = sys.path.copy()

    try:
        for name in saved_modules:
            del sys.modules[name]
        monkeypatch.chdir(directory)
        sys.path.insert(0, str(SOURCE_ROOT))

        importlib.import_module('globaldatafinance')
        config = importlib.import_module('globaldatafinance.core.config')
        settings = config.Settings()
        return settings.network.timeout, settings.debug
    finally:
        for name in list(sys.modules):
            if name == 'globaldatafinance' or name.startswith(
                'globaldatafinance.'
            ):
                del sys.modules[name]
        sys.modules.update(saved_modules)
        sys.path[:] = saved_path


def _clear_configuration_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        'DATAFINANCE_DEBUG',
        'DATAFINANCE_NETWORK',
        'DATAFINANCE_NETWORK_TIMEOUT',
        'DATAFINANCE_NETWORK_MAX_RETRIES',
        'DATAFINANCE_NETWORK_RETRY_BACKOFF',
        'DATAFINANCE_NETWORK_USER_AGENT',
    ):
        monkeypatch.delenv(name, raising=False)


def test_root_all_and_facade_identities() -> None:
    package = importlib.import_module('globaldatafinance')
    application = importlib.import_module('globaldatafinance.application')

    assert package.__all__ == EXPECTED_ROOT_EXPORTS
    assert package.ExtractionResultB3 is application.ExtractionResultB3
    assert (
        package.FundamentalStocksDataCVM
        is application.FundamentalStocksDataCVM
    )
    assert package.HistoricalQuotesB3 is application.HistoricalQuotesB3


def test_root_import_works_without_dotenv(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _clear_configuration_environment(monkeypatch)

    assert _load_settings_from_directory(tmp_path, monkeypatch) == (180, False)


def test_root_import_ignores_dotenv_in_consumer_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    (tmp_path / '.env').write_text(
        'DATAFINANCE_DEBUG=true\nDATAFINANCE_NETWORK_TIMEOUT=60\n',
        encoding='utf-8',
    )

    _clear_configuration_environment(monkeypatch)

    assert _load_settings_from_directory(tmp_path, monkeypatch) == (180, False)


@pytest.mark.parametrize('module_name', EXPORT_MODULES)
def test_declared_all_names_exist(module_name: str) -> None:
    module = importlib.import_module(module_name)
    exported_names = module.__dict__['__all__']

    assert isinstance(exported_names, list)
    assert all(hasattr(module, name) for name in exported_names)


@pytest.mark.parametrize('module_name', EXPORT_MODULES)
def test_star_import_exposes_only_declared_names(
    module_name: str, tmp_path: Path
) -> None:
    module = importlib.import_module(module_name)
    script_path = tmp_path / 'star_import_check.py'
    script_path.write_text(
        f'from {module_name} import *\n',
        encoding='utf-8',
    )

    namespace = runpy.run_path(str(script_path))

    imported_names = {
        name
        for name in namespace
        if not name.startswith('__') or name in module.__all__
    }
    assert imported_names == set(module.__all__)


def test_removed_singleton_and_accessor_symbols_absent() -> None:
    """Settings and logging singletons/accessors must be completely removed."""
    core = importlib.import_module('globaldatafinance.core')
    config = importlib.import_module('globaldatafinance.core.config')
    logging_config = importlib.import_module(
        'globaldatafinance.core.logging_config'
    )

    assert 'settings' not in core.__all__
    assert 'get_logging_settings' not in core.__all__
    assert not hasattr(core, 'settings')
    assert not hasattr(core, 'get_logging_settings')
    assert not hasattr(core, 'Settings')
    assert not hasattr(core, 'LoggingSettings')

    assert not hasattr(config, '__all__')
    assert not hasattr(config, 'settings')

    assert not hasattr(logging_config, '__all__')
    assert not hasattr(logging_config, 'get_logging_settings')


def test_root_import_succeeds_in_fresh_process_with_invalid_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Root package import succeeds even with malformed settings in env."""
    monkeypatch.setenv('DATAFINANCE_NETWORK_TIMEOUT', 'invalid-int')
    monkeypatch.setenv('DATAFINANCE_ARCHIVE_MAX_MEMBERS', '-999')
    monkeypatch.setenv('DATAFINANCE_PATH_SAFETY_ALLOWED_UNC_ROOTS', 'bad-json')
    monkeypatch.setenv('DATAFIN_LOG_LEVEL', 'INVALID_LEVEL')

    import_cmd = (
        'import sys; '
        'sys.path.insert(0, "src"); '
        'import globaldatafinance as gdf; '
        'from globaldatafinance import '
        'FundamentalStocksDataCVM, HistoricalQuotesB3'
    )
    result = run_process(
        ['python', '-c', import_cmd],
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    assert result.returncode == 0, result.stderr

    settings_cmd = (
        'import sys; '
        'sys.path.insert(0, "src"); '
        'from globaldatafinance.core.config import Settings; '
        'Settings()'
    )
    result_settings = run_process(
        ['python', '-c', settings_cmd],
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    assert result_settings.returncode != 0

    cvm_cmd = (
        'import sys; '
        'sys.path.insert(0, "src"); '
        'from globaldatafinance import FundamentalStocksDataCVM; '
        'FundamentalStocksDataCVM()'
    )
    result_cvm = run_process(
        ['python', '-c', cvm_cmd],
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    assert result_cvm.returncode != 0

    b3_cmd = (
        'import sys; '
        'sys.path.insert(0, "src"); '
        'from globaldatafinance import HistoricalQuotesB3; '
        'HistoricalQuotesB3()'
    )
    result_b3 = run_process(
        ['python', '-c', b3_cmd],
        cwd=REPOSITORY_ROOT,
        check=False,
    )
    assert result_b3.returncode != 0
