"""Public typed contracts for the B3 historical quotes facade."""

from typing import Literal, TypedDict


class B3SourceWarningReport(TypedDict):
    """One stable warning observed during source validation."""

    code: str
    count: int
    explanation: str


class B3IntegrityWarning(B3SourceWarningReport):
    """Associate a warning with its annual source or committed output."""

    source: str


class B3SourceIntegrityReport(TypedDict):
    """Preflight, transformation, and readback evidence for one source."""

    source: str
    year: int
    member: str
    outer_sha256: str
    content_sha256: str
    uncompressed_bytes: int
    market_counts: dict[str, int]
    unknown_market_counts: dict[str, int]
    header_records: int
    trailer_records: int
    generation_date: str
    blank_lines: int
    warnings: list[B3SourceWarningReport]
    raw_quotes: int
    selected_quotes: int
    intentional_exclusions: int
    excluded_records: int
    written_rows: int
    verified_rows: int
    declared_records: int
    trailer_convention: str
    first_trading_date: str
    last_trading_date: str
    header_base64: str
    trailer_base64: str
    expected_rows_sha256: str
    verified_rows_sha256: str | None


class B3IntegrityReport(TypedDict):
    """Auditable facts behind one version 2 extraction result."""

    status: Literal['passed', 'failed', 'not_run']
    schema_version: int
    verification_method: str
    requested_years: list[int]
    selected_years: list[int]
    missing_years: list[int]
    complete_market_selection: bool
    market_codes: list[str]
    asset_classes: list[str]
    raw_quotes: int
    selected_quotes: int
    intentional_exclusions: int
    excluded_records: int
    written_rows: int
    verified_rows: int
    selection_complete: bool
    source_complete: bool
    source_first_trading_date: str | None
    source_last_trading_date: str | None
    output_first_trading_date: str | None
    output_last_trading_date: str | None
    unknown_market_counts: dict[str, int]
    warnings: list[B3IntegrityWarning]
    sources: list[B3SourceIntegrityReport]
    ignored_duplicate_sources: list[str]
    output_sha256: str | None


class ExtractionResultB3(TypedDict):
    """Public shape of the dict returned by ``HistoricalQuotesB3.extract``.

    It is a required-field ``TypedDict`` (not a dataclass) so existing
    ``result['key']`` access keeps working, while consumers gain type checking
    and editor autocomplete on the complete public contract. Every public
    extraction response contains all declared fields, including when no
    matching input file is found.
    """

    success: bool
    message: str
    total_files: int
    success_count: int
    error_count: int
    total_records: int
    output_file: str
    errors: dict[str, str]
    assets: list[str]
    processing_mode: str
    elapsed_time: float
    schema_version: int
    integrity: B3IntegrityReport
