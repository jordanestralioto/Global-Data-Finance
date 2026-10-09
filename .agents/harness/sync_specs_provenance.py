"""Authenticate decision-source provenance before planning any spec mutations."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from harness.decision_provenance import validate_decision_source


@dataclass(frozen=True)
class SyncIssue:
    capability: str
    code: str
    message: str


def decision_preflight(
    repo_root: Path, change_name: str
) -> tuple[tuple[str, ...], list[SyncIssue]]:
    try:
        source, findings = validate_decision_source(
            repo_root, repo_root / 'openspec/changes' / change_name
        )
    except (OSError, RuntimeError, ValueError) as exc:
        return (), [SyncIssue('manifest', 'sync-provenance-error', str(exc))]
    if findings:
        return (), [
            SyncIssue(
                'manifest',
                'sync-provenance-error',
                f'{item["code"]}: {item["message"]}',
            )
            for item in findings
        ]
    if source is None:
        return (), [
            SyncIssue(
                'manifest',
                'sync-provenance-error',
                'decision-source preflight returned no source envelope',
            )
        ]
    raw_ids = source.get('decision_ids')
    if not isinstance(raw_ids, list) or not all(
        isinstance(item, str) for item in raw_ids
    ):
        return (), [
            SyncIssue(
                'manifest',
                'sync-provenance-error',
                'decision-source preflight returned invalid decision IDs',
            )
        ]
    return tuple(raw_ids), []
