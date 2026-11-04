"""Provide the console progress bar used by file-processing workflows."""

import sys
import time
from types import TracebackType
from typing import Self


class SimpleProgressBar:
    """A small terminal progress bar.

    - Non-blocking: updates only every ~0.1s to reduce console noise.
    - Safe to instantiate with total=0 (no-op printing).
    """

    def __init__(
        self,
        total: int,
        desc: str = '',
        width: int = 40,
        *,
        operation: str = 'download',
    ) -> None:
        """Initialize a progress bar for a known number of items."""
        self.total = max(0, int(total))
        self.desc = desc
        self.width = int(width)
        self.current = 0
        self._last_print_time = 0.0

        if self.total > 0:
            sys.stdout.write(
                f'\n{desc}: Starting {operation} of {self.total} files...\n'
            )
            sys.stdout.flush()

    def __enter__(self) -> Self:
        """Display the initial count before processing any files."""
        self.update(0)
        return self

    def __exit__(
        self,
        _exc_type: type[BaseException] | None,
        _exc_value: BaseException | None,
        _traceback: TracebackType | None,
    ) -> None:
        """Close the output line while preserving errors and cancellation."""
        self.close()

    def update(self, amount: int = 1) -> None:
        """Advance the progress bar by the requested number of items."""
        self.current += int(amount)
        now = time.time()
        if now - self._last_print_time >= 0.1 or self.current >= self.total:
            self._print()
            self._last_print_time = now

    def _print(self) -> None:
        if self.total == 0:
            return
        percent = float(self.current) / float(self.total)
        filled = int(self.width * percent)
        bar = '█' * filled + '░' * (self.width - filled)
        progress_text = (
            f'\r{self.desc} [{bar}] {self.current}/{self.total} '
            f'({percent * 100:.0f}%)'
        )
        sys.stdout.write(progress_text)
        sys.stdout.flush()

    def close(self) -> None:
        """Render the final progress state and terminate its output line."""
        if self.total > 0:
            self._print()
            sys.stdout.write('\n')
            sys.stdout.flush()
