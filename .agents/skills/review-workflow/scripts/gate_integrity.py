"""Resolve declared review gates and check evidence against repository state."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from runtime_support import REPO_ROOT, ArtifactError, normalize_repo_path

CHANGE_NAME = re.compile(r'^[A-Za-z0-9._-]+$')
HOOK_ID = re.compile(r'^\s*-\s+id:\s*[A-Za-z0-9._-]+\s*$', re.M)
HOOK_STAGES = re.compile(r'^\s*(?:default_)?stages\s*:', re.M)


def declared_contract(change: str | None) -> dict[str, Any]:
    handoff_path = REPO_ROOT / 'openspec/handoff.json'
    if handoff_path.is_file():
        if (
            not change
            or change in {'.', '..'}
            or not CHANGE_NAME.fullmatch(change)
        ):
            raise ArtifactError(
                'a valid --change is required by openspec/handoff.json'
            )
        try:
            config = json.loads(handoff_path.read_text(encoding='utf-8'))
            relative = config['evidencePath']
            if relative != 'evidence/gate-report.json':
                raise ArtifactError('invalid handoff evidence path')
            evidence = normalize_repo_path(
                f'openspec/changes/{change}/{relative}'
            )
            command = shlex.split(
                config['validationCommand'].replace('<change>', change)
            )
            verifier = normalize_repo_path(config['evidenceVerifier'])
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise ArtifactError(
                'invalid openspec/handoff.json gate contract'
            ) from exc
        evidence_index = (
            command.index('--evidence-path')
            if '--evidence-path' in command
            else -1
        )
        if (
            not command
            or '<change>' not in config['validationCommand']
            or command.count('--evidence-path') != 1
            or evidence_index < 0
            or command[evidence_index + 1 : evidence_index + 2] != [evidence]
            or not (REPO_ROOT / verifier).is_file()
        ):
            raise ArtifactError(
                'handoff validation command does not match evidence'
            )
        return {
            'mode': 'structured',
            'command': command,
            'evidence': evidence,
            'verifier': verifier,
            'change': change,
        }

    precommit = REPO_ROOT / '.pre-commit-config.yaml'
    config = (
        precommit.read_text(encoding='utf-8') if precommit.is_file() else ''
    )
    if HOOK_ID.search(config):
        if HOOK_STAGES.search(config):
            raise ArtifactError(
                'stage-specific hooks require a structured validation contract'
            )
        return {
            'mode': 'pre-commit',
            'command': ['pre-commit', 'run', '--all-files'],
        }
    raise ArtifactError('no declared validation contract was found')


def _git(*args: str) -> bytes:
    result = subprocess.run(
        ['git', *args], cwd=REPO_ROOT, capture_output=True, check=False
    )
    if result.returncode != 0:
        raise ArtifactError('cannot read repository state with git')
    return result.stdout


def state_fingerprint(
    session_dir: Path,
    reviewed_files: list[str],
    excluded_files: tuple[str, ...] = (),
) -> str:
    """Hash HEAD and reviewed or changed files, excluding session artifacts."""
    changed = set(reviewed_files)
    for args in (
        ('diff', '--name-only', '-z', '--cached'),
        ('diff', '--name-only', '-z'),
        ('ls-files', '--others', '--exclude-standard', '-z'),
    ):
        changed.update(
            os.fsdecode(path) for path in _git(*args).split(b'\0') if path
        )
    try:
        excluded = session_dir.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        excluded = None
    digest = hashlib.sha256(_git('rev-parse', 'HEAD'))
    included = [
        name
        for name in sorted(changed)
        if name not in excluded_files
        and (excluded is None or not Path(name).is_relative_to(excluded))
    ]
    if included:
        digest.update(
            _git(
                '--literal-pathspecs',
                'ls-files',
                '--stage',
                '-z',
                '--',
                *included,
            )
        )
    for name in included:
        path = Path(name)
        candidate = REPO_ROOT / path
        digest.update(os.fsencode(name) + b'\0')
        if candidate.is_symlink():
            digest.update(b'link\0' + os.fsencode(os.readlink(candidate)))
        elif candidate.is_file():
            digest.update(
                b'file\0' + hashlib.sha256(candidate.read_bytes()).digest()
            )
        else:
            digest.update(b'missing\0')
    return digest.hexdigest()


def evidence_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def recorded_evidence_issue(
    report: dict[str, Any], session_dir: Path
) -> str | None:
    """Return the reason a completed report cannot be used for approval."""
    try:
        contract = declared_contract(report.get('change'))
        if report.get('validationMode') != contract['mode']:
            return 'Gate report does not match the declared validation mode.'
        command = shlex.join(contract['command'])
        if not report['gates'] or report['gates'][0]['command'] != command:
            return (
                'Gate report does not match the declared validation command.'
            )
        excluded = (
            (contract['evidence'],) if contract['mode'] == 'structured' else ()
        )
        if report.get('stateFingerprint') != state_fingerprint(
            session_dir, report['reviewedFiles'], excluded
        ):
            return 'Repository state changed after validation.'
        if contract['mode'] == 'pre-commit':
            return None
        evidence = REPO_ROOT / contract['evidence']
        if report.get('sourceEvidencePath') != contract['evidence']:
            return 'Gate report points to different structured evidence.'
        if report.get('sourceEvidenceSha256') != evidence_digest(evidence):
            return 'Structured evidence changed after validation.'
        source = json.loads(evidence.read_text(encoding='utf-8'))
        if report['gates'][1:-1] != source['gates']:
            return 'Imported gates differ from verified structured evidence.'
        verify_command = [
            sys.executable,
            str(REPO_ROOT / contract['verifier']),
            '--verify-evidence',
            str(evidence),
        ]
        result = subprocess.run(
            verify_command,
            cwd=REPO_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode != 0:
            return 'Native evidence verification failed for current state.'
        if evidence_digest(evidence) != report['sourceEvidenceSha256']:
            return 'Structured evidence changed during native verification.'
        if (
            state_fingerprint(session_dir, report['reviewedFiles'], excluded)
            != report['stateFingerprint']
        ):
            return 'Repository state changed during native verification.'
    except (
        ArtifactError,
        OSError,
        UnicodeError,
        json.JSONDecodeError,
        KeyError,
        IndexError,
        TypeError,
    ) as exc:
        return f'Gate evidence cannot be verified: {exc}'
    return None
