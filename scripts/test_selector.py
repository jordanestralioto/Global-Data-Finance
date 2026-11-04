"""Resolve replacement test IDs against one inspected Git state."""

from __future__ import annotations

import ast
from collections.abc import Callable
from pathlib import Path

from scripts.git_changes import read_git_file


def replacement_test_exists(
    replacement_id: str,
    is_test_file: Callable[[str], bool],
    repo_root: Path | None = None,
    revision_range: str | None = None,
) -> bool:
    """Return whether a replacement ID names a real collected test node."""
    file_path, separator, selector = replacement_id.partition('::')
    if (
        not separator
        or not selector.strip()
        or not is_test_file(file_path)
        or Path(file_path).is_absolute()
        or '..' in Path(file_path).parts
    ):
        return False

    source = read_git_file(
        file_path, repo_root=repo_root, revision_range=revision_range
    )
    if source is None:
        return False
    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError:
        return False

    nodes: list[ast.stmt] = tree.body
    segments = selector.split('::')
    for position, segment in enumerate(segments):
        if not segment.isidentifier():
            return False
        node = next(
            (
                candidate
                for candidate in nodes
                if isinstance(
                    candidate,
                    (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef),
                )
                and candidate.name == segment
            ),
            None,
        )
        if node is None:
            return False
        if position == len(segments) - 1:
            return isinstance(
                node, (ast.FunctionDef, ast.AsyncFunctionDef)
            ) and node.name.startswith('test')
        if not isinstance(node, ast.ClassDef):
            return False
        nodes = node.body
    return False
