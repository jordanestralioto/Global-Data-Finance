"""Annual COTAHIST corpus discovery and typed expectations."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from scripts.benchmark_support.digests import logical_digest
from scripts.benchmark_support.models import ScenarioInput

_ANNUAL_B3_YEARS = tuple(range(2000, 2027))


def annual_b3_assets() -> list[str]:
    """Return every supported asset class for the annual B3 benchmark."""
    from globaldatafinance.brazil.b3_data.historical_quotes.assets import (
        AvailableAssetsServiceB3,
    )

    return AvailableAssetsServiceB3.get_available_assets()


def b3_extraction_selection(
    source: ScenarioInput,
) -> tuple[int, int, list[str]]:
    """Return the year range and asset scope for a B3 benchmark scenario."""
    if source.scenario == 'b3_annual':
        return 2000, 2026, annual_b3_assets()
    if source.scenario == 'b3_multi_4x25k':
        return 2021, 2020 + source.source_count, ['ações']
    return 2024, 2024, ['ações']


def annual_corpus_available(path: Path | None) -> bool:
    """Require the complete 27-ZIP annual corpus before timing it."""
    if path is None or not path.is_dir():
        return False
    return len(_annual_b3_source_paths(path)) == len(_ANNUAL_B3_YEARS)


def expected_b3_annual_digest(path: Path) -> str:
    """Build the full typed expectation from the annual source corpus."""
    sources = _annual_b3_source_paths(path)
    if len(sources) != len(_ANNUAL_B3_YEARS):
        raise ValueError(
            f'B3 annual benchmark requires all {len(_ANNUAL_B3_YEARS)} '
            'official ZIP files'
        )
    return logical_digest(_annual_b3_rows(sources))


def _annual_b3_source_paths(path: Path) -> tuple[Path, ...]:
    """Return canonical annual ZIP paths in the same order as extraction."""
    paths_by_name = {
        item.name.casefold(): item for item in path.iterdir() if item.is_file()
    }
    return tuple(
        paths_by_name[f'cotahist_a{year}.zip']
        for year in _ANNUAL_B3_YEARS
        if f'cotahist_a{year}.zip' in paths_by_name
    )


def _annual_b3_rows(paths: tuple[Path, ...]) -> Iterator[dict[str, Any]]:
    """Yield canonical typed equity rows directly from official annual ZIPs."""
    from globaldatafinance.brazil.b3_data.historical_quotes import (
        assets,
        cotahist_parser,
        zip_reader,
    )

    target_tpmerc_codes = (
        assets.AvailableAssetsServiceB3.get_tpmerc_codes_for_assets(
            set(annual_b3_assets())
        )
    )
    parser = cotahist_parser.CotahistParserB3()
    reader = zip_reader.ZipFileReaderB3()
    for path in paths:
        for line, context in reader.iter_lines(str(path)):
            if record := parser.parse_line(line, target_tpmerc_codes, context):
                source_hash = record['id_fonte']
                if not isinstance(source_hash, str):
                    raise TypeError('B3 parser source hash must be text')
                record['id_fonte'] = bytes.fromhex(source_hash)
                yield record
