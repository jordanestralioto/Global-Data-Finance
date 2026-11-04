import importlib

import pytest

import globaldatafinance.brazil as brazil_ns

pytestmark = pytest.mark.unit


def test_brazil_namespace_does_not_expose_application_facades() -> None:
    assert not hasattr(brazil_ns, 'FundamentalStocksDataCVM')
    assert not hasattr(brazil_ns, 'HistoricalQuotesB3')
    assert not hasattr(brazil_ns, '__all__')


def test_brazil_namespace_rejects_facade_imports() -> None:
    with pytest.raises(ModuleNotFoundError):
        importlib.import_module(
            'globaldatafinance.brazil.FundamentalStocksDataCVM'
        )


def test_brazil_namespace_raises_attribute_error_for_unknown_attribute() -> (
    None
):
    unknown_attribute = 'NonExistentService'
    with pytest.raises(AttributeError) as exc_info:
        getattr(brazil_ns, unknown_attribute)

    assert (
        "module 'globaldatafinance.brazil' has no attribute "
        "'NonExistentService'" in str(exc_info.value)
    )
