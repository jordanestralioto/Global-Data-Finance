"""Inspect release distribution contents, version, and reproducible digests."""

from __future__ import annotations

import argparse
import json
import sys
import tarfile
import zipfile
from email.parser import Parser
from pathlib import Path
from typing import Any

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.file_digests import sha256_file

REQUIRED_MODULES = (
    'globaldatafinance/macro_infra/http_safety.py',
    'globaldatafinance/brazil/cvm/fundamental_stocks_data/http_retry.py',
)


def _contents(path: Path) -> tuple[list[str], str]:
    if path.suffix == '.whl':
        with zipfile.ZipFile(path) as archive:
            names = archive.namelist()
            metadata = [
                name for name in names if name.endswith('.dist-info/METADATA')
            ]
            if len(metadata) != 1:
                raise ValueError('wheel requires exactly one METADATA record')
            return names, archive.read(metadata[0]).decode('utf-8')
    with tarfile.open(path, 'r:gz') as archive:
        names = archive.getnames()
        source_metadata = [
            member
            for member in archive.getmembers()
            if member.name.count('/') == 1
            and member.name.endswith('/PKG-INFO')
            and member.isfile()
        ]
        if len(source_metadata) != 1:
            raise ValueError('sdist requires one top-level PKG-INFO record')
        stream = archive.extractfile(source_metadata[0])
        if stream is None:
            raise ValueError('sdist metadata is unreadable')
        with stream:
            return names, stream.read().decode('utf-8')


def inspect_distribution(
    path: Path, expected_version: str | None
) -> dict[str, Any]:
    """Require library metadata and the implemented safety modules."""
    names, text = _contents(path)
    metadata = Parser().parsestr(text)
    if metadata['Name'] != 'globaldatafinance':
        raise ValueError('distribution name does not identify this library')
    version = metadata['Version']
    if not version or (
        expected_version is not None and version != expected_version
    ):
        raise ValueError('distribution version differs from the release tag')
    if set(str(metadata['Requires-Python']).replace(' ', '').split(',')) != {
        '>=3.12',
        '<4.0',
    }:
        raise ValueError('distribution changed the Python compatibility range')
    for module in REQUIRED_MODULES:
        present = (
            module in names
            if path.suffix == '.whl'
            else any(name.endswith('/src/' + module) for name in names)
        )
        if not present:
            raise ValueError(f'distribution omits required module: {module}')
    return {
        'file': path.name,
        'version': version,
        'sha256': sha256_file(path),
        'modules': list(REQUIRED_MODULES),
    }


def inspect_distributions(
    root: Path, expected_version: str | None = None
) -> list[dict[str, Any]]:
    """Require exactly one wheel and one source distribution of one version."""
    wheels, sources = sorted(root.glob('*.whl')), sorted(root.glob('*.tar.gz'))
    if len(wheels) != 1 or len(sources) != 1:
        raise ValueError(
            'release build must contain exactly one wheel and sdist'
        )
    reports = [
        inspect_distribution(path, expected_version)
        for path in wheels + sources
    ]
    if len({report['version'] for report in reports}) != 1:
        raise ValueError('wheel and sdist versions disagree')
    return reports


def main() -> int:
    """Inspect existing builds and optionally retain their artifact digests."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--expected-version')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    try:
        reports = inspect_distributions(args.directory, args.expected_version)
    except (
        OSError,
        ValueError,
        tarfile.TarError,
        zipfile.BadZipFile,
    ) as error:
        sys.stderr.write(f'FAIL [DISTRIBUTIONS]: {error}\n')
        return 1
    text = json.dumps(reports, indent=2) + '\n'
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    sys.stdout.write(text)
    return 0


if __name__ == '__main__':
    sys.exit(main())
