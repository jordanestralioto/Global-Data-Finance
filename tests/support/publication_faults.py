"""Trace filesystem operations and inject faults in owned test children."""

from __future__ import annotations

import errno
import json
import os
import re
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any
from unittest.mock import patch

from globaldatafinance.macro_infra.transactional_publication import (
    FileOperations,
)
from globaldatafinance.macro_infra.transactional_publication.types import (
    JOURNAL_NAME,
    LOCK_NAME,
)
from tests.support.publication_crashes import CRASH_EXIT

MUTATIONS = frozenset(
    {
        'mkdir',
        'makedirs',
        'mkdtemp',
        'write_bytes',
        'fsync_file',
        'fsync_directory',
        'link',
        'copy2',
        'replace',
        'unlink',
        'rmtree',
    }
)


class FaultOperations(FileOperations):
    """Wrap the real seam without replacing transaction decisions."""

    def __init__(
        self,
        destination: Path,
        connection: Connection,
        *,
        fault: dict[str, Any] | None = None,
        recover: bool = False,
        copy_backups: bool = False,
    ) -> None:
        """Select an operation ordinal and retain an independent trace."""
        self.destination = destination
        self.connection = connection
        self.fault = fault or {}
        self.copy_backups = copy_backups
        self.recover = recover
        self.active = not recover or (destination / LOCK_NAME).exists()
        self.fired = False
        self.events = 0
        self.cleaning = False
        self.phase: str | None = None
        self.delegate = FileOperations()

    def __getattribute__(self, name: str) -> Any:
        """Intercept only the declared filesystem seam operations."""
        if name in MUTATIONS:
            return partial(object.__getattribute__(self, '_perform'), name)
        return object.__getattribute__(self, name)

    def _perform(self, name: str, *args: Any, **kwargs: Any) -> Any:
        if self.active:
            self._point(name, 'before', args)
        previous = self.cleaning
        self.cleaning = previous or name == 'rmtree'
        try:
            if name == 'link' and self.copy_backups:
                raise OSError(errno.EXDEV, 'test requires copy-based backups')
            result = getattr(self.delegate, name)(*args, **kwargs)
        finally:
            self.cleaning = previous
        if name == 'replace' and args[1].name == JOURNAL_NAME:
            self.phase = json.loads(args[1].read_text())['phase']
        if self.active:
            self._point(name, 'after', args)
        if (
            self.recover
            and name == 'rmtree'
            and args[0] == self.destination / LOCK_NAME
        ):
            self.active = False
        return result

    def _point(self, operation: str, edge: str, args: tuple[Any, ...]) -> None:
        event = {
            'index': self.events,
            'operation': operation,
            'edge': edge,
            'phase': self.phase,
            'paths': [
                self._role(arg) for arg in args if isinstance(arg, Path)
            ],
        }
        self.events += 1
        self.connection.send_bytes(json.dumps({'event': event}).encode())
        selected = event['index'] == self.fault.get('index')
        sticky = self.fired and self.fault.get('kind') == 'persistent'
        if not selected and not (sticky and edge == 'before'):
            return
        self.fired = True
        self.connection.send_bytes(b'{"fired": true}')
        fraction = self.fault.get('partial')
        if selected and fraction is not None and edge == 'before':
            self._write_partial(operation, args, fraction)
        if self.fault.get('kind') == 'exit':
            os._exit(CRASH_EXIT)
        raise OSError(
            self.fault['errno'], 'injected publication storage fault'
        )

    def _write_partial(
        self, operation: str, args: tuple[Any, ...], fraction: float
    ) -> None:
        if operation == 'write_bytes':
            path, payload = args
        elif operation == 'copy2':
            path, payload = args[1], args[0].read_bytes()
        else:
            raise AssertionError(f'unsupported partial operation: {operation}')
        size = min(len(payload) - 1, int(len(payload) * fraction))
        self.delegate.write_bytes(path, payload[: max(0, size)])

    def _role(self, path: Path) -> str:
        relative = path.relative_to(self.destination).as_posix()
        relative = re.sub(
            r'(\.globaldatafinance-transaction-)[0-9a-f]{32}-[^/]+',
            r'\1<id>-<stage>',
            relative,
        )
        return re.sub(r'[0-9a-f]{32}', '<id>', relative)

    @contextmanager
    def cleanup_primitives(self) -> Iterator[None]:
        """Expose interrupted child deletion inside the real tree remover."""
        unlink, rmdir = os.unlink, os.rmdir

        def invoke(
            operation: str, original: Any, path: Any, **kwargs: Any
        ) -> None:
            if not self.active or not self.cleaning:
                original(path, **kwargs)
                return
            candidate = Path(path)
            descriptor = kwargs.get('dir_fd')
            if descriptor is not None:
                candidate = (
                    Path(f'/proc/self/fd/{descriptor}').readlink() / candidate
                )
            self._point(operation, 'before', (candidate,))
            original(path, **kwargs)
            self._point(operation, 'after', (candidate,))

        with (
            patch.object(
                os, 'unlink', partial(invoke, 'cleanup.unlink', unlink)
            ),
            patch.object(os, 'rmdir', partial(invoke, 'cleanup.rmdir', rmdir)),
        ):
            yield
