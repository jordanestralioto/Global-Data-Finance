"""Unit checks for the opt-in live CVM benchmark command."""

from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import benchmark_cvm_full

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('errors', [0, 1])
def test_full_benchmark_returns_download_status(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    errors: int,
) -> None:
    observed: dict[str, object] = {}

    class FakeClient:
        def download(self, **kwargs: object) -> SimpleNamespace:
            observed.update(kwargs)
            return SimpleNamespace(
                success_count_downloads=1,
                error_count_downloads=errors,
                failed_downloads={'DFP_2024': 'failed'} if errors else {},
            )

    monkeypatch.setattr(
        benchmark_cvm_full, 'FundamentalStocksDataCVM', FakeClient
    )

    assert benchmark_cvm_full.main(tmp_path) == (1 if errors else 0)
    assert observed['destination_path'] == str(tmp_path)
    assert observed['automatic_extractor'] is True


def test_full_benchmark_rejects_nonempty_destination(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / 'existing.txt').write_text('keep', encoding='utf-8')
    monkeypatch.setattr(
        benchmark_cvm_full,
        'FundamentalStocksDataCVM',
        lambda: pytest.fail('download must not start'),
    )

    assert benchmark_cvm_full.main(tmp_path) == 2
