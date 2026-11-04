"""Controlled child for cooperative preflight cancellation checks."""

import os
import time

from globaldatafinance.brazil.b3_data.historical_quotes import async_execution


def cancellable_annual(_candidates, year, selection):
    marker = selection.directory / f'{year}-{os.getpid()}'
    marker.with_suffix('.started').write_text(str(os.getpid()))
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            async_execution.check_phase_cancellation()
            time.sleep(0.01)
        raise AssertionError('Worker was not cancelled')
    finally:
        marker.with_suffix('.stopped').write_text(str(os.getpid()))
