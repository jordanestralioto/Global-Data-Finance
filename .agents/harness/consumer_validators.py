"""Allowlisted generic static validators for consumer validation."""

from __future__ import annotations

import re
from pathlib import Path

from harness.consumer_types import (
    AGENT_LEGACY_SECTIONS,
    AGENT_REQUIRED_SECTIONS,
    ALLOWED_AGENT_FM,
    ALLOWED_SKILL_ACTIVE_FM,
    ALLOWED_SKILL_ARCHIVED_FM,
    ALLOWED_WORKFLOW_FM,
    Diagnostic,
    check_declared_refs,
    check_fm_base,
    parse_frontmatter,
)


def validate_skill_item(
    root: Path, file_path: Path, item_path: str, _item_name: str
) -> list[Diagnostic]:
    try:
        text = file_path.read_text(encoding='utf-8')
    except (UnicodeDecodeError, OSError) as exc:
        return [
            Diagnostic(
                item_path,
                'skill.frontmatter',
                'skill.frontmatter.invalid',
                f'file cannot be read as UTF-8: {exc}',
            )
        ]
    diags: list[Diagnostic] = []
    if len(text.splitlines()) > 500:
        diags.append(
            Diagnostic(
                item_path,
                'skill.structure',
                'skill.document.size',
                f'{len(text.splitlines())} lines exceeds 500 limit',
            )
        )
    try:
        meta, body = parse_frontmatter(text)
    except ValueError as exc:
        return [
            Diagnostic(
                item_path,
                'skill.frontmatter',
                'skill.frontmatter.invalid',
                str(exc),
            )
        ]
    raw_status = meta.get('status', 'active')
    if not isinstance(raw_status, str) or raw_status not in (
        'active',
        'archived',
    ):
        diags.append(
            Diagnostic(
                item_path,
                'skill.frontmatter',
                'skill.frontmatter.invalid',
                f"invalid skill status '{raw_status}'",
            )
        )
        status = 'active'
    else:
        status = raw_status

    allowed = (
        ALLOWED_SKILL_ARCHIVED_FM
        if status == 'archived'
        else ALLOWED_SKILL_ACTIVE_FM
    )
    diags.extend(
        check_fm_base(
            meta,
            file_path.parent.name,
            allowed,
            item_path,
            'skill.frontmatter',
        )
    )
    if status == 'archived':
        rep = meta.get('replaced_by')
        if not isinstance(rep, str) or not rep.strip():
            diags.append(
                Diagnostic(
                    item_path,
                    'skill.frontmatter',
                    'skill.metadata.missing',
                    "archived skill must specify non-empty 'replaced_by'",
                )
            )

    body_checks = [
        (
            not body.lstrip().startswith('# '),
            "body must start with '# <Title>'",
        ),
        (
            not re.search(r'^## Procedimento\s*$', body, re.M),
            "missing '## Procedimento'",
        ),
        (
            not re.search(r'^## Exemplos\s*$', body, re.M)
            or not re.search(
                r'Por qu[eê] não|Caso negativo|caso negativo', body
            ),
            "'## Exemplos' must contain negative case",
        ),
        (
            not re.search(r'^## Evals de trigger\s*$', body, re.M)
            or not re.search(r'[Nn]ão deve acionar|[Nn]ao deve acionar', body),
            "'## Evals de trigger' must contain 'Não deve acionar'",
        ),
        (
            bool(re.search(r'^## Quando usar\s*$', body, re.M)),
            "forbidden '## Quando usar'",
        ),
    ]
    for failed, msg in body_checks:
        if failed:
            diags.append(
                Diagnostic(
                    item_path,
                    'skill.structure',
                    'skill.document.structure',
                    msg,
                )
            )

    diags.extend(
        check_declared_refs(root, file_path, text, 'skill.references', 'skill')
    )
    diags.extend(check_skill_script_syntax(root, file_path, text))
    return diags


def check_skill_script_syntax(
    root: Path, file_path: Path, text: str
) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    scripts_dir = file_path.parent / 'scripts'
    resolved_root = root.resolve()
    if scripts_dir.is_dir():
        for script_path in sorted(scripts_dir.rglob('*.py')):
            if not script_path.is_file():
                continue
            script_rel = script_path.relative_to(root).as_posix()
            try:
                if not script_path.resolve().is_relative_to(resolved_root):
                    diags.append(
                        Diagnostic(
                            script_rel,
                            'skill.script-syntax',
                            'skill.script-syntax.outside-root',
                            f'script escapes root via symlink: {script_rel}',
                        )
                    )
                    continue
            except OSError:
                continue
            try:
                content = script_path.read_text(encoding='utf-8')
                compile(content, script_rel, 'exec')
            except SyntaxError as exc:
                diags.append(
                    Diagnostic(
                        script_rel,
                        'skill.script-syntax',
                        'skill.script-syntax.invalid',
                        f'syntax error: {exc}',
                    )
                )
            except (UnicodeDecodeError, OSError) as exc:
                diags.append(
                    Diagnostic(
                        script_rel,
                        'skill.script-syntax',
                        'skill.script-syntax.invalid',
                        f'cannot read script: {exc}',
                    )
                )

    tool_ref_pattern = (
        r'(?<![A-Za-z0-9._\-/])\.agents/scripts/[A-Za-z0-9._\-/]+\.py'
    )
    for raw_ref in sorted(set(re.findall(tool_ref_pattern, text))):
        tool_ref = raw_ref.rstrip('.,;:)')
        tool_path = root / tool_ref
        if tool_path.is_file():
            try:
                content = tool_path.read_text(encoding='utf-8')
                compile(content, tool_ref, 'exec')
            except SyntaxError as exc:
                diags.append(
                    Diagnostic(
                        tool_ref,
                        'skill.script-syntax',
                        'skill.script-syntax.invalid',
                        f'syntax error: {exc}',
                    )
                )
            except (UnicodeDecodeError, OSError) as exc:
                diags.append(
                    Diagnostic(
                        tool_ref,
                        'skill.script-syntax',
                        'skill.script-syntax.invalid',
                        f'cannot read script: {exc}',
                    )
                )
    return diags


def validate_agent_item(
    root: Path, file_path: Path, item_path: str, _item_name: str
) -> list[Diagnostic]:
    try:
        text = file_path.read_text(encoding='utf-8')
    except (UnicodeDecodeError, OSError) as exc:
        return [
            Diagnostic(
                item_path,
                'agent.frontmatter',
                'agent.frontmatter.invalid',
                f'file cannot be read as UTF-8: {exc}',
            )
        ]
    diags: list[Diagnostic] = []
    try:
        meta, body = parse_frontmatter(text)
    except ValueError as exc:
        return [
            Diagnostic(
                item_path,
                'agent.frontmatter',
                'agent.frontmatter.invalid',
                str(exc),
            )
        ]
    expected_name = file_path.name.replace('.agent.md', '')
    diags.extend(
        check_fm_base(
            meta,
            expected_name,
            ALLOWED_AGENT_FM,
            item_path,
            'agent.frontmatter',
        )
    )
    if 'mode' in meta and not isinstance(meta['mode'], str):
        diags.append(
            Diagnostic(
                item_path,
                'agent.frontmatter',
                'agent.frontmatter.invalid',
                "'mode' must be a string",
            )
        )
    if 'agents' in meta:
        agents_list = meta['agents']
        if not isinstance(agents_list, list) or any(
            not isinstance(x, str) for x in agents_list
        ):
            diags.append(
                Diagnostic(
                    item_path,
                    'agent.frontmatter',
                    'agent.frontmatter.invalid',
                    "'agents' must be a list of strings",
                )
            )
        else:
            diags.extend(
                Diagnostic(
                    item_path,
                    'agent.frontmatter',
                    'agent.reference.missing',
                    f"missing referenced agent '{subagent}'",
                )
                for subagent in agents_list
                if not (file_path.parent / f'{subagent}.agent.md').exists()
            )
    headings = {
        h.split(' — ')[0].strip()
        for h in re.findall(r'^##\s+(.+?)\s*$', body, re.M)
    }
    missing_sections = [
        s for s in AGENT_REQUIRED_SECTIONS if s not in headings
    ]
    if missing_sections:
        diags.append(
            Diagnostic(
                item_path,
                'agent.structure',
                'agent.document.structure',
                f'missing required sections: {missing_sections}',
            )
        )
    legacy_present = [s for s in AGENT_LEGACY_SECTIONS if s in headings]
    if legacy_present:
        diags.append(
            Diagnostic(
                item_path,
                'agent.structure',
                'agent.document.central-only-section',
                f'legacy central sections present: {legacy_present}',
            )
        )
    diags.extend(
        check_declared_refs(root, file_path, text, 'agent.references', 'agent')
    )
    return diags


def validate_workflow_item(
    root: Path, file_path: Path, item_path: str, _item_name: str
) -> list[Diagnostic]:
    try:
        text = file_path.read_text(encoding='utf-8')
    except (UnicodeDecodeError, OSError) as exc:
        return [
            Diagnostic(
                item_path,
                'workflow.frontmatter',
                'workflow.frontmatter.invalid',
                f'file cannot be read as UTF-8: {exc}',
            )
        ]
    diags: list[Diagnostic] = []
    try:
        meta, body = parse_frontmatter(text)
    except ValueError as exc:
        return [
            Diagnostic(
                item_path,
                'workflow.frontmatter',
                'workflow.frontmatter.invalid',
                str(exc),
            )
        ]
    diags.extend(
        check_fm_base(
            meta, None, ALLOWED_WORKFLOW_FM, item_path, 'workflow.frontmatter'
        )
    )
    if 'category' in meta and not isinstance(meta['category'], str):
        diags.append(
            Diagnostic(
                item_path,
                'workflow.frontmatter',
                'workflow.frontmatter.invalid',
                "'category' must be a string",
            )
        )
    if 'tags' in meta:
        tags_list = meta['tags']
        if not isinstance(tags_list, list) or any(
            not isinstance(x, str) for x in tags_list
        ):
            diags.append(
                Diagnostic(
                    item_path,
                    'workflow.frontmatter',
                    'workflow.frontmatter.invalid',
                    "'tags' must be a list of strings",
                )
            )

    h2_sections = re.split(r'(?m)^##\s+.+$', body)
    has_non_empty_h2 = any(sec.strip() != '' for sec in h2_sections[1:])
    if not has_non_empty_h2:
        diags.append(
            Diagnostic(
                item_path,
                'workflow.structure',
                'workflow.document.structure',
                'workflow must contain at least one non-empty level-two section',
            )
        )
    diags.extend(
        check_declared_refs(
            root, file_path, text, 'workflow.references', 'workflow'
        )
    )
    return diags
