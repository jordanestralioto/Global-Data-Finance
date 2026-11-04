from __future__ import annotations

import importlib

import pytest

import globaldatafinance.macro_infra as macro_infra

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    'module_name',
    [
        'globaldatafinance.macro_infra.extractor_file',
        'globaldatafinance.macro_infra.read_files',
    ],
)
def test_removed_generic_adapter_modules_fail_to_import(
    module_name: str,
) -> None:
    """The breaking cut does not leave importable compatibility shims."""
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(module_name)


def test_macro_infra_exports_only_the_active_http_adapter() -> None:
    """The package boundary exposes no replacement legacy adapters."""
    assert macro_infra.__all__ == ['RequestsAdapter']
    assert not hasattr(macro_infra, 'ExtractorAdapter')
    assert not hasattr(macro_infra, 'ReadFilesAdapter')
