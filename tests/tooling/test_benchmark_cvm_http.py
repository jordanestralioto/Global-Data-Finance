"""Tests for deterministic CVM HTTP benchmark fixtures and aggregation."""

import io
import zipfile

import pytest

from scripts import benchmark_cvm_http_support

pytestmark = pytest.mark.unit


def test_local_fixture_is_reproducible_and_contains_expected_csv() -> None:
    first_archive, first_csv, first_rows = (
        benchmark_cvm_http_support.build_fixture(1)
    )
    second_archive, second_csv, second_rows = (
        benchmark_cvm_http_support.build_fixture(1)
    )

    assert first_archive == second_archive
    assert first_csv == second_csv
    assert first_rows == second_rows == benchmark_cvm_http_support.DEFAULT_ROWS
    with zipfile.ZipFile(io.BytesIO(first_archive)) as archive:
        assert archive.namelist() == ['payload.bin', 'filings.csv']
        assert all(
            member.date_time == (2020, 1, 1, 0, 0, 0)
            for member in archive.infolist()
        )
        assert archive.read('filings.csv') == first_csv


def test_stage_metrics_keep_transferred_and_processed_bytes_separate() -> None:
    measurements = benchmark_cvm_http_support.PhaseMeasurements()

    measurements.add_phase('get', 0.25, transferred_bytes=120)
    measurements.add_phase('validation', 0.1, processed_bytes=120)
    measurements.add_phase('extraction', 0.2, processed_bytes=40)

    phases = measurements.snapshot()['phases']
    assert phases['get']['transferred_bytes'] == 120
    assert phases['get']['operations'] == 1
    assert phases['head']['transferred_bytes'] == 0
    assert phases['head']['announced_bytes'] == 0
    assert phases['head']['operations'] == 0
    assert phases['head']['seconds'] == 0.0
    assert phases['validation']['processed_bytes'] == 120
    assert phases['extraction']['processed_bytes'] == 40
