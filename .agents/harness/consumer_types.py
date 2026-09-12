"""Core types, exceptions, and frontmatter parsing for consumer validation."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SCOPE_VALIDATORS: dict[str, list[str]] = {
    'skills': [
        'skill.frontmatter',
        'skill.references',
        'skill.script-syntax',
        'skill.structure',
    ],
    'agents': ['agent.frontmatter', 'agent.references', 'agent.structure'],
    'workflows': [
        'workflow.frontmatter',
        'workflow.references',
        'workflow.structure',
    ],
}

ALLOWED_SKILL_ACTIVE_FM = {'name', 'description'}
ALLOWED_SKILL_ARCHIVED_FM = {'name', 'description', 'status', 'replaced_by'}
ALLOWED_AGENT_FM = {'name', 'description', 'mode', 'agents'}
ALLOWED_WORKFLOW_FM = {'name', 'description', 'category', 'tags'}

AGENT_REQUIRED_SECTIONS = ('Identity', 'Can Do', 'Cannot Do', 'Done When')
AGENT_LEGACY_SECTIONS = (
    'Skill Routing',
    'Escalation',
    'Activation Rule',
    'Required Inputs',
    'Preflight',
    'Context Policy',
    'Phase Machine',
    'Failure Branches',
    'Success Exit',
    'Stop Conditions',
    'Hard Boundaries',
)


class ConsumerValidationError(Exception):
    """Base error for consumer validation."""


class ContractError(ConsumerValidationError):
    """Contract violation in request or environment (exit code 2)."""


class BoundaryError(ContractError):
    """Path or symlink escapes the repository boundary (exit code 2)."""


class DistributionVersionError(ContractError):
    """Installed distribution metadata cannot be resolved (exit code 2)."""


@dataclass(frozen=True)
class Diagnostic:
    item: str
    validator_id: str
    code: str
    message: str
    severity: str = 'error'

    def to_dict(self) -> dict[str, str]:
        return {
            'code': self.code,
            'item': self.item,
            'message': self.message,
            'severity': self.severity,
            'validatorId': self.validator_id,
        }


def _split_csv_preserving_quotes(s: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    in_single = False
    in_double = False
    for char in s:
        if char == "'" and not in_double:
            in_single = not in_single
            current.append(char)
        elif char == '"' and not in_single:
            in_double = not in_double
            current.append(char)
        elif char == ',' and not in_single and not in_double:
            parts.append(''.join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        parts.append(''.join(current).strip())
    return parts


def _parse_yaml_scalar(val: str) -> Any:
    val = val.strip()
    if (val.startswith('"') and val.endswith('"')) or (
        val.startswith("'") and val.endswith("'")
    ):
        return val[1:-1]
    if val in ('true', 'True', 'TRUE'):
        return True
    if val in ('false', 'False', 'FALSE'):
        return False
    if val in ('null', 'Null', 'NULL', '~'):
        return None
    if re.fullmatch(r'[+-]?\d+', val):
        try:
            return int(val)
        except ValueError:
            pass
    if re.fullmatch(r'[+-]?(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?', val):
        try:
            return float(val)
        except ValueError:
            pass
    if val.startswith('[') and val.endswith(']'):
        inner = val[1:-1].strip()
        return (
            [
                _parse_yaml_scalar(x)
                for x in _split_csv_preserving_quotes(inner)
                if x
            ]
            if inner
            else []
        )
    if val.startswith('{') and val.endswith('}'):
        inner = val[1:-1].strip()
        if not inner:
            return {}
        res: dict[str, Any] = {}
        for item in _split_csv_preserving_quotes(inner):
            if ':' in item:
                k, _, v = item.partition(':')
                res[k.strip().strip('"\'')] = _parse_yaml_scalar(v.strip())
        return res
    return val


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Parse UTF-8 YAML frontmatter block and return (metadata, body)."""
    match = re.match(r'^---\r?\n(.*?)\r?\n---\r?\n', text, re.DOTALL)
    if not match:
        raise ValueError(
            'frontmatter missing or malformed (expected --- ... ---)'
        )
    body = text[match.end() :]
    meta: dict[str, Any] = {}
    current_key: str | None = None
    current_lines: list[str] = []

    def flush() -> None:
        if current_key is not None:
            meta[current_key] = ' '.join(current_lines).strip()

    for line in match.group(1).splitlines():
        if line.startswith((' ', '\t')) and current_key:
            current_lines.append(line.strip())
            continue
        flush()
        current_key, current_lines = None, []
        if not line.strip() or ':' not in line:
            continue
        key, _, raw_val = line.partition(':')
        key, val = key.strip(), raw_val.strip()
        if val in ('>', '>-', '|', '|-', '>+', '|+'):
            current_key = key
        else:
            meta[key] = _parse_yaml_scalar(val)
    flush()
    return meta, body


FORBIDDEN_SOURCE_PREFIXES = (
    'openspec/schema/',
    'workflows/',
    'skills/',
    'agents/',
    'runtime/',
    'harness/',
)


def check_declared_refs(
    root: Path, file_path: Path, text: str, v_id: str, code_prefix: str
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    item_str = file_path.relative_to(root).as_posix()
    pattern = (
        r'(?<![A-Za-z0-9._\-/])'
        r'(?:'
        r'\.agents/(?:skills|scripts|runtime)|'
        r'references|assets|scripts|templates|schemas|data|'
        r'openspec/schema|workflows|skills|agents|runtime|harness|'
        r'(?:\.\./)+'
        r')/[A-Za-z0-9._\-/]+(?:\.[A-Za-z0-9._-]+)?'
    )
    for raw_ref in sorted(set(re.findall(pattern, text))):
        ref = raw_ref.rstrip('.,;:)')
        if ref.startswith(FORBIDDEN_SOURCE_PREFIXES) or (
            ref.startswith('..')
            and any(f'/{p}' in ref for p in FORBIDDEN_SOURCE_PREFIXES)
        ):
            diags.append(
                Diagnostic(
                    item_str,
                    v_id,
                    f'{code_prefix}.reference.invalid',
                    f'forbidden source-tree reference: {raw_ref}',
                )
            )
            continue
        if ref.startswith('.agents/'):
            target = root / ref
        else:
            target = file_path.parent / ref
        try:
            resolved_root = root.resolve()
            resolved_target = target.resolve()
            if not resolved_target.is_relative_to(resolved_root):
                diags.append(
                    Diagnostic(
                        item_str,
                        v_id,
                        f'{code_prefix}.reference.outside-root',
                        f'reference escapes root: {raw_ref}',
                    )
                )
                continue
        except OSError:
            diags.append(
                Diagnostic(
                    item_str,
                    v_id,
                    f'{code_prefix}.reference.invalid',
                    f'reference cannot be resolved: {raw_ref}',
                )
            )
            continue
        if not target.exists():
            diags.append(
                Diagnostic(
                    item_str,
                    v_id,
                    f'{code_prefix}.reference.invalid',
                    f'referenced file does not exist: {raw_ref}',
                )
            )
    return diags


def check_fm_base(
    meta: dict[str, Any],
    expected_name: str | None,
    allowed: set[str],
    item_path: str,
    v_id: str,
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    prefix = v_id.split('.')[0]
    name, desc = meta.get('name'), meta.get('description')
    if not isinstance(name, str) or not name.strip():
        diags.append(
            Diagnostic(
                item_path,
                v_id,
                f'{prefix}.metadata.missing',
                "missing or invalid non-empty 'name'",
            )
        )
    elif expected_name and name.strip() != expected_name:
        diags.append(
            Diagnostic(
                item_path,
                v_id,
                f'{prefix}.metadata.name-mismatch',
                f"frontmatter name '{name.strip()}' != '{expected_name}'",
            )
        )
    if not isinstance(desc, str) or not desc.strip():
        diags.append(
            Diagnostic(
                item_path,
                v_id,
                f'{prefix}.metadata.missing',
                "missing or invalid non-empty 'description'",
            )
        )
    extras = set(meta) - allowed
    if extras:
        diags.append(
            Diagnostic(
                item_path,
                v_id,
                f'{prefix}.frontmatter.invalid',
                f'extra frontmatter keys: {sorted(extras)}',
            )
        )
    return diags
