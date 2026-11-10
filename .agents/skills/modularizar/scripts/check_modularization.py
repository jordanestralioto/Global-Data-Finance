#!/usr/bin/env python3
"""Initialize one refactoring record and check selected extraction results."""

from __future__ import annotations

import argparse
import ast
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parents[1] / 'references/PLAN_TEMPLATE.md'
SKIP_DIRS = frozenset(
    {
        '.git',
        '.agents',
        '.venv',
        'venv',
        '__pycache__',
        '.pytest_cache',
        '.mypy_cache',
        '.ruff_cache',
        'node_modules',
        'vendor',
        'dist',
        'build',
    }
)


def repository_root(explicit: Path | None = None) -> Path:
    """Keep consumer discovery independent from the installed skill location."""
    if explicit is not None:
        root = explicit.resolve()
        if not root.is_dir():
            raise ValueError(f'repository directory does not exist: {root}')
        return root
    cwd = Path.cwd()
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--show-toplevel'],
            cwd=cwd,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return cwd
    return (
        Path(result.stdout.strip()).resolve()
        if (result.returncode == 0 and result.stdout.strip())
        else cwd
    )


def consumer_path(root: Path, raw: str) -> Path:
    """Validate resolved containment while retaining the named legacy path."""
    path = Path(os.path.abspath(root / raw))
    if not path.resolve().is_relative_to(root):
        raise ValueError(f'path is outside the consumer repository: {raw}')
    return path


def raise_walk_error(error: OSError) -> None:
    raise error


def files_under(path: Path) -> list[Path]:
    if path.is_file():
        return [path]
    if not path.is_dir():
        return []
    files: list[Path] = []
    for directory, names, filenames in os.walk(path, onerror=raise_walk_error):
        names[:] = sorted(name for name in names if name not in SKIP_DIRS)
        files.extend(
            Path(directory) / name
            for name in sorted(filenames)
            if not name.endswith(('.pyc', '.pyo'))
        )
    return files


def explicit_export(node: ast.stmt) -> bool:
    if isinstance(node, ast.Expr):
        return isinstance(node.value, ast.Constant) and isinstance(
            node.value.value, str
        )
    if isinstance(node, ast.Import):
        return True
    if isinstance(node, ast.ImportFrom):
        return all(alias.name != '*' for alias in node.names)
    value: ast.expr | None
    if isinstance(node, ast.Assign) and len(node.targets) == 1:
        target, value = node.targets[0], node.value
    elif isinstance(node, ast.AnnAssign):
        target, value = node.target, node.value
    else:
        return False
    return (
        isinstance(target, ast.Name)
        and target.id == '__all__'
        and isinstance(value, (ast.List, ast.Tuple))
        and all(
            isinstance(item, ast.Constant) and isinstance(item.value, str)
            for item in value.elts
        )
    )


def check_file(root: Path, path: Path, max_lines: int) -> list[str]:
    path = consumer_path(root, str(path))
    label = path.relative_to(root).as_posix()
    errors = []
    if path.name.startswith('_') and path.name != '__init__.py':
        errors.append(f'{label}: extracted module has a private basename')
    content = path.read_text(encoding='utf-8')
    count = len(content.splitlines())
    if count > max_lines:
        errors.append(f'{label}: {count} lines exceeds {max_lines}')
    if path.suffix == '.py':
        try:
            tree = ast.parse(content, filename=label)
        except SyntaxError as exc:
            errors.append(f'{label}:{exc.lineno}: invalid Python: {exc.msg}')
        else:
            if path.name == '__init__.py' and not all(
                explicit_export(node) for node in tree.body
            ):
                errors.append(
                    f'{label}: initializer must contain only explicit exports'
                )
    return errors


def imported_names(node: ast.AST, package: tuple[str, ...]) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if not isinstance(node, ast.ImportFrom):
        return []
    prefix = package[: len(package) - node.level + 1] if node.level else ()
    parts = (*prefix, *(node.module.split('.') if node.module else []))
    base = '.'.join(parts)
    return [
        base,
        *(
            '.'.join((*parts, alias.name))
            for alias in node.names
            if alias.name != '*'
        ),
    ]


def check_retired_imports(
    root: Path, python_root: Path, retired: list[str]
) -> tuple[list[str], int]:
    if not python_root.is_dir():
        raise ValueError(
            f'Python source root is not a directory: {python_root}'
        )
    errors = []
    scanned = 0
    for path in files_under(python_root):
        if path.suffix != '.py':
            continue
        path = consumer_path(root, str(path))
        label = path.relative_to(root).as_posix()
        package = path.relative_to(python_root).parent.parts
        content = path.read_text(encoding='utf-8')
        scanned += 1
        try:
            tree = ast.parse(content, filename=label)
        except SyntaxError as exc:
            errors.append(f'{label}:{exc.lineno}: invalid Python: {exc.msg}')
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level > len(package):
                errors.append(
                    f'{label}:{node.lineno}: relative import escapes Python root'
                )
                continue
            errors.extend(
                f'{label}:{getattr(node, "lineno", 0)}: retired import {name}'
                for name in imported_names(node, package)
                if any(
                    name == old or name.startswith(old + '.')
                    for old in retired
                )
            )
    return errors, scanned


def check_extraction(
    root: Path,
    target: Path,
    entrypoint: Path,
    modules: list[Path],
    max_lines: int,
) -> tuple[list[str], list[str]]:
    errors = []
    if target.exists() or target.is_symlink():
        errors.append(
            f'{target.relative_to(root)}: legacy target still exists'
        )
    if not entrypoint.is_file():
        errors.append(
            f'{entrypoint.relative_to(root)}: entrypoint is missing or not a file'
        )
    selected = set()
    for destination in [entrypoint, *modules]:
        files = files_under(destination)
        if not files:
            errors.append(
                f'{destination.relative_to(root)}: no module files found'
            )
        selected.update(files)
    checked = []
    for path in sorted(selected):
        errors.extend(check_file(root, path, max_lines))
        checked.append(path.relative_to(root).as_posix())
    return errors, checked


def initialize_record(
    root: Path, target: Path, record: Path
) -> dict[str, object]:
    if not target.is_file():
        raise ValueError(f'target file does not exist: {target}')
    rendered = (
        TEMPLATE.read_text(encoding='utf-8')
        .replace('{{target}}', target.relative_to(root).as_posix())
        .replace('{{date}}', datetime.now(UTC).date().isoformat())
    )
    record.parent.mkdir(parents=True, exist_ok=True)
    with record.open('x', encoding='utf-8', newline='\n') as output:
        output.write(rendered)
    return {'status': 'created', 'record': record.relative_to(root).as_posix()}


def parser() -> argparse.ArgumentParser:
    command = argparse.ArgumentParser(description=__doc__)
    commands = command.add_subparsers(dest='command', required=True)
    initialize = commands.add_parser(
        'init', help='Create one short refactoring record'
    )
    check = commands.add_parser(
        'check', help='Check selected extraction results'
    )
    for subcommand in (initialize, check):
        subcommand.add_argument(
            '--repo', type=Path, help='Explicit consumer root'
        )
        subcommand.add_argument(
            '--target', required=True, help='Legacy target file'
        )
    initialize.add_argument(
        '--record', required=True, help='Consumer-owned record path'
    )
    check.add_argument(
        '--entrypoint', required=True, help='Canonical public entrypoint'
    )
    check.add_argument(
        '--module',
        action='append',
        required=True,
        help='Extracted file or source directory; repeatable',
    )
    check.add_argument('--max-lines', type=int, default=400)
    check.add_argument(
        '--python-root',
        default='.',
        help='Source root for static Python import resolution',
    )
    check.add_argument(
        '--retired-import',
        action='append',
        default=[],
        help='Retired Python import name; repeatable',
    )
    return command


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        root = repository_root(args.repo)
        target = consumer_path(root, args.target)
        if args.command == 'init':
            report = initialize_record(
                root, target, consumer_path(root, args.record)
            )
            code = 0
        else:
            if args.max_lines < 1:
                raise ValueError('--max-lines must be positive')
            if any(
                not all(part.isidentifier() for part in name.split('.'))
                for name in args.retired_import
            ):
                raise ValueError(
                    '--retired-import requires dotted Python import names'
                )
            errors, checked = check_extraction(
                root,
                target,
                consumer_path(root, args.entrypoint),
                [consumer_path(root, name) for name in args.module],
                args.max_lines,
            )
            scanned = 0
            if args.retired_import:
                import_errors, scanned = check_retired_imports(
                    root,
                    consumer_path(root, args.python_root),
                    args.retired_import,
                )
                errors.extend(import_errors)
            code = 1 if errors else 0
            report = {
                'status': 'failed' if errors else 'passed',
                'errors': errors,
                'checkedFiles': checked,
                'pythonFilesScanned': scanned,
                'retiredImports': args.retired_import,
                'limitations': [
                    'Only selected destinations and the declared Python source root are checked.',
                    'Dynamic imports, other languages and runtime behavior require native validation.',
                    'Markdown approvals and completeness of the extraction inventory are not verified.',
                ],
            }
    except (OSError, UnicodeError, ValueError) as exc:
        report = {'status': 'error', 'errors': [str(exc)]}
        code = 2
    sys.stdout.write(json.dumps(report, indent=2) + '\n')
    return code


if __name__ == '__main__':
    raise SystemExit(main())
