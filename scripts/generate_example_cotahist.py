"""Generate the small synthetic COTAHIST archives bundled with the examples."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from tempfile import TemporaryDirectory

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.benchmark_corpus.containers import select_b3_container
from tests.support.builders import build_cotahist_record, write_cotahist_txt

SAMPLES_DIRECTORY = Path(__file__).resolve().parents[1] / 'cotahist_b3'
SAMPLE_YEARS = (2022, 2023)
SAMPLE_QUOTES = (
    ('PETR4', '010'),
    ('BOVA11', '010'),
    ('PETR4F', '020'),
    ('PETRA1', '070'),
    ('PETRM1', '080'),
    ('PETR4T', '030'),
)


def build_samples() -> dict[str, bytes]:
    """Build valid synthetic documents with fixed ZIP member timestamps."""
    archives = {}
    with TemporaryDirectory(prefix='gdf-example-cotahist-') as temporary:
        for year in SAMPLE_YEARS:
            source = write_cotahist_txt(
                Path(temporary),
                year=year,
                records=[
                    build_cotahist_record(
                        year=year, ticker=ticker, market=market
                    )
                    for ticker, market in SAMPLE_QUOTES
                ],
            )
            archive = select_b3_container(source, 'zip')
            archives[archive.name] = archive.read_bytes()
    return archives


def check_samples(directory: Path) -> tuple[str, ...]:
    """Report missing or changed generated archives without writing them."""
    return tuple(
        name
        for name, expected in build_samples().items()
        if not (directory / name).is_file()
        or (directory / name).read_bytes() != expected
    )


def write_samples(directory: Path) -> None:
    """Replace only the two reserved synthetic example ZIPs."""
    archives = build_samples()
    directory.mkdir(parents=True, exist_ok=True)
    for name, content in archives.items():
        (directory / name).write_bytes(content)


def main(argv: Sequence[str] | None = None) -> int:
    """Regenerate the bundled inputs or verify their canonical contents."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        '--check', action='store_true', help='Check samples without writing'
    )
    args = parser.parse_args(argv)
    if args.check:
        mismatches = check_samples(SAMPLES_DIRECTORY)
        if mismatches:
            sys.stderr.write(
                'Missing or changed COTAHIST samples: '
                + ', '.join(mismatches)
                + '\n'
            )
            return 1
        sys.stdout.write('Bundled COTAHIST samples match the generator.\n')
        return 0
    write_samples(SAMPLES_DIRECTORY)
    sys.stdout.write(f'Generated synthetic samples in {SAMPLES_DIRECTORY}\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
