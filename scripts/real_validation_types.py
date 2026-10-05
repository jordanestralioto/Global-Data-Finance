"""Typed values shared by the opt-in real-validation campaign."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal

CaseStatus = Literal[
    'passed',
    'failed',
    'skipped',
    'external_failure',
    'not_published',
]
ValidationMode = Literal['fast', 'parity', 'multi_parity', 'cvm']


@dataclass(frozen=True)
class ValidationInputSnapshot:
    """One caller-owned source file frozen into a campaign manifest."""

    path: str
    size_bytes: int
    sha256: str

    def to_manifest_dict(self) -> dict[str, object]:
        """Serialize a source identity with stable manifest field names."""
        return {
            'path': self.path,
            'sizeBytes': self.size_bytes,
            'sha256': self.sha256,
        }


class ExternalFailure(RuntimeError):
    """Indicate that a case could not be evaluated at its external boundary."""


class NotPublished(RuntimeError):
    """Indicate that the official CVM endpoint has no published archive."""


@dataclass(frozen=True)
class ValidationCase:
    """One isolated source/year or source/document/year execution."""

    case_id: str
    source: Literal['cotahist', 'cvm']
    year: int
    input_path: str
    output_root: str
    document: str | None = None
    mode: ValidationMode = 'cvm'
    url: str | None = None
    input_size_bytes: int | None = None
    input_sha256: str | None = None
    initial_year: int | None = None
    last_year: int | None = None
    input_files: tuple[ValidationInputSnapshot, ...] = ()
    frozen_baseline: bool = False

    def to_manifest_dict(self) -> dict[str, object]:
        """Serialize the case with stable keys and no runtime state."""
        return {
            'caseId': self.case_id,
            'source': self.source,
            'document': self.document,
            'year': self.year,
            'inputPath': self.input_path,
            'outputRoot': self.output_root,
            'mode': self.mode,
            'url': self.url,
            'inputSizeBytes': self.input_size_bytes,
            'inputSha256': self.input_sha256,
            'initialYear': self.initial_year,
            'lastYear': self.last_year,
            'inputFiles': [
                item.to_manifest_dict() for item in self.input_files
            ],
            'frozenBaseline': self.frozen_baseline,
        }

    def command(self) -> list[str]:
        """Return the public operation represented by this case."""
        if self.source == 'cotahist':
            first_year = self.initial_year or self.year
            last_year = self.last_year or self.year
            processing_mode = (
                'fast+slow'
                if self.mode in {'parity', 'multi_parity'}
                else self.mode
            )
            command = [
                'HistoricalQuotesB3.extract_async',
                f'path_of_docs={Path(self.input_path).parent}',
                'assets_list=[todos]',
                f'initial_year={first_year}',
                f'last_year={last_year}',
                f'processing_mode={processing_mode}',
                'independent_raw_reconciliation=True',
                'automatic_network_access=False',
            ]
            if self.frozen_baseline:
                command.append('historical_frozen_baseline=True')
            return command
        return [
            'FundamentalStocksDataCVM.download',
            f'destination_path={self.output_root}',
            f'list_docs=[{self.document}]',
            f'initial_year={self.year}',
            f'last_year={self.year}',
            'automatic_extractor=True',
        ]
