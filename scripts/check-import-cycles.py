#!/usr/bin/env python3
"""Fail when the package's import graph contains a cycle.

import-linter (see [tool.importlinter] in pyproject.toml) enforces the
*layering* between top-level packages, but it has no contract type that
expresses "no cycles anywhere". The gap matters: the common Python cycle is a
submodule importing its own package root (``from ...core import x`` while
``core/__init__`` imports that same submodule). That is invisible to a layers
contract because the package root is the container, not a sibling layer.

Importing a submodule also initializes its parent packages. Those implicit
dependencies can hide a cycle even when modules import defining files directly.
Include them unless the importer is already inside the package being
initialized. Local imports are checked too: delaying a dependency does not
remove it from the library's structural contract.
"""

from __future__ import annotations

import sys

import grimp

PACKAGE = 'globaldatafinance'


class _TarjanState:
    """Mutable state shared by the iterative Tarjan traversal."""

    def __init__(self) -> None:
        self.index: dict[str, int] = {}
        self.low: dict[str, int] = {}
        self.on_stack: set[str] = set()
        self.stack: list[str] = []
        self.cycles: list[list[str]] = []
        self.counter = 0


def _enter_node(node: str, state: _TarjanState) -> None:
    """Assign a Tarjan index and push one newly discovered node."""
    state.index[node] = state.low[node] = state.counter
    state.counter += 1
    state.stack.append(node)
    state.on_stack.add(node)


def _advance_frame(
    adjacency: dict[str, list[str]],
    state: _TarjanState,
    work: list[tuple[str, int]],
) -> bool:
    """Advance one DFS frame, pushing an unvisited child when present."""
    node, child_index = work[-1]
    children = adjacency[node]
    for index in range(child_index, len(children)):
        child = children[index]
        if child not in state.index:
            work[-1] = (node, index + 1)
            work.append((child, 0))
            return True
        if child in state.on_stack:
            state.low[node] = min(state.low[node], state.index[child])
    return False


def _close_component(
    node: str,
    adjacency: dict[str, list[str]],
    state: _TarjanState,
) -> None:
    """Close and record the strongly connected component rooted at a node."""
    if state.low[node] != state.index[node]:
        return
    component: list[str] = []
    while True:
        member = state.stack.pop()
        state.on_stack.discard(member)
        component.append(member)
        if member == node:
            break
    if len(component) > 1 or component[0] in adjacency[component[0]]:
        state.cycles.append(sorted(component))


def _finish_frame(
    adjacency: dict[str, list[str]],
    state: _TarjanState,
    work: list[tuple[str, int]],
) -> None:
    """Close one DFS frame and propagate its low link to the parent."""
    node = work[-1][0]
    _close_component(node, adjacency, state)
    work.pop()
    if work:
        parent = work[-1][0]
        state.low[parent] = min(state.low[parent], state.low[node])


def _walk_component(
    root: str,
    adjacency: dict[str, list[str]],
    state: _TarjanState,
) -> None:
    """Traverse one connected region without recursive Python calls."""
    work: list[tuple[str, int]] = [(root, 0)]
    while work:
        node = work[-1][0]
        if node not in state.index:
            _enter_node(node, state)
        if _advance_frame(adjacency, state, work):
            continue
        _finish_frame(adjacency, state, work)


def find_cycles(graph: grimp.ImportGraph) -> list[list[str]]:
    """Return every strongly connected component that contains a cycle.

    This check uses a static import graph. Imports guarded by ``TYPE_CHECKING``
    are deliberately excluded from this contract; dynamic imports are outside
    this contract.

    Iterative Tarjan, so a deep import graph cannot blow the stack.
    """
    modules = sorted(graph.modules)
    adjacency = {
        m: sorted(graph.find_modules_directly_imported_by(m)) for m in modules
    }

    state = _TarjanState()

    for root in modules:
        if root not in state.index:
            _walk_component(root, adjacency, state)

    return state.cycles


def _add_package_initialization_imports(
    graph: grimp.ImportGraph,
) -> dict[tuple[str, str], str]:
    """Include initializer dependencies outside the importer's ancestry."""
    modules = graph.modules
    implicit: dict[tuple[str, str], str] = {}
    for importer in sorted(modules):
        for imported in sorted(
            graph.find_modules_directly_imported_by(importer)
        ):
            details = graph.get_import_details(
                importer=importer, imported=imported
            )
            parent = imported.rpartition('.')[0]
            while parent:
                if (
                    parent in modules
                    and importer != parent
                    and not importer.startswith(parent + '.')
                    and not graph.direct_import_exists(
                        importer=importer, imported=parent
                    )
                ):
                    if details:
                        graph.add_import(
                            importer=importer,
                            imported=parent,
                            line_number=details[0]['line_number'],
                            line_contents=details[0]['line_contents'],
                        )
                    else:
                        graph.add_import(importer=importer, imported=parent)
                    implicit[importer, parent] = imported
                parent = parent.rpartition('.')[0]
    return implicit


def main() -> int:
    """Check the package import graph for circular dependencies."""
    graph = grimp.build_graph(
        PACKAGE,
        exclude_type_checking_imports=True,
    )
    implicit = _add_package_initialization_imports(graph)
    cycles = find_cycles(graph)

    if not cycles:
        print(f'  ok no import cycles ({len(graph.modules)} modules)')
        return 0

    print(f'Import cycle(s) detected in {PACKAGE}:', file=sys.stderr)
    for component in cycles:
        print('', file=sys.stderr)
        for module in component:
            targets = sorted(
                set(graph.find_modules_directly_imported_by(module))
                & set(component)
            )
            for target in targets:
                details = graph.get_import_details(
                    importer=module, imported=target
                )
                where = (
                    f' (line {details[0]["line_number"]})'
                    if details and details[0].get('line_number')
                    else ''
                )
                if initialized_for := implicit.get((module, target)):
                    where += f' (package initialization for {initialized_for})'
                print(f'  {module} -> {target}{where}', file=sys.stderr)
    print(
        '\nRemove the dependency cycle, including package initialization. '
        'Moving an import inside a function does not remove the dependency.',
        file=sys.stderr,
    )
    return 1


if __name__ == '__main__':
    raise SystemExit(main())
