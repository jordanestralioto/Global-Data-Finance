"""Every B3 extraction outcome matches its published TypedDict contract."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from types import NoneType, UnionType
from typing import (
    Any,
    Literal,
    NamedTuple,
    NoReturn,
    TypedDict,
    Union,
    get_args,
    get_origin,
    get_type_hints,
    is_typeddict,
)

import pytest

from globaldatafinance import ExtractionResultB3, HistoricalQuotesB3
from globaldatafinance.brazil.b3_data.historical_quotes import (
    extraction_service,
)
from globaldatafinance.macro_infra.transactional_publication import (
    FileOperations,
)
from tests.support.builders import (
    build_cotahist_record,
    write_cotahist_txt,
    write_cotahist_zip,
)

OUTPUT_FILENAME = 'contract.parquet'
NUMERIC_TYPES: dict[type, tuple[type, ...]] = {
    int: (int,),
    float: (int, float),
}


def contract_violations(value: object, hint: Any, path: str) -> list[str]:
    """Describe every difference between a value and a type annotation."""
    if is_typeddict(hint):
        return _typed_dict_violations(value, hint, path)
    origin = get_origin(hint)
    if origin is Literal:
        options = get_args(hint)
        if value in options:
            return []
        return [f'{path}: {value!r} is not one of {options}']
    if origin is Union or origin is UnionType:
        return _union_violations(value, hint, path)
    if origin is list:
        return _list_violations(value, get_args(hint)[0], path)
    if origin is dict:
        return _dict_violations(value, get_args(hint), path)
    if origin is not None:
        return [f'{path}: extend the checker for annotation {hint!r}']
    return _scalar_violations(value, hint, path)


def _typed_dict_violations(
    value: object, contract: Any, path: str
) -> list[str]:
    if not isinstance(value, dict):
        return [f'{path}: expected mapping, got {type(value).__name__}']
    fields = get_type_hints(contract)
    violations = [
        f'{path}: missing key {key!r}'
        for key in sorted(contract.__required_keys__ - value.keys())
    ]
    violations.extend(
        f'{path}: undeclared key {key!r}'
        for key in sorted(value.keys() - fields.keys())
    )
    for key in sorted(fields.keys() & value.keys()):
        violations.extend(
            contract_violations(value[key], fields[key], f'{path}[{key!r}]')
        )
    return violations


def _union_violations(value: object, hint: Any, path: str) -> list[str]:
    if any(
        not contract_violations(value, option, path)
        for option in get_args(hint)
    ):
        return []
    return [f'{path}: {type(value).__name__} matches none of {hint}']


def _list_violations(value: object, item_hint: Any, path: str) -> list[str]:
    if not isinstance(value, list):
        return [f'{path}: expected list, got {type(value).__name__}']
    return [
        violation
        for index, item in enumerate(value)
        for violation in contract_violations(
            item, item_hint, f'{path}[{index}]'
        )
    ]


def _dict_violations(
    value: object, hints: tuple[Any, ...], path: str
) -> list[str]:
    if not isinstance(value, dict):
        return [f'{path}: expected dict, got {type(value).__name__}']
    key_hint, item_hint = hints
    violations: list[str] = []
    for key, item in value.items():
        violations.extend(
            contract_violations(key, key_hint, f'{path} key {key!r}')
        )
        violations.extend(
            contract_violations(item, item_hint, f'{path}[{key!r}]')
        )
    return violations


def _scalar_violations(value: object, hint: Any, path: str) -> list[str]:
    if hint is NoneType:
        accepted = value is None
    elif hint in NUMERIC_TYPES:
        accepted = isinstance(value, NUMERIC_TYPES[hint]) and not isinstance(
            value, bool
        )
    else:
        accepted = isinstance(value, hint)
    if accepted:
        return []
    return [f'{path}: expected {hint.__name__}, got {type(value).__name__}']


class ObservedPath(NamedTuple):
    """Facts that identify which result producer handled a scenario."""

    error_keys: tuple[str, ...]
    source_count: int
    warning_codes: tuple[str, ...]
    source_warning_codes: tuple[str, ...]


def observed_path(result: ExtractionResultB3) -> ObservedPath:
    """Summarize the outcome facts that distinguish result producers."""
    integrity = result['integrity']
    return ObservedPath(
        error_keys=tuple(sorted(result['errors'])),
        source_count=len(integrity['sources']),
        warning_codes=tuple(
            sorted({warning['code'] for warning in integrity['warnings']})
        ),
        source_warning_codes=tuple(
            sorted(
                {
                    warning['code']
                    for source in integrity['sources']
                    for warning in source['warnings']
                }
            )
        ),
    )


@dataclass(frozen=True)
class ScenarioContext:
    """Locations and patching seam available to one scenario setup."""

    sources: Path
    output: Path
    monkeypatch: pytest.MonkeyPatch


@dataclass(frozen=True)
class ContractScenario:
    """One reachable producer of the public extraction result."""

    prepare: Callable[[ScenarioContext], None]
    first_year: int
    last_year: int
    expected: ObservedPath
    assets: tuple[str, ...] | None = None


def write_sources_with_every_warning(context: ScenarioContext) -> None:
    """Publish one source while raising source and integrity warnings."""
    records = [build_cotahist_record(year=2023)]
    for write in (write_cotahist_zip, write_cotahist_txt):
        write(
            context.sources,
            year=2023,
            records=records,
            trailer_convention='quotes_only',
        )
    write_cotahist_txt(
        context.sources,
        year=2024,
        records=[build_cotahist_record(year=2024, market='070')],
    )


def write_one_valid_source(context: ScenarioContext) -> None:
    """Write a single valid annual source for 2023."""
    write_cotahist_txt(
        context.sources,
        year=2023,
        records=[build_cotahist_record(year=2023)],
    )


def write_no_sources(context: ScenarioContext) -> None:
    """Leave the caller catalog empty."""
    assert not any(context.sources.iterdir())


def write_valid_then_truncated_source(context: ScenarioContext) -> None:
    """Fail preflight after an earlier source was already observed."""
    write_one_valid_source(context)
    write_cotahist_txt(
        context.sources,
        year=2024,
        records=[build_cotahist_record(year=2024)[:200]],
    )


def write_corrupt_archive(context: ScenarioContext) -> None:
    """Write bytes that are not a ZIP under an official archive name."""
    (context.sources / 'COTAHIST_A2023.ZIP').write_bytes(b'not a zip archive')


def fail_source_worker(context: ScenarioContext) -> None:
    """Make the only source fail inside its extraction worker."""
    write_one_valid_source(context)

    def reject_source(*_args: object, **_kwargs: object) -> NoReturn:
        raise RuntimeError('injected source worker failure')

    context.monkeypatch.setattr(
        extraction_service.ZipProcessorB3, 'process', reject_source
    )


def fail_final_publication(context: ScenarioContext) -> None:
    """Make the verified output fail at its final atomic replacement."""
    write_one_valid_source(context)
    replace = FileOperations.replace
    final_output = context.output.resolve()

    def reject_final_replacement(
        self: FileOperations, source: Path, destination: Path
    ) -> None:
        if Path(destination).resolve() == final_output:
            raise OSError('injected final publication failure')
        replace(self, source, destination)

    context.monkeypatch.setattr(
        FileOperations, 'replace', reject_final_replacement
    )


SCENARIOS = [
    pytest.param(
        ContractScenario(
            prepare=write_sources_with_every_warning,
            first_year=2023,
            last_year=2024,
            assets=('ações',),
            expected=ObservedPath(
                error_keys=(),
                source_count=2,
                warning_codes=(
                    'IGNORED_EQUIVALENT_TXT',
                    'NO_SELECTED_QUOTES',
                    'TRAILER_QUOTES_ONLY',
                ),
                source_warning_codes=('TRAILER_QUOTES_ONLY',),
            ),
        ),
        id='published-with-warnings',
    ),
    pytest.param(
        ContractScenario(
            prepare=write_one_valid_source,
            first_year=2022,
            last_year=2023,
            expected=ObservedPath(('coverage',), 1, (), ()),
        ),
        id='missing-requested-year',
    ),
    pytest.param(
        ContractScenario(
            prepare=write_no_sources,
            first_year=2023,
            last_year=2023,
            expected=ObservedPath(('coverage',), 0, (), ()),
        ),
        id='no-input-files',
    ),
    pytest.param(
        ContractScenario(
            prepare=write_valid_then_truncated_source,
            first_year=2023,
            last_year=2024,
            expected=ObservedPath(('COTAHIST_A2024.TXT',), 1, (), ()),
        ),
        id='invalid-record-preflight',
    ),
    pytest.param(
        ContractScenario(
            prepare=write_corrupt_archive,
            first_year=2023,
            last_year=2023,
            expected=ObservedPath(('COTAHIST_A2023.ZIP',), 0, (), ()),
        ),
        id='corrupt-archive-preflight',
    ),
    pytest.param(
        ContractScenario(
            prepare=fail_source_worker,
            first_year=2023,
            last_year=2023,
            expected=ObservedPath(('COTAHIST_A2023.TXT',), 1, (), ()),
        ),
        id='source-worker-failure',
    ),
    pytest.param(
        ContractScenario(
            prepare=fail_final_publication,
            first_year=2023,
            last_year=2023,
            expected=ObservedPath(('transaction',), 1, (), ()),
        ),
        id='final-publication-failure',
    ),
]


@pytest.mark.integration
@pytest.mark.parametrize('scenario', SCENARIOS)
def test_every_extraction_outcome_matches_the_published_result_contract(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    scenario: ContractScenario,
) -> None:
    """Each reachable result producer returns exactly the declared shape.

    Thread workers keep injected faults in-process; results are assembled in
    the calling process for every executor backend.
    """
    monkeypatch.setenv('GDF_B3_EXECUTOR_BACKEND', 'thread')
    sources = tmp_path / 'sources'
    sources.mkdir()
    destination = tmp_path / 'output'
    scenario.prepare(
        ScenarioContext(sources, destination / OUTPUT_FILENAME, monkeypatch)
    )

    result = HistoricalQuotesB3().extract(
        path_of_docs=str(sources),
        assets_list=None if scenario.assets is None else list(scenario.assets),
        initial_year=scenario.first_year,
        last_year=scenario.last_year,
        destination_path=str(destination),
        output_filename=OUTPUT_FILENAME,
        verbose=False,
    )

    assert observed_path(result) == scenario.expected
    assert contract_violations(result, ExtractionResultB3, 'result') == []


class _SampleWarning(TypedDict):
    code: str
    count: int


class _SampleReport(TypedDict):
    status: Literal['passed', 'failed']
    digest: str | None
    ratio: float
    counts: dict[str, int]
    years: list[int]
    warnings: list[_SampleWarning]


@pytest.mark.unit
def test_contract_checker_reports_each_kind_of_drift() -> None:
    """The checker rejects key, literal, numeric, and nested drift."""
    conforming = {
        'status': 'passed',
        'digest': None,
        'ratio': 1,
        'counts': {'010': 3},
        'years': [2023],
        'warnings': [{'code': 'BLANK', 'count': 1}],
    }
    drifted = {
        'status': 'skipped',
        'digest': 7,
        'ratio': True,
        'counts': {'010': '3'},
        'years': (2023,),
        'warnings': [{'code': 'BLANK'}],
        'extra': 1,
    }

    assert contract_violations(conforming, _SampleReport, 'report') == []
    assert contract_violations(drifted, _SampleReport, 'report') == [
        "report: undeclared key 'extra'",
        "report['counts']['010']: expected int, got str",
        "report['digest']: int matches none of str | None",
        "report['ratio']: expected float, got bool",
        "report['status']: 'skipped' is not one of ('passed', 'failed')",
        "report['warnings'][0]: missing key 'count'",
        "report['years']: expected list, got tuple",
    ]
