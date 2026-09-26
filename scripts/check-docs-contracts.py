"""Validate Markdown documentation contracts and code blocks.

Enforces:
1. Bilingual parity & structural alignment between PT-BR (.md) and EN (.en.md).
2. Code block syntax integrity (valid AST, imports, context, and colons).
3. Admonition syntax integrity (bodies and multiline paragraphs are indented).
4. No 4-backtick markdown blocks.
5. Contract compliance (symbols, methods, required args, and source semantics).
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

if __package__ in {None, ''}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.docs_contract_ast import SourceContracts, load_source_contracts
from scripts.docs_contract_code_blocks import check_ast_nodes
from scripts.docs_contract_public_rules import (
    check_b3_internal_readme_contract,
    check_public_b3_api_contract,
    check_public_b3_asset_semantics,
    check_public_b3_signature_contract,
    check_public_cvm_api_contract,
)
from scripts.docs_contract_rules import KNOWN_IMPORTS as KNOWN_IMPORTS
from scripts.docs_contract_rules import (
    check_bilingual_contract_markers,
    check_logging_contract,
    check_public_b3_contract,
    check_test_module_commands,
    documentation_files,
)

DOCS_DIR = Path(__file__).resolve().parents[1] / 'docs'
SOURCE_CONTRACTS = load_source_contracts(DOCS_DIR.parent)


def check_bilingual_parity(docs_dir: Path) -> list[str]:
    """Check PT-BR files for English counterparts and structural alignment."""
    errors: list[str] = []
    pt_files = {
        p for p in docs_dir.rglob('*.md') if not p.name.endswith('.en.md')
    }

    for pt_file in sorted(pt_files):
        en_file = pt_file.with_name(pt_file.name[:-3] + '.en.md')
        if not en_file.exists():
            errors.append(
                f'{pt_file}:1: missing English counterpart: {en_file}'
            )
            continue

        pt_content = pt_file.read_text(encoding='utf-8')
        en_content = en_file.read_text(encoding='utf-8')
        pt_h2 = len(re.findall(r'^##\s+', pt_content, re.MULTILINE))
        en_h2 = len(re.findall(r'^##\s+', en_content, re.MULTILINE))
        if pt_h2 != en_h2:
            errors.append(
                f'{pt_file}:1: H2 section count mismatch with EN '
                f'({pt_h2} vs {en_h2})'
            )
        errors.extend(check_bilingual_contract_markers(pt_file, en_file))

    return errors


def _admonition_error(file_path: Path, line_number: int) -> str:
    """Format an unindented admonition diagnostic."""
    return f'{file_path}:{line_number}: unindented line inside admonition body'


def _advance_blank_lines(lines: list[str], index: int) -> int:
    """Advance past consecutive blank lines and return the next index."""
    while index < len(lines) and not lines[index].strip():
        index += 1
    return index


def _is_admonition_terminator(line: str) -> bool:
    """Return whether a structural Markdown line ends an admonition."""
    return line.startswith(('#', '___', '---', '!!!', '```', '|'))


def _inspect_admonition_body(
    file_path: Path,
    lines: list[str],
    body_start: int,
) -> tuple[int, list[str]]:
    """Inspect one admonition body and return its next unconsumed line."""
    index = _advance_blank_lines(lines, body_start)
    if index >= len(lines):
        return index, [f'{file_path}:{body_start}: empty admonition block']
    if not lines[index].startswith(('    ', '\t')):
        return index, [_admonition_error(file_path, index + 1)]

    while index < len(lines):
        if lines[index].startswith(('    ', '\t')):
            index += 1
            continue
        if lines[index].strip():
            return index, [_admonition_error(file_path, index + 1)]

        index = _advance_blank_lines(lines, index)
        if index >= len(lines) or _is_admonition_terminator(lines[index]):
            return index, []
        if not lines[index].startswith(('    ', '\t')):
            return index, [_admonition_error(file_path, index + 1)]
    return index, []


def check_markdown_formatting(file_path: Path, content: str) -> list[str]:
    """Check fences and paragraph indentation inside admonition callouts."""
    errors: list[str] = []
    lines = content.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        if line.startswith('````'):
            errors.append(f'{file_path}:{i + 1}: 4-backtick fence found')

        if line.startswith('!!!'):
            i, admonition_errors = _inspect_admonition_body(
                file_path, lines, i + 1
            )
            errors.extend(admonition_errors)
            continue
        i += 1

    return errors


def extract_code_blocks(content: str) -> list[tuple[int, str, str]]:
    """Extract code blocks with line number, language tag, and content."""
    blocks: list[tuple[int, str, str]] = []
    lines = content.splitlines()
    in_block = False
    block_start = 0
    lang = ''
    block_lines: list[str] = []

    for idx, line in enumerate(lines, 1):
        if not in_block:
            if line.startswith('```') and not line.startswith('````'):
                in_block = True
                block_start = idx
                lang = line[3:].strip()
                block_lines = []
        else:
            if line.startswith('```'):
                in_block = False
                blocks.append((block_start, lang, '\n'.join(block_lines)))
            else:
                block_lines.append(line)

    return blocks


def check_python_blocks(
    file_path: Path,
    start_line: int,
    lang: str,
    code: str,
    contracts: SourceContracts = SOURCE_CONTRACTS,
) -> list[str]:
    """Validate python code blocks for AST syntax and contracts."""
    errors: list[str] = []
    lang_lower = lang.lower()

    if lang_lower not in ('python', 'py'):
        return errors

    lines = code.splitlines()
    for offset, line in enumerate(lines):
        stripped = line.strip()
        if (
            stripped.startswith('def ')
            and '->' in stripped
            and not stripped.endswith((':', 'pass', '...'))
        ):
            has_colon = any(
                fwd.strip().endswith(':') for fwd in lines[offset:]
            )
            if not has_colon:
                errors.append(
                    f'{file_path}:{start_line + offset}: signature missing '
                    'trailing colon'
                )
    try:
        tree = ast.parse(code)
        errors.extend(
            check_ast_nodes(file_path, start_line, tree, code, contracts)
        )
    except SyntaxError as e:
        errors.append(
            f'{file_path}:{start_line + (e.lineno or 1) - 1}: SyntaxError in '
            f'python code block: {e.msg}'
        )
    return errors


def check_file_contracts(
    file_path: Path,
    content: str,
    contracts: SourceContracts = SOURCE_CONTRACTS,
) -> list[str]:
    """Validate specific contractual guarantees per documentation file."""
    errors = check_public_b3_contract(file_path, content)
    errors.extend(
        check_public_b3_asset_semantics(file_path, content, contracts)
    )
    errors.extend(check_b3_internal_readme_contract(file_path, content))
    errors.extend(check_test_module_commands(file_path, content))
    errors.extend(check_public_b3_api_contract(file_path, content, contracts))
    errors.extend(
        check_public_b3_signature_contract(
            file_path, extract_code_blocks(content), contracts
        )
    )
    errors.extend(check_public_cvm_api_contract(file_path, content, contracts))
    fname = file_path.name

    if 'logging-system' in fname:
        errors.extend(
            check_logging_contract(file_path, extract_code_blocks(content))
        )

    if 'b3-docs' in fname:
        if '010' not in content or '020' not in content:
            errors.append(
                f'{file_path}:1: b3-docs must document spot (010) and '
                'fractional (020) TPMERC codes'
            )
        if (
            'COTAHIST_A' not in content
            or 'ZIP' not in content
            or 'TXT' not in content
        ):
            errors.append(
                f'{file_path}:1: b3-docs must document COTAHIST_A with ZIP '
                'and TXT support'
            )

    if 'faq' in fname:
        benchmark_page = (
            'benchmarks.en.md' if fname.endswith('.en.md') else 'benchmarks.md'
        )
        measured_modes = all(
            re.search(
                rf'^\|[^\n]*\*\*{mode}\*\*[^\n]*\d+(?:[.,]\d+)?\s+MiB\b',
                content,
                flags=re.MULTILINE,
            )
            for mode in ('fast', 'slow')
        )
        benchmark_link = re.search(
            rf'\[[^\]]+\]\(\.\./dev-guide/{re.escape(benchmark_page)}\)',
            content,
        )
        if not measured_modes or benchmark_link is None:
            errors.append(
                f'{file_path}:1: faq must report measured fast and slow '
                'peak RSS in MiB and link to the benchmark evidence'
            )

    return errors


def main() -> int:
    """Run documentation contract checks and report deterministic findings."""
    all_errors: list[str] = []
    repo_root = DOCS_DIR.parent

    if not DOCS_DIR.exists():
        print(f'Docs directory {DOCS_DIR} not found', file=sys.stderr)
        return 1

    all_errors.extend(check_bilingual_parity(DOCS_DIR))

    for md_file in documentation_files(repo_root):
        content = md_file.read_text(encoding='utf-8')
        all_errors.extend(check_markdown_formatting(md_file, content))
        all_errors.extend(check_file_contracts(md_file, content))

        blocks = extract_code_blocks(content)
        for start_line, lang, code in blocks:
            all_errors.extend(
                check_python_blocks(
                    md_file, start_line, lang, code, SOURCE_CONTRACTS
                )
            )

    if all_errors:
        for err in all_errors:
            print(err)
        return 1

    print('All documentation contracts passed successfully.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
