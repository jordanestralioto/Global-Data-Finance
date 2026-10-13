"""Exclusive CVM destination ownership across threads and processes."""

from __future__ import annotations

import json
import os
import socket
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path

from ....core import get_logger
from ....core.utils import normalize_destination_path
from ....macro_exceptions import ExtractionError, PathIsNotDirectoryError
from .destination_io import (
    DestinationFileOperationsCVM,
    DownloadDestinationSnapshot,
    assert_download_destination_unchanged,
    capture_download_destination,
    open_download_destination,
)

_THREAD_STATE = threading.local()
LOCK_NAME = '.cvm-write-lock'
logger = get_logger(__name__)


@contextmanager
def exclusive_destination(
    destination_path: str,
    *,
    allowed_unc_roots: Sequence[str] | None = None,
    expected_destination: DownloadDestinationSnapshot | None = None,
) -> Iterator[DestinationFileOperationsCVM]:
    """Reject competing writers before ZIP replacement or source reading.

    Nested extraction in the owning finalizer thread shares its lease. A lock
    left by a terminated process is retained for explicit operator inspection.
    """
    owned = getattr(_THREAD_STATE, 'owned', None)
    if owned is None:
        owned = _THREAD_STATE.owned = {}
    raw_destination = Path(destination_path).expanduser().absolute()
    existing = owned.get(raw_destination)
    if existing is not None:
        assert_download_destination_unchanged(
            raw_destination.resolve(), existing.snapshot
        )
        yield existing
        return
    destination = normalize_destination_path(
        destination_path,
        type_label='Destination path',
        empty_message='path cannot be empty or whitespace',
        allowed_unc_roots=allowed_unc_roots,
    )
    if not destination.is_dir():
        raise PathIsNotDirectoryError(
            str(destination), exists=destination.exists()
        )
    if expected_destination is not None:
        assert_download_destination_unchanged(
            destination, expected_destination
        )
    if destination in owned:
        yield owned[destination]
        return
    snapshot = expected_destination or capture_download_destination(
        destination
    )
    with open_download_destination(snapshot) as operations:
        lock = destination / LOCK_NAME
        try:
            operations.mkdir(lock)
        except FileExistsError as error:
            raise ExtractionError(
                str(destination),
                f'CVM destination has an active or unrecovered writer: {lock}',
            ) from error
        with operations.open_child_directory(lock) as lock_operations:
            owner_path = lock / 'owner.json'
            owned[destination] = operations
            try:
                owner = {
                    'pid': os.getpid(),
                    'hostname': socket.gethostname(),
                    'thread': threading.get_ident(),
                }
                lock_operations.write_bytes(
                    owner_path,
                    json.dumps(owner).encode('utf-8'),
                    exclusive=True,
                )
                yield operations
            finally:
                del owned[destination]
                try:
                    lock_operations.unlink(owner_path)
                except FileNotFoundError:
                    logger.warning(
                        'CVM lease owner is missing: %s', owner_path
                    )
                operations.rmdir(lock)
