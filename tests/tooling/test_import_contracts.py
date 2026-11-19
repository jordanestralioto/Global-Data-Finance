"""Import contracts keep future sources and namespaces inside the layering."""

from __future__ import annotations

import re
from pathlib import Path

import grimp
import importlinter.configuration
import pytest
from importlinter.application.use_cases import read_user_options
from importlinter.application.user_options import UserOptions
from importlinter.contracts.forbidden import ForbiddenContract
from importlinter.contracts.independence import IndependenceContract
from importlinter.contracts.layers import LayersContract
from importlinter.domain.contract import Contract

pytestmark = pytest.mark.unit

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT_PATH = REPOSITORY_ROOT / 'pyproject.toml'
CONTRACT_TYPES: dict[str, type[Contract]] = {
    'forbidden': ForbiddenContract,
    'independence': IndependenceContract,
    'layers': LayersContract,
}
NEW_SOURCE = 'globaldatafinance.brazil.new_source.client'
LAYER_SEPARATORS = re.compile(r'[|:]')


@pytest.fixture(scope='module')
def user_options() -> UserOptions:
    """Read the import contracts exactly as ``lint-imports`` reads them."""
    importlinter.configuration.configure()
    return read_user_options(str(PYPROJECT_PATH))


def build_package_graph(options: UserOptions) -> grimp.ImportGraph:
    """Build the uncached production import graph that the contracts see."""
    session = options.session_options
    return grimp.build_graph(
        *session['root_packages'],
        include_external_packages=bool(
            session.get('include_external_packages', False)
        ),
        exclude_type_checking_imports=bool(
            session.get('exclude_type_checking_imports', False)
        ),
        cache_dir=None,
    )


def add_module_import(
    graph: grimp.ImportGraph, importer: str, imported: str
) -> None:
    """Add one import, registering hypothetical modules and their packages."""
    for module in (importer, imported):
        parts = module.split('.')
        for depth in range(1, len(parts) + 1):
            name = '.'.join(parts[:depth])
            if name not in graph.modules:
                graph.add_module(name)
    graph.add_import(importer=importer, imported=imported)


def broken_contracts(
    graph: grimp.ImportGraph, options: UserOptions
) -> list[str]:
    """Return the names of configured contracts that the graph violates."""
    broken: list[str] = []
    for contract_options in options.contracts_options:
        contract_type = contract_options['type']
        if contract_type not in CONTRACT_TYPES:
            pytest.fail(
                f'Map the {contract_type!r} import-linter contract type '
                'in CONTRACT_TYPES before relying on it.'
            )
        contract = CONTRACT_TYPES[contract_type](
            name=contract_options['name'],
            session_options=options.session_options,
            contract_options=contract_options,
        )
        if not contract.check(graph, verbose=False).kept:
            broken.append(contract.name)
    return broken


def layered_modules(options: UserOptions) -> set[str]:
    """Return every module named by the configured layers contracts."""
    return {
        part.strip().strip('()').strip()
        for contract_options in options.contracts_options
        if contract_options['type'] == 'layers'
        for layer in contract_options['layers']
        for part in LAYER_SEPARATORS.split(layer)
    }


def unlayered_namespaces(
    graph: grimp.ImportGraph, options: UserOptions
) -> list[str]:
    """Return top-level namespaces that no layers contract constrains."""
    namespaces = {
        child
        for root in options.session_options['root_packages']
        for child in graph.find_children(root)
    }
    return sorted(namespaces - layered_modules(options))


def test_configured_contracts_hold_for_the_current_package(
    user_options: UserOptions,
) -> None:
    """The unmodified package graph keeps every configured contract."""
    graph = build_package_graph(user_options)

    assert broken_contracts(graph, user_options) == []


@pytest.mark.parametrize(
    ('importer', 'imported'),
    [
        pytest.param(
            NEW_SOURCE,
            'globaldatafinance.brazil.cvm.ingestion.http',
            id='new-source-imports-cvm-internals',
        ),
        pytest.param(
            'globaldatafinance.brazil.b3_data.historical_quotes.client',
            NEW_SOURCE,
            id='b3-imports-new-source',
        ),
    ],
)
def test_new_brazilian_source_cannot_couple_to_another_source(
    user_options: UserOptions, importer: str, imported: str
) -> None:
    """Source independence covers sources added after the contract."""
    graph = build_package_graph(user_options)
    add_module_import(graph, importer, imported)

    assert broken_contracts(graph, user_options) != []


def test_every_top_level_namespace_is_assigned_to_a_layer(
    user_options: UserOptions,
) -> None:
    """No current namespace escapes the layered architecture contract."""
    graph = build_package_graph(user_options)

    assert unlayered_namespaces(graph, user_options) == []


def test_new_top_level_namespace_is_reported_until_layered(
    user_options: UserOptions,
) -> None:
    """A namespace that layers do not list is reported instead of ignored."""
    graph = build_package_graph(user_options)
    add_module_import(
        graph, 'globaldatafinance.usa.sec', 'globaldatafinance.application'
    )

    assert broken_contracts(graph, user_options) == []
    assert unlayered_namespaces(graph, user_options) == [
        'globaldatafinance.usa'
    ]
