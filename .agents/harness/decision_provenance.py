"""Authenticate decision ownership and dependencies across OpenSpec changes."""

from __future__ import annotations

from pathlib import Path

from harness.change_manifest import (
    iter_decision_change_dirs,
    load_change_manifest,
    logical_change_name,
)
from harness.decision_source import (
    SourceNamespace,
    provenance_finding,
    source_descriptor,
)

Descriptor = tuple[str, SourceNamespace | None, dict[str, object], list[str]]


def _unverifiable_owner(change_dir: Path, reason: str) -> dict[str, str]:
    return {
        'code': 'decision-owner-unverifiable',
        'message': f'{logical_change_name(change_dir)} cannot prove its decision ownership ({reason}).',
    }


def _dependency_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(name: str) -> list[str] | None:
        if name in visiting:
            return [*stack[stack.index(name) :], name]
        if name in visited:
            return None
        visiting.add(name)
        stack.append(name)
        for dependency in graph.get(name, []):
            if cycle := visit(dependency):
                return cycle
        stack.pop()
        visiting.remove(name)
        visited.add(name)
        return None

    for name in sorted(graph):
        if cycle := visit(name):
            return cycle
    return None


def _str_list(value: object) -> list[str]:
    return [str(item) for item in value] if isinstance(value, list) else []


def validate_decision_source(
    repo_root: Path, change_dir: Path, change_dirs: list[Path] | None = None
) -> tuple[dict[str, object] | None, list[dict[str, str]]]:
    """Validate one source envelope and its durable ownership graph."""
    decision_dirs = (
        change_dirs
        if change_dirs is not None
        else iter_decision_change_dirs(repo_root / 'openspec/changes')
    )
    source, source_namespace, findings = source_descriptor(
        repo_root, change_dir
    )
    descriptors: list[Descriptor] = []
    for candidate in decision_dirs:
        candidate_source, namespace, candidate_findings = source_descriptor(
            repo_root, candidate
        )
        if candidate_source is None:
            if 'decision_source' in load_change_manifest(candidate):
                findings.append(
                    _unverifiable_owner(candidate, 'decision-source-missing')
                )
            continue
        if (
            candidate_findings
            and candidate.resolve() != change_dir.resolve()
            and namespace in (None, source_namespace)
        ):
            codes = ', '.join(
                sorted({item['code'] for item in candidate_findings})
            )
            findings.append(_unverifiable_owner(candidate, codes))
        ids = _str_list(candidate_source.get('decision_ids'))
        descriptors.append(
            (logical_change_name(candidate), namespace, candidate_source, ids)
        )
    if source is not None:
        owners: dict[tuple[tuple[str, str, str], str], list[str]] = {}
        for name, namespace, _descriptor, ids in descriptors:
            if namespace is None:
                continue
            for decision_id in ids:
                owners.setdefault((namespace, decision_id), []).append(name)
        for (_, decision_id), names in sorted(owners.items()):
            # Ownership is exclusive; dependencies never grant co-ownership.
            if len(names) > 1:
                findings.append(
                    provenance_finding(
                        'decision-id-duplicate-owner',
                        f'{decision_id} is owned by sibling changes:'
                        f' {", ".join(names)}.',
                    )
                )
    graph: dict[str, list[str]] = {}
    known_names = {name for name, _, _, _ in descriptors}
    for name, _, descriptor, _ in descriptors:
        dependencies = _str_list(descriptor.get('depends_on'))
        if unknown := sorted(set(dependencies) - known_names):
            findings.append(
                provenance_finding(
                    'decision-dependency-unknown',
                    f'{name} depends on unknown changes: {", ".join(unknown)}.',
                )
            )
        graph[name] = [item for item in dependencies if item in known_names]
    cycle = _dependency_cycle(graph)
    if cycle:
        findings.append(
            provenance_finding(
                'decision-dependency-cycle',
                'Decision-source dependency cycle: '
                + ' -> '.join(cycle)
                + '.',
            )
        )
    return source, findings
