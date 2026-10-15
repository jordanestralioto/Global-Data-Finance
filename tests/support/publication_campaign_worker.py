"""Run traced transactions in disposable Linux child processes."""

from __future__ import annotations

import json
import multiprocessing
import time
from multiprocessing.connection import Connection
from pathlib import Path
from typing import Any

from globaldatafinance.macro_exceptions import ExtractionError, SecurityError
from tests.support.publication_crashes import ARTIFACT_NAMES, run_worker
from tests.support.publication_faults import FaultOperations


def _error_details(error: Exception) -> list[dict[str, Any]]:
    chain = []
    current: BaseException | None = error
    while current is not None:
        chain.append(
            {
                'type': type(current).__name__,
                'errno': getattr(current, 'errno', None),
                'message': str(current),
            }
        )
        current = current.__cause__ or current.__context__
    return chain


def _child(
    connection: Connection,
    destination: Path,
    payloads: dict[str, bytes],
    action: str,
    copy_backups: bool,
    fault: dict[str, Any] | None,
) -> None:
    operations = FaultOperations(
        destination,
        connection,
        fault=fault,
        recover=action != 'commit',
        copy_backups=copy_backups,
    )
    error = None
    try:
        with operations.cleanup_primitives():
            repetitions = 3 if action == 'repeat' else 1
            for _ in range(repetitions):
                run_worker(
                    destination,
                    '',
                    action,
                    operations=operations,
                    payloads=payloads,
                )
    except (
        OSError,
        ExtractionError,
        SecurityError,
        ValueError,
        RuntimeError,
    ) as failure:
        error = _error_details(failure)
    connection.send_bytes(json.dumps({'error': error}).encode())
    connection.close()


def run_child(
    destination: Path,
    payload_root: Path,
    *,
    action: str = 'commit',
    copy_backups: bool = False,
    fault: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fork only the single-threaded campaign launcher, never pytest itself."""
    payloads = {
        name: (payload_root / f'new-{name}').read_bytes()
        for name in ARTIFACT_NAMES
    }
    context = multiprocessing.get_context('fork')
    receiving, sending = context.Pipe(duplex=False)
    process = context.Process(
        target=_child,
        args=(sending, destination, payloads, action, copy_backups, fault),
    )
    process.start()
    sending.close()
    result: dict[str, Any] = {'events': [], 'fired': False, 'error': None}
    deadline = time.monotonic() + 30
    try:
        while True:
            if time.monotonic() > deadline:
                raise TimeoutError('campaign child exceeded 30 seconds')
            if not receiving.poll(0.1):
                if not process.is_alive():
                    break
                continue
            try:
                message = json.loads(receiving.recv_bytes())
            except EOFError:
                break
            if 'event' in message:
                result['events'].append(message['event'])
            else:
                result.update(message)
        process.join(timeout=5)
        if process.is_alive():
            raise TimeoutError(
                'campaign child did not exit after closing trace'
            )
        result['exit_code'] = process.exitcode
        return result
    finally:
        receiving.close()
        if process.is_alive():
            process.kill()
            process.join(timeout=5)
        process.close()
