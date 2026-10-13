"""Bounded discovery of official CVM annual archive listings."""

from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from typing import Any

import httpx

from globaldatafinance.brazil.cvm.fundamental_stocks_data.core import (
    DOCUMENT_START_YEARS,
)

from .real_validation_types import ValidationCase

_LISTING_LIMIT = 1024 * 1024


class _ArchiveListing(HTMLParser):
    """Accept exact relative annual filenames and report unknown ZIP links."""

    def __init__(self, document: str) -> None:
        """Bind accepted filenames to one registered document code."""
        super().__init__()
        self.pattern = re.compile(
            rf'{document.lower()}_cia_aberta_(\d{{4}})\.zip'
        )
        self.years: set[int] = set()
        self.unknown_archives: set[str] = set()

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        """Collect ZIP links without trusting their host or path."""
        if tag != 'a':
            return
        href = dict(attrs).get('href')
        if href is None or not href.casefold().endswith('.zip'):
            return
        matched = self.pattern.fullmatch(href)
        if matched is None:
            self.unknown_archives.add(href)
        else:
            self.years.add(int(matched.group(1)))


def verify_catalog(
    cases: list[ValidationCase], timeout: float
) -> dict[str, Any]:
    """Compare official published years with the selected document matrix."""
    cvm_cases = [case for case in cases if case.source == 'cvm']
    if not cvm_cases:
        raise ValueError('CVM catalog verification requires CVM cases')
    selected_years: dict[str, set[int]] = {}
    for case in cvm_cases:
        document = case.document
        if document is None or document not in DOCUMENT_START_YEARS:
            raise ValueError('CVM catalog document is not registered')
        selected_years.setdefault(document, set()).add(case.year)
    documents = sorted(selected_years)
    listings: list[dict[str, Any]] = []
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for document in documents:
            url = (
                'https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/'
                f'{document}/DADOS/'
            )
            payload = _read_listing(client, url)
            parsed = _ArchiveListing(document)
            parsed.feed(payload.decode('utf-8', errors='strict'))
            if not parsed.years or parsed.unknown_archives:
                raise ValueError(
                    f'Unrecognized CVM archive listing for {document}: '
                    f'{sorted(parsed.unknown_archives)}'
                )
            selected = selected_years[document]
            listings.append(
                {
                    'document': document,
                    'url': url,
                    'listingSha256': hashlib.sha256(payload).hexdigest(),
                    'publishedYears': sorted(parsed.years),
                    'selectedYears': sorted(selected),
                    'publishedYearsNotSelected': sorted(
                        parsed.years - selected
                    ),
                    'selectedYearsNotListed': sorted(selected - parsed.years),
                }
            )
    complete = all(
        not listing['publishedYearsNotSelected'] for listing in listings
    )
    return {
        'status': 'passed' if complete else 'failed',
        'publishedArchiveCount': sum(
            len(listing['publishedYears']) for listing in listings
        ),
        'selectedArchiveCount': len(cvm_cases),
        'allPublishedArchivesSelected': complete,
        'documents': listings,
    }


def _read_listing(client: httpx.Client, url: str) -> bytes:
    """Bound official directory responses before accumulating their bytes."""
    chunks: list[bytes] = []
    size = 0
    with client.stream('GET', url) as response:
        response.raise_for_status()
        for chunk in response.iter_bytes(chunk_size=64 * 1024):
            size += len(chunk)
            if size > _LISTING_LIMIT:
                raise ValueError('CVM archive listing exceeds its byte limit')
            chunks.append(chunk)
    return b''.join(chunks)
