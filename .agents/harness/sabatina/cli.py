"""Run cumulative sabatina validation and expose its command interface."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from harness.sabatina.closure import (
    check_closure,
    check_drafts,
    check_handoff,
    check_status,
    check_structure,
    check_understanding,
)
from harness.sabatina.decomposition import (
    check_decomposition,
)
from harness.sabatina.document import (
    PHASE_CLOSED,
    PHASE_PRE,
    PHASE_ROUND,
    PHASES,
    Document,
    Finding,
    parse_document,
)
from harness.sabatina.evidence import (
    check_coverage,
    check_facts,
    check_references,
)
from harness.sabatina.questions import (
    check_graph,
    check_questions,
    check_score,
    computed_score,
)
from harness.sabatina.routing import (
    check_route,
)


def validate(document: Document, phase: str) -> list[Finding]:
    """Apply the cumulative checks required by the selected phase."""
    findings = check_structure(document, phase)
    findings += check_status(document, phase)
    findings += check_questions(document)
    findings += check_references(document)
    findings += check_graph(document)
    findings += check_score(document)
    findings += check_facts(document)
    findings += check_coverage(document)
    if phase in (PHASE_PRE, PHASE_CLOSED):
        findings += check_closure(document)
        findings += check_understanding(document)
        findings += check_drafts(document, phase)
    if phase == PHASE_CLOSED:
        findings += check_handoff(document)
        findings += check_route(document)
        findings += check_decomposition(document)
    return findings


def build_report(
    document: Document, phase: str, findings: list[Finding]
) -> dict[str, object]:
    return {
        'status': 'error' if findings else 'ok',
        'phase': phase,
        'document': str(document.path),
        'question_count': len(document.questions),
        'score': computed_score(document),
        'errors': [finding.as_dict() for finding in findings],
    }


def _print_human(
    document: Document, phase: str, findings: list[Finding]
) -> None:
    for finding in findings:
        where = finding.question or finding.line or '-'
        print(f'error [{finding.code}] {where}: {finding.message}')
    summary = ' '.join(
        f'{name}={count}' for name, count in computed_score(document).items()
    )
    verdict = 'FALHOU' if findings else 'OK'
    print(
        f'{verdict} fase={phase} duvidas={len(document.questions)} {summary}'
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description='Valida um documento de sabatina.'
    )
    parser.add_argument('--document', required=True)
    parser.add_argument('--phase', choices=PHASES, default=PHASE_ROUND)
    parser.add_argument('--json', action='store_true')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    path = Path(args.document)
    if not path.is_file():
        print(f'error [document-missing] {path}: arquivo nao encontrado')
        return 2
    document = parse_document(path)
    findings = validate(document, args.phase)
    if args.json:
        report = build_report(document, args.phase, findings)
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        _print_human(document, args.phase, findings)
    return 1 if findings else 0
