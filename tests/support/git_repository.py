"""Disposable Git repositories for quality-gate tests."""

from __future__ import annotations

from pathlib import Path

from scripts.process_runner import ProcessResult, run_process


def run_git(repo: Path, *args: str) -> ProcessResult:
    """Run a Git command in an isolated test repository."""
    return run_process(['git', *args], cwd=repo)


def initialize_git_repository(repo: Path) -> None:
    """Initialize a disposable repository with deterministic metadata."""
    run_git(repo, 'init', '--quiet')
    run_git(repo, 'config', 'user.name', 'Quality Gate Tests')
    run_git(repo, 'config', 'user.email', 'quality-gates@example.invalid')


def run_gate(script: Path, repo: Path, *arguments: str) -> ProcessResult:
    """Execute a gate script from an isolated repository."""
    return run_process(
        ['python', str(script), *arguments],
        cwd=repo,
        check=False,
    )
