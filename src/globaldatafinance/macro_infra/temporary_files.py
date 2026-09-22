"""Same-directory temporary-file reservation for atomic publication."""

from __future__ import annotations

import contextlib
import os
import tempfile
from pathlib import Path


def reserve_temporary_path(
    target_path: Path,
    *,
    suffix: str,
) -> Path:
    """Reserve a unique hidden temporary file beside the final target.

    Creates a unique file in ``target_path.parent`` using a prefix derived
    from ``target_path.name``. The file descriptor is closed before
    returning so the caller may reopen the path independently.

    The caller owns the returned path after a successful call and is
    responsible for later cleanup.

    Args:
        target_path: Final publication target whose parent directory
            receives the temporary file.
        suffix: File extension for the temporary file (e.g. ``'.part'``).

    Returns:
        A resolved Path to the newly created temporary file.

    Raises:
        OSError: If the file cannot be created or the descriptor cannot
            be closed.
    """
    descriptor, name = tempfile.mkstemp(
        prefix=f'.{target_path.name}.',
        suffix=suffix,
        dir=str(target_path.parent),
    )
    temporary = Path(name)
    try:
        os.close(descriptor)
    except BaseException:
        with contextlib.suppress(BaseException):
            temporary.unlink(missing_ok=True)
        raise
    return temporary
