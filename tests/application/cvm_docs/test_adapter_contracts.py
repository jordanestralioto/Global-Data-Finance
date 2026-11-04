"""Canonical ingestion contracts and the company adapter clean cutover."""

import importlib.util
import inspect
from typing import get_type_hints

import pytest

from globaldatafinance import FundamentalStocksDataCVM
from globaldatafinance.brazil.cvm import fundamental_stocks_data
from globaldatafinance.brazil.cvm.fundamental_stocks_data import core
from globaldatafinance.brazil.cvm.ingestion.extract import CvmParquetExtractor
from globaldatafinance.brazil.cvm.ingestion.http import (
    CvmDownloadAdapter,
    DownloadTaskCVM,
)
from globaldatafinance.brazil.cvm.ingestion.models import DownloadResultCVM

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    ('surface', 'expected'),
    [
        (
            CvmDownloadAdapter.__init__,
            '(self, file_extractor_repository, max_concurrent=10, '
            'chunk_size=8192, timeout=180.0, max_retries=5, '
            'initial_backoff=1.0, max_backoff=120.0, '
            'backoff_multiplier=2.0, http2=True, automatic_extractor=False, '
            'user_agent=None, follow_redirects=True, archive_limits=None, '
            'allowed_unc_roots=None)',
        ),
        (
            CvmDownloadAdapter.download_docs,
            '(self, tasks, *, automatic_extractor=None)',
        ),
        (
            CvmDownloadAdapter.async_download_docs,
            '(self, tasks, *, automatic_extractor=None)',
        ),
        (
            CvmParquetExtractor.__init__,
            '(self, *, archive_limits=None, allowed_unc_roots=None)',
        ),
        (
            CvmParquetExtractor.extract,
            '(self, source_path, destination_path)',
        ),
    ],
)
def test_adapter_argument_kinds_and_defaults_match_baseline(
    surface, expected: str
) -> None:
    signature = inspect.signature(surface)
    unannotated = signature.replace(
        parameters=[
            parameter.replace(annotation=inspect.Parameter.empty)
            for parameter in signature.parameters.values()
        ],
        return_annotation=inspect.Signature.empty,
    )

    assert str(unannotated) == expected


def test_facades_and_ingestion_use_the_canonical_result_class() -> None:
    assert (
        DownloadResultCVM.__module__
        == 'globaldatafinance.brazil.cvm.ingestion.models'
    )
    assert not hasattr(fundamental_stocks_data, 'DownloadResultCVM')
    assert not hasattr(core, 'DownloadResultCVM')
    assert DownloadTaskCVM == tuple[str, str, str, str]
    for surface in (
        FundamentalStocksDataCVM.download,
        FundamentalStocksDataCVM.async_download,
        CvmDownloadAdapter.download_docs,
        CvmDownloadAdapter.async_download_docs,
    ):
        assert get_type_hints(surface)['return'] is DownloadResultCVM


@pytest.mark.parametrize('module', ['http', 'extract'])
def test_removed_company_adapter_modules_are_absent(module: str) -> None:
    name = f'{fundamental_stocks_data.__name__}.{module}'
    assert importlib.util.find_spec(name) is None


def test_company_facade_composes_shared_ingestion_directly() -> None:
    facade = FundamentalStocksDataCVM()

    assert type(facade.download_adapter) is CvmDownloadAdapter
    assert facade.download_adapter.file_extractor_repository is None
    assert not hasattr(fundamental_stocks_data, 'AsyncDownloadAdapterCVM')
    assert not hasattr(fundamental_stocks_data, 'ParquetExtractorAdapterCVM')
