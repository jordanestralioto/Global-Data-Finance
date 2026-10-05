"""Reconcile raw COTAHIST sources with extracted Parquet rows."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pyarrow.parquet as pq

from scripts.cotahist_oracle.errors import OracleMismatch
from scripts.cotahist_oracle.manifest_validation import (
    validate_expected_checksums,
    validate_manifest_counts,
    validate_public_result,
)
from scripts.cotahist_oracle.parquet_reader import (
    iter_parquet_rows,
    open_oracle_parquet,
)
from scripts.cotahist_oracle.row_decoder import decode_quote
from scripts.cotahist_oracle.row_digest import update_rows_digest
from scripts.cotahist_oracle.schema import COLUMN_NAMES, OLD_COLUMNS
from scripts.cotahist_oracle.source_reader import (
    SourceFacts,
    inspect_source,
    iter_bounded_lines,
    sha256_file,
    source_sort_key,
    split_line_terminator,
    validate_header,
    validate_trailer,
)

PREVIOUS_MARKETS = frozenset(
    {'010', '020', '070', '080', '030', '012', '013', '050', '060', '017'}
)
KNOWN_MARKETS = PREVIOUS_MARKETS | {'021'}


@dataclass
class _ReconciliationTotals:
    total_rows: int = 0
    previous_count: int = 0
    previous_source_digest: Any = field(default_factory=hashlib.sha256)
    previous_output_digest: Any = field(default_factory=hashlib.sha256)
    markets: Counter[str] = field(default_factory=Counter)
    unknown_markets: Counter[str] = field(default_factory=Counter)
    block_rows_by_year: Counter[int] = field(default_factory=Counter)
    block_tickers: set[str] = field(default_factory=set)
    block_volume_cents: int = 0
    first_date: date | None = None
    last_date: date | None = None


def reconcile_sources(
    source_paths: Sequence[Path],
    output_path: Path,
    *,
    public_result: dict[str, Any] | None = None,
    expected_checksums: dict[str, str] | None = None,
    batch_size: int = 8_192,
) -> dict[str, Any]:
    """Compare every source quotation with one complete ordered Parquet.

    The oracle owns its offsets and conversions. It does not import the
    production layout, parser, schema builder, or market-class mapping.
    """
    source_facts = _prepare_source_facts(
        source_paths, expected_checksums, batch_size
    )
    parquet, manifest = open_oracle_parquet(output_path, source_facts)
    totals = _reconcile_source_facts(source_facts, parquet, batch_size)
    _validate_reconciled_output(
        parquet, manifest, source_facts, totals.total_rows
    )
    if public_result is not None:
        validate_public_result(public_result, source_facts, totals.total_rows)
    return _reconciliation_report(output_path, source_facts, totals)


def _prepare_source_facts(
    source_paths: Sequence[Path],
    expected_checksums: dict[str, str] | None,
    batch_size: int,
) -> list[SourceFacts]:
    if batch_size <= 0:
        raise ValueError('batch_size must be positive')
    ordered_paths = tuple(sorted(source_paths, key=source_sort_key))
    if not ordered_paths:
        raise ValueError('at least one COTAHIST source is required')
    source_facts = [inspect_source(path) for path in ordered_paths]
    if expected_checksums is not None:
        validate_expected_checksums(source_facts, expected_checksums)
    return source_facts


def _reconcile_source_facts(
    source_facts: Sequence[SourceFacts],
    parquet: pq.ParquetFile,
    batch_size: int,
) -> _ReconciliationTotals:
    totals = _ReconciliationTotals()
    output_rows = iter_parquet_rows(parquet, batch_size)
    for fact in source_facts:
        _reconcile_source(fact, output_rows, totals)
        _validate_source_fact(fact)
    if next(output_rows, None) is not None:
        raise OracleMismatch('Parquet contains extra quotation rows')
    return totals


def _reconcile_source(
    fact: SourceFacts,
    output_rows: Iterator[dict[str, Any]],
    totals: _ReconciliationTotals,
) -> None:
    for line_number, raw_line in iter_bounded_lines(fact.path, fact.member):
        content, _terminator = split_line_terminator(raw_line)
        if not content:
            fact.blank_lines += 1
            continue
        if len(content) != 245:
            raise OracleMismatch(
                f'{fact.path.name}: line {line_number} has '
                f'{len(content)} bytes, expected 245'
            )
        _consume_source_line(fact, content, line_number, output_rows, totals)


def _consume_source_line(
    fact: SourceFacts,
    content: bytes,
    line_number: int,
    output_rows: Iterator[dict[str, Any]],
    totals: _ReconciliationTotals,
) -> None:
    record_type = content[:2]
    if record_type == b'00':
        fact.generation_date = validate_header(content, fact, line_number)
        fact.header = content
        return
    if record_type == b'99':
        validate_trailer(content, fact, line_number)
        fact.trailer = content
        return
    if record_type != b'01':
        raise OracleMismatch(
            f'{fact.path.name}: line {line_number} has unsupported '
            f'record type {record_type!r}'
        )
    if fact.header is None or fact.trailer is not None:
        raise OracleMismatch(
            f'{fact.path.name}: quotation at line {line_number} is '
            'outside the header/trailer boundary'
        )
    _reconcile_quote(fact, content, line_number, output_rows, totals)


def _reconcile_quote(
    fact: SourceFacts,
    content: bytes,
    line_number: int,
    output_rows: Iterator[dict[str, Any]],
    totals: _ReconciliationTotals,
) -> None:
    expected = decode_quote(
        content,
        source_name=fact.path.name,
        member=fact.member,
        year=fact.year,
        line_number=line_number,
        content_sha256=fact.content_sha256,
    )
    observed = next(output_rows, None)
    if observed is None:
        raise OracleMismatch(
            f'{fact.path.name}: output ended before source line {line_number}'
        )
    _compare_row(fact.path.name, line_number, expected, observed)
    fact.quote_count += 1
    _accumulate_quote(fact, expected, observed, totals)


def _accumulate_quote(
    fact: SourceFacts,
    expected: dict[str, Any],
    observed: dict[str, Any],
    totals: _ReconciliationTotals,
) -> None:
    market = cast(str, expected['tipo_mercado'])
    update_rows_digest(fact.rows_digest, expected)
    fact.market_counts[market] = fact.market_counts.get(market, 0) + 1
    totals.markets[market] += 1
    if market not in KNOWN_MARKETS:
        fact.unknown_market_counts[market] = (
            fact.unknown_market_counts.get(market, 0) + 1
        )
        totals.unknown_markets[market] += 1
    trading_date = cast(date, expected['data_pregao'])
    fact.first_date = _min_date(fact.first_date, trading_date)
    fact.last_date = _max_date(fact.last_date, trading_date)
    totals.first_date = _min_date(totals.first_date, trading_date)
    totals.last_date = _max_date(totals.last_date, trading_date)
    if market == '021':
        totals.block_rows_by_year[fact.year] += 1
        totals.block_tickers.add(cast(str, expected['ticker']))
        volume = cast(Decimal, expected['volume_total'])
        totals.block_volume_cents += int(
            format(volume, '.2f').replace('.', '')
        )
    if market in PREVIOUS_MARKETS:
        totals.previous_count += 1
        _update_old_digest(totals.previous_source_digest, expected)
        _update_old_digest(totals.previous_output_digest, observed)
    totals.total_rows += 1


def _min_date(current: date | None, candidate: date) -> date:
    return candidate if current is None else min(current, candidate)


def _max_date(current: date | None, candidate: date) -> date:
    return candidate if current is None else max(current, candidate)


def _validate_source_fact(fact: SourceFacts) -> None:
    if fact.header is None or fact.trailer is None or fact.quote_count == 0:
        raise OracleMismatch(
            f'{fact.path.name}: expected one header, at least one quote, '
            'and one trailer'
        )
    if fact.declared_count not in {fact.quote_count, fact.quote_count + 2}:
        raise OracleMismatch(
            f'{fact.path.name}: unsupported trailer count '
            f'{fact.declared_count} for {fact.quote_count} quotations'
        )
    fact.trailer_convention = (
        'quotes_only'
        if fact.declared_count == fact.quote_count
        else 'quotes_and_controls'
    )


def _validate_reconciled_output(
    parquet: pq.ParquetFile,
    manifest: dict[str, Any],
    source_facts: Sequence[SourceFacts],
    total_rows: int,
) -> None:
    if parquet.metadata is None or parquet.metadata.num_rows != total_rows:
        raise OracleMismatch(
            'Parquet footer row count differs from raw sources'
        )
    validate_manifest_counts(manifest, source_facts, total_rows)


def _reconciliation_report(
    output_path: Path,
    source_facts: Sequence[SourceFacts],
    totals: _ReconciliationTotals,
) -> dict[str, Any]:
    return {
        'sourceCount': len(source_facts),
        'rawQuotes': totals.total_rows,
        'selectedQuotes': totals.total_rows,
        'intentionalExclusions': 0,
        'verifiedRows': totals.total_rows,
        'missingYears': [],
        'firstTradingDate': (
            totals.first_date.isoformat() if totals.first_date else None
        ),
        'lastTradingDate': (
            totals.last_date.isoformat() if totals.last_date else None
        ),
        'marketCounts': dict(sorted(totals.markets.items())),
        'unknownMarketCounts': dict(sorted(totals.unknown_markets.items())),
        'sourceChecksums': [
            {
                'source': fact.path.name,
                'outerSha256': fact.outer_sha256,
                'contentSha256': fact.content_sha256,
            }
            for fact in source_facts
        ],
        'trailerConventions': {
            fact.path.name: fact.trailer_convention for fact in source_facts
        },
        'blankLines': {
            fact.path.name: fact.blank_lines for fact in source_facts
        },
        'previousSupportedRows': totals.previous_count,
        'previousTwentyFieldsEqual': (
            totals.previous_source_digest.digest()
            == totals.previous_output_digest.digest()
        ),
        'previousTwentySourceSha256': (
            totals.previous_source_digest.hexdigest()
        ),
        'previousTwentyOutputSha256': (
            totals.previous_output_digest.hexdigest()
        ),
        'blockLotRowsByYear': dict(sorted(totals.block_rows_by_year.items())),
        'blockLotDistinctTradingCodes': len(totals.block_tickers),
        'blockLotVolumeTotal': (
            f'{totals.block_volume_cents // 100}.'
            f'{totals.block_volume_cents % 100:02d}'
        ),
        'outputSha256': sha256_file(output_path),
        'schemaVersion': 2,
    }


def _compare_row(
    source_name: str,
    line_number: int,
    expected: dict[str, Any],
    observed: dict[str, Any],
) -> None:
    for name in COLUMN_NAMES:
        if observed.get(name) != expected[name]:
            raise OracleMismatch(
                f'{source_name}: line {line_number} field {name} differs: '
                f'expected={expected[name]!r}; observed={observed.get(name)!r}'
            )


def _update_old_digest(digest: Any, row: dict[str, Any]) -> None:
    payload = json.dumps(
        [row[name] for name in OLD_COLUMNS],
        default=str,
        ensure_ascii=True,
        separators=(',', ':'),
    ).encode('utf-8')
    digest.update(len(payload).to_bytes(8, 'big'))
    digest.update(payload)
