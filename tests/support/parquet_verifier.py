"""Read campaign outputs in an isolated persistent Parquet process."""

from __future__ import annotations

import json
import multiprocessing
from contextlib import AbstractContextManager
from multiprocessing.connection import Connection
from pathlib import Path
from types import TracebackType

from tests.support.publication_crashes import ARTIFACT_NAMES


def _verify_parquet(destination: Path) -> None:
    from pyarrow import parquet

    for name in ARTIFACT_NAMES:
        path = destination / name
        if not path.exists():
            continue
        table = parquet.read_table(path, use_threads=False)
        assert table.column_names == ['version', 'item']
        versions = set(table['version'].to_pylist())
        assert versions in ({'old'}, {'new'})
        assert table.num_rows == (1 if versions == {'old'} else 2)
        assert set(table['item'].to_pylist()) == {name}


def _serve(connection: Connection) -> None:
    try:
        while payload := connection.recv_bytes():
            failure = None
            try:
                _verify_parquet(Path(payload.decode()))
            except (OSError, ValueError, AssertionError) as error:
                failure = f'{type(error).__name__}: {error}'
            connection.send_bytes(json.dumps(failure).encode())
    finally:
        connection.close()


class ParquetVerifier(AbstractContextManager['ParquetVerifier']):
    """Reuse imports without ever forking a process containing Arrow pools."""

    def __init__(self) -> None:
        """Spawn the verifier independently of the single-threaded launcher."""
        context = multiprocessing.get_context('spawn')
        self.connection, child = context.Pipe()
        self.process = context.Process(target=_serve, args=(child,))
        self.process.start()
        child.close()
        self.exit_code: int | None = None

    def verify(self, destination: Path) -> None:
        """Require genuine Parquet schema, rows, version, and item readback."""
        self.connection.send_bytes(str(destination).encode())
        if not self.connection.poll(30):
            raise TimeoutError('Parquet verifier exceeded 30 seconds')
        failure = json.loads(self.connection.recv_bytes())
        if failure is not None:
            raise AssertionError(f'Parquet readback failed: {failure}')

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exception: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Reap the owned verifier after successful or failed cases."""
        try:
            if self.process.is_alive():
                self.connection.send_bytes(b'')
        finally:
            self.connection.close()
            self.process.join(timeout=5)
            if self.process.is_alive():
                self.process.kill()
                self.process.join(timeout=5)
            self.exit_code = self.process.exitcode
            self.process.close()
