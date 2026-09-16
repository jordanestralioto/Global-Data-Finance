"""Build safe local targets for files downloaded from CVM URLs."""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path
from urllib.parse import unquote, urlsplit

from ....core.archive_names import validate_portable_basename
from ....core.utils import assert_path_not_sensitive
from ....macro_exceptions import SecurityError


def build_download_target_path(
    url: str,
    dest_path: str,
    *,
    allowed_unc_roots: Sequence[str] | None = None,
) -> Path:
    """Return a validated destination for the URL's final path component."""
    filename = _filename_from_url(url)
    destination = Path(dest_path).expanduser().resolve()
    assert_path_not_sensitive(
        destination,
        dest_path,
        allowed_unc_roots=allowed_unc_roots,
    )
    target = (destination / filename).resolve()
    if not target.is_relative_to(destination):
        raise SecurityError(
            'Downloaded URL filename escapes its destination',
            path=filename,
        )
    return target


def _filename_from_url(url: str) -> str:
    """Extract one safe, platform-independent basename from a URL."""
    try:
        url_path = urlsplit(url).path
    except ValueError as error:
        raise SecurityError('Downloaded URL has an invalid path') from error

    raw_filename = url_path.rsplit('/', maxsplit=1)[-1]
    filename = 'download' if not raw_filename else unquote(raw_filename)
    try:
        validate_portable_basename(filename)
    except ValueError as error:
        raise SecurityError(
            'Downloaded URL does not contain a safe basename',
            path=filename,
        ) from error
    return filename
