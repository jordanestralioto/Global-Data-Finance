"""Validate one declared decision source against its repository and document."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from harness import sabatina
from harness.change_manifest import load_change_manifest, logical_change_name

DATE_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')
DECISION_ID_RE = re.compile(r'^Q\d+$')
SHA256_RE = re.compile(r'^[0-9a-f]{64}$', re.I)
SourceNamespace = tuple[str, str, str]


def provenance_finding(code: str, message: str) -> dict[str, str]:
    return {'code': code, 'message': message}


def _resolve_source_path(
    repo_root: Path, raw_path: object, findings: list[dict[str, str]]
) -> Path | None:
    if not isinstance(raw_path, str) or not raw_path.strip():
        findings.append(
            provenance_finding(
                'decision-source-path',
                'decision_source.path must be a repository-relative path.',
            )
        )
        return None
    candidate = Path(raw_path)
    try:
        resolved = (repo_root / candidate).resolve()
        resolved.relative_to(repo_root.resolve())
    except (OSError, ValueError):
        findings.append(
            provenance_finding(
                'decision-source-path',
                'decision_source.path must remain inside the repository.',
            )
        )
        return None
    if candidate.is_absolute():
        findings.append(
            provenance_finding(
                'decision-source-path',
                'decision_source.path must be repository-relative.',
            )
        )
    return resolved


def _normalize_decision_ids(
    raw_ids: object, findings: list[dict[str, str]]
) -> list[str]:
    if not isinstance(raw_ids, list) or not raw_ids:
        findings.append(
            provenance_finding(
                'decision-source-ids',
                'decision_source.decision_ids must be a nonempty list.',
            )
        )
        return []
    normalized = [str(item) for item in raw_ids]
    invalid = [
        item for item in normalized if not DECISION_ID_RE.fullmatch(item)
    ]
    if invalid:
        findings.append(
            provenance_finding(
                'decision-source-ids',
                'Invalid decision IDs: ' + ', '.join(invalid) + '.',
            )
        )
    if len(set(normalized)) != len(normalized):
        findings.append(
            provenance_finding(
                'decision-source-ids',
                'decision_source.decision_ids must not contain duplicates.',
            )
        )
    return normalized


def _normalize_dependencies(
    raw_dependencies: object,
    change_dir: Path,
    findings: list[dict[str, str]],
) -> list[str]:
    if not isinstance(raw_dependencies, list) or not all(
        isinstance(item, str) and item.strip() for item in raw_dependencies
    ):
        findings.append(
            provenance_finding(
                'decision-source-dependencies',
                'decision_source.depends_on must be a list of change names.',
            )
        )
        return []
    normalized = [str(item) for item in raw_dependencies]
    if logical_change_name(change_dir) in normalized:
        findings.append(
            provenance_finding(
                'decision-source-dependencies',
                'A change cannot depend on itself.',
            )
        )
    return normalized


def _validate_source_file(
    repo_root: Path,
    source_type: object,
    source_path: Path | None,
    digest: object,
    decision_ids: list[str],
    findings: list[dict[str, str]],
) -> None:
    if source_path is None:
        return
    if not source_path.is_file():
        findings.append(
            provenance_finding(
                'decision-source-missing',
                f'Source file does not exist: {source_path.relative_to(repo_root)}.',
            )
        )
        return
    source_bytes = source_path.read_bytes()
    actual_digest = hashlib.sha256(source_bytes).hexdigest()
    if isinstance(digest, str) and actual_digest != digest.lower():
        findings.append(
            provenance_finding(
                'decision-source-digest-mismatch',
                f'Expected {digest}, found {actual_digest}.',
            )
        )
    source_text = source_bytes.decode('utf-8', errors='replace')
    missing_ids = [
        decision_id
        for decision_id in decision_ids
        if not re.search(
            rf'(?<![A-Z0-9]){re.escape(decision_id)}(?![A-Z0-9])',
            source_text,
        )
    ]
    findings.extend(
        provenance_finding(
            'decision-id-not-found',
            f'{decision_id} does not occur in {source_path.relative_to(repo_root)}.',
        )
        for decision_id in missing_ids
    )
    if source_type == 'sabatina':
        _validate_closed_sabatina(source_path, findings)


def validate_sabatina_ownership(
    source_path: Path,
    change_name: str,
    decision_ids: list[str],
    findings: list[dict[str, str]],
    dependencies: list[str] | None = None,
) -> None:
    document = sabatina.parse_document(source_path)
    body = sabatina._subsection_body(
        document, 'handoff', sabatina.HANDOFF_ROUTE_SECTION
    )
    table = sabatina._find_table(sabatina._tables(body), 'ids')
    units = sabatina._decomposition_units(table) if table else []
    unit = next((item for item in units if item.name == change_name), None)
    if unit is None:
        findings.append(
            provenance_finding(
                'decision-owner-not-declared',
                f'{change_name} is absent from the sabatina decomposition.',
            )
        )
        return
    declared = list(unit.owned)
    if declared != decision_ids:
        findings.append(
            provenance_finding(
                'decision-owner-mismatch',
                f'{change_name} declares {decision_ids}, but the sabatina '
                f'assigns {declared}.',
            )
        )
    if dependencies is not None and list(unit.dependencies) != dependencies:
        findings.append(
            provenance_finding(
                'decision-dependency-mismatch',
                f'{change_name} declares dependencies {dependencies}, but '
                f'the sabatina assigns {list(unit.dependencies)}.',
            )
        )


def _validate_closed_sabatina(
    source_path: Path, findings: list[dict[str, str]]
) -> None:
    document = sabatina.parse_document(source_path)
    errors = sabatina.validate(document, sabatina.PHASE_CLOSED)
    if errors:
        detail = json.dumps(
            sabatina.build_report(document, sabatina.PHASE_CLOSED, errors),
            ensure_ascii=False,
            indent=2,
        )
        findings.append(
            provenance_finding(
                'sabatina-not-closed',
                f'Closed sabatina validation failed: {detail[-500:]}.',
            )
        )


def source_descriptor(
    repo_root: Path,
    change_dir: Path,
) -> tuple[
    dict[str, object] | None, SourceNamespace | None, list[dict[str, str]]
]:
    raw_source = load_change_manifest(change_dir).get('decision_source')
    if not isinstance(raw_source, dict):
        missing = provenance_finding(
            'decision-source-missing',
            'Change must declare a decision_source envelope in .openspec.yaml.',
        )
        return None, None, [missing]
    findings: list[dict[str, str]] = []
    source = dict(raw_source)
    source_type = source.get('type')
    if source_type not in {'sabatina', 'user-contract'}:
        findings.append(
            provenance_finding(
                'decision-source-type',
                "decision_source.type must be 'sabatina' or 'user-contract'.",
            )
        )
    source_path = _resolve_source_path(repo_root, source.get('path'), findings)
    digest = source.get('sha256')
    if not isinstance(digest, str) or not SHA256_RE.fullmatch(digest):
        findings.append(
            provenance_finding(
                'decision-source-digest',
                'decision_source.sha256 must be a 64-character SHA-256 digest.',
            )
        )
    confirmed = source.get('confirmed_on')
    if not isinstance(confirmed, str) or not DATE_RE.fullmatch(confirmed):
        findings.append(
            provenance_finding(
                'decision-source-confirmation',
                'decision_source.confirmed_on must use YYYY-MM-DD.',
            )
        )
    decision_ids = _normalize_decision_ids(
        source.get('decision_ids'), findings
    )
    if 'depends_on' not in source:
        findings.append(
            provenance_finding(
                'decision-source-dependencies-missing',
                'decision_source.depends_on is required; declare [] for a root '
                'change.',
            )
        )
        dependencies = []
    else:
        dependencies = _normalize_dependencies(
            source.get('depends_on'), change_dir, findings
        )
    _validate_source_file(
        repo_root, source_type, source_path, digest, decision_ids, findings
    )
    if source_type == 'sabatina' and source_path and source_path.is_file():
        validate_sabatina_ownership(
            source_path,
            logical_change_name(change_dir),
            decision_ids,
            findings,
            dependencies,
        )
    source['decision_ids'] = decision_ids
    source['depends_on'] = dependencies
    namespace = None
    if (
        source_type in ('sabatina', 'user-contract')
        and source_path is not None
        and isinstance(digest, str)
        and SHA256_RE.fullmatch(digest)
    ):
        namespace = (
            str(source_type),
            source_path.relative_to(repo_root.resolve()).as_posix(),
            digest.lower(),
        )
    return source, namespace, findings
