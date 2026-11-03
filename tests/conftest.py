"""Isolate test subprocesses from the invoking Git repository."""

from collections.abc import Iterator
from pathlib import Path

import pytest

from scripts.process_runner import run_process


@pytest.fixture(scope='session', autouse=True)
def isolate_git_environment() -> Iterator[None]:
    """Keep hook-local repository pointers out of disposable test repos."""
    variables = run_process(
        ['git', 'rev-parse', '--local-env-vars'], cwd=Path.cwd()
    ).stdout.splitlines()
    with pytest.MonkeyPatch.context() as environment:
        for variable in variables:
            environment.delenv(variable, raising=False)
        yield
