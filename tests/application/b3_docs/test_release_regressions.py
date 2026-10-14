"""Public B3 regressions found during release acceptance."""

import asyncio
import json
import threading
import zipfile
from pathlib import Path
from typing import Any

import pytest

from globaldatafinance import HistoricalQuotesB3
from globaldatafinance.core import archive_safety
from globaldatafinance.macro_infra.transactional_publication.types import (
    MANIFEST_PREFIX,
)
from tests.support.builders import (
    build_cotahist_record,
    write_cotahist_txt,
    write_cotahist_zip,
)

pytestmark = pytest.mark.integration


@pytest.mark.parametrize('mode', ['fast', 'slow'])
@pytest.mark.parametrize('phase', ['OPEN', 'PUBLISHING'])
def test_forged_recovery_preserves_caller_sources_and_directories(
    tmp_path: Path, mode: str, phase: str
) -> None:
    """A discovery record cannot grant ownership of caller files."""
    source = write_cotahist_txt(
        tmp_path, year=2024, records=[build_cotahist_record()]
    )
    before = source.read_bytes()
    caller_directory = tmp_path / 'caller-data'
    caller_directory.mkdir()
    unrelated = caller_directory / 'keep.txt'
    unrelated.write_bytes(b'caller-owned data')
    transaction_id = 'a' * 32
    manifest_path = tmp_path / f'{MANIFEST_PREFIX}{transaction_id}.json'
    manifest_path.write_text(
        json.dumps(
            {
                'version': 1,
                'transaction_id': transaction_id,
                'owner': 'b3',
                'destination_dir': '.',
                'staging_dir': caller_directory.name,
                'created_at': '2026-10-14T00:00:00+00:00',
                'phase': phase,
                'source_descriptors': [{'source': source.name}],
                'artifacts': [
                    {
                        'final_path': source.name,
                        'staged_path': 'caller-data/missing.parquet',
                        'backup_path': None,
                        'expected_rows': 1,
                        'schema_fingerprint': 'schema-v2',
                        'existed_before': False,
                        'publishing': True,
                        'published': False,
                    }
                ],
            }
        ),
        encoding='utf-8',
    )
    manifest_path.chmod(0o600)

    result = HistoricalQuotesB3().extract(
        path_of_docs=str(tmp_path),
        initial_year=2024,
        last_year=2024,
        processing_mode=mode,
        verbose=False,
    )

    assert source.exists(), 'Recovery deleted an approved COTAHIST source'
    assert source.read_bytes() == before
    assert unrelated.read_bytes() == b'caller-owned data'
    assert result['success'] is False
    assert result['output_file'] == ''
    assert manifest_path.exists()
    assert not (tmp_path / 'cotahist_extracted.parquet').exists()


def test_preflight_failure_clears_previous_request_timings(
    tmp_path: Path,
) -> None:
    """Failed input validation exposes no telemetry from an earlier call."""
    source = write_cotahist_txt(
        tmp_path, year=2024, records=[build_cotahist_record()]
    )
    facade = HistoricalQuotesB3()
    options: dict[str, Any] = {
        'path_of_docs': str(tmp_path),
        'initial_year': 2024,
        'last_year': 2024,
        'verbose': False,
    }
    result = facade.extract(**options)
    assert result['success'] is True
    assert facade.last_phase_timings['source_wall_seconds'] > 0
    source.write_bytes(b'invalid COTAHIST bytes\n')

    failed = facade.extract(**options)

    assert failed['success'] is False
    assert facade.last_phase_timings == {}


@pytest.mark.asyncio
async def test_cancellation_stops_preflight_crc_at_next_bounded_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A cancelled request closes its ZIP after the in-progress CRC block."""
    source = write_cotahist_zip(
        tmp_path,
        year=2024,
        records=[build_cotahist_record()] * 4_096,
        compression=zipfile.ZIP_STORED,
    )
    before = source.read_bytes()
    loop = asyncio.get_running_loop()
    started = asyncio.Event()
    release = threading.Event()
    reads = []
    readinto = archive_safety._LimitedZipMemberStream.readinto

    def block_first_crc_read(self, buffer):
        count = readinto(self, buffer)
        reads.append(count)
        if len(reads) == 1:
            loop.call_soon_threadsafe(started.set)
            assert release.wait(timeout=5)
        return count

    monkeypatch.setattr(
        archive_safety._LimitedZipMemberStream,
        'readinto',
        block_first_crc_read,
    )
    task = asyncio.create_task(
        HistoricalQuotesB3().extract_async(
            path_of_docs=str(tmp_path),
            initial_year=2024,
            last_year=2024,
            verbose=False,
        )
    )
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        task.cancel()
        await asyncio.sleep(0)
        assert not task.done()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=5)

    assert len(reads) == 1
    assert 0 < reads[0] <= 64 * 1024
    assert source.read_bytes() == before
    assert list(tmp_path.iterdir()) == [source]
    assert not any(
        thread.name.startswith('gdf-b3-phase')
        for thread in threading.enumerate()
    )
