"""Descriptor bridge validation retains directory identity protections."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from globaldatafinance.brazil.cvm.fundamental_stocks_data import destination_io
from globaldatafinance.macro_exceptions import SecurityError

pytestmark = pytest.mark.unit


@pytest.mark.parametrize('changed', ['entry', 'child'])
def test_traversable_descriptor_paths_reject_different_directory_identity(
    monkeypatch: pytest.MonkeyPatch, changed: str
) -> None:
    """Traversable bridges reject redirected entries and child directories."""
    expected = os.stat_result((0, 1, 2, 0, 0, 0, 0, 0, 0, 0))
    different = os.stat_result((0, 3, 4, 0, 0, 0, 0, 0, 0, 0))
    opened: list[int] = []
    closed: list[int] = []

    def open_directory(*_args: Any, **_kwargs: Any) -> int:
        opened.append(11)
        return 11

    monkeypatch.setattr(
        destination_io, '_DESCRIPTOR_ROOTS', (Path('/descriptor-root'),)
    )
    monkeypatch.setattr(
        Path,
        'stat',
        lambda _path: different if changed == 'entry' else expected,
    )
    monkeypatch.setattr(
        os,
        'fstat',
        lambda descriptor: (
            different if descriptor == 11 and changed == 'child' else expected
        ),
    )
    monkeypatch.setattr(os, 'O_DIRECTORY', 0, raising=False)
    monkeypatch.setattr(os, 'open', open_directory)
    monkeypatch.setattr(os, 'close', closed.append)

    with pytest.raises(SecurityError, match=r'changed.*identity'):
        destination_io._descriptor_directory(10)

    assert closed == opened
