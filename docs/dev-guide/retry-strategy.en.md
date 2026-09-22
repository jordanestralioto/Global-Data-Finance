# Retry Strategy

Technical documentation outlining the error retry and back-off strategies enforced within Global-Data-Finance.

______________________________________________________________________

## Overview

The `RetryStrategy` domain class evaluates execution exceptions to determine retry eligibility and computes optimized exponential back-off delays between attempts.

______________________________________________________________________

## Highlights

- ✅ **Transient Intelligence**: Filters failures to trigger retries strictly upon encountering transient network interruptions
- ✅ **Exponential Back-off**: Progressively elongates rest intervals between successive unsuccessful execution attempts
- ✅ **Configurable Thresholds**: Full support for tailoring initial delays, max ceilings, and scaling multiplier coefficients
- ✅ **Type-Safe Hierarchy**: Evaluates errors leveraging the repository's dedicated custom exception hierarchy

______________________________________________________________________

## Retryable Exception Rules

### Always Retryable Exceptions

- `NetworkError` - Connection drops or socket disruptions
- `DownloadTimeoutError` - CVM download timeout failures

### Keyword-Based Exception Matchers

Standard runtime exceptions triggered by underlying transports are marked retryable if their error string matches standard connection keywords:

- `"timeout"`
- `"connection refused"`
- `"connection reset"`
- `"connection aborted"`
- `"temporarily"`
- `"unavailable"`
- `"try again"`

### Never Retryable (Fail-Fast) Exceptions

- `PathPermissionError` - File system authorization blocks
- `DiskFullError` - Local volume capacity exhaustion
- `ValueError` / `InvalidDocumentName` - Invalid API parameters or unapproved inputs

______________________________________________________________________

## Public API

### Instantiate Custom Strategy

```python
from globaldatafinance.core.utils.retry_strategy import RetryStrategy

strategy = RetryStrategy(
    initial_backoff=1.0,    # Base starting backoff delay (in seconds)
    max_backoff=60.0,       # Maximum delay ceiling (in seconds)
    multiplier=2.0          # Exponential multiplier step rate
)
```

### Validate Exception Eligibility

```python
from globaldatafinance.macro_exceptions import NetworkError

try:
    download_file()
except Exception as exc:
    if strategy.is_retryable(exc):
        print("✓ Transient network failure detected, scheduling retry")
    else:
        print("✗ Non-retryable exception encountered, aborting immediately")
        raise
```

### Compute Back-off Durations

```python
# Derive staggered delay schedules across sequential attempts
for retry_count in range(3):
    backoff = strategy.calculate_backoff(retry_count)
    print(f"Attempt {retry_count + 1} scheduling delay: {backoff} seconds")
```

**Sample Estimated Output (initial=1.0, multiplier=2.0 with bounded multiplicative jitter [0.5, 1.5])**:

```text
Attempt 1 scheduling delay: ~1.0 seconds (e.g. 0.92s)
Attempt 2 scheduling delay: ~2.0 seconds (e.g. 2.15s)
Attempt 3 scheduling delay: ~4.0 seconds (e.g. 3.80s)
```

> Note: The `calculate_backoff` method applies bounded multiplicative jitter
> with a uniformly sampled factor between `0.5` and `1.5` on top of the base
> exponential calculation. This prevents thundering-herd retry collisions when
> multiple concurrent downloads fail in lockstep.

______________________________________________________________________

## Practical Implementation Examples

### Manual Defensive Retry Loop

```python
from globaldatafinance.core.utils.retry_strategy import RetryStrategy
from globaldatafinance.macro_exceptions import NetworkError
import time

strategy = RetryStrategy(
    initial_backoff=1.0,
    max_backoff=30.0,
    multiplier=2.0
)

max_retries = 3

# max_retries counts additional attempts after the first execution.
for attempt in range(max_retries + 1):
    try:
        result = download_file()
        break  # Successful execution completion
    except Exception as exc:
        if not strategy.is_retryable(exc):
            raise  # Abort loop on hard system faults

        if attempt < max_retries:
            backoff = strategy.calculate_backoff(attempt)
            print(f"Attempt {attempt + 1} failed. Next attempt scheduled in {backoff}s...")
            time.sleep(backoff)
        else:
            raise  # Exhausted maximum permitted attempts
```

______________________________________________________________________

## Automated Library Adapter Behavior

Concrete download adapters invoke `RetryStrategy` automatically during network operations:

```python
from globaldatafinance import FundamentalStocksDataCVM

# AsyncDownloadAdapterCVM natively integrates automated exponential backoff loops
cvm = FundamentalStocksDataCVM()
result = cvm.download(
    destination_path="/data/cvm",
    list_docs=["DFP"],
    initial_year=2023,
    last_year=2023,
)
```

The underlying adapter execution loop operates as follows:

1. Executes asynchronous HTTP transfer requests
2. If exceptions occur, evaluates if the resulting error matches retryable criteria
3. Computes the required exponential back-off duration
4. Yields worker threads for the duration of the computed back-off interval
5. Repeats until the initial execution plus `max_retries` additional attempts are exhausted, or the operation succeeds

______________________________________________________________________

## Global Environment Retry Customization

Tune global network retry profiles via environment variable declarations:

```bash
# Define maximum connection retry attempts
export DATAFINANCE_NETWORK_MAX_RETRIES=5

# Modify the exponential delay scaling multiplier
export DATAFINANCE_NETWORK_RETRY_BACKOFF=2.0
```

______________________________________________________________________

## Project Exception Definitions

The `RetryStrategy` engine evaluates symbols generated from `macro_exceptions`:

```python
from globaldatafinance.macro_exceptions import (
    NetworkError,          # Transient network communication interruptions
    DownloadTimeoutError,  # Download timeout events
    PathPermissionError,   # Filesystem write boundary lockouts
    DiskFullError          # Storage capacity exhaustion errors
)
```

______________________________________________________________________

## Related Documentation

- [Exception Reference](../reference/exceptions.md) - Deep breakdown of project custom exceptions
- [Global Configuration](advanced-usage.md#global-configuration-tuning) - Tuning parameters and settings
- [Advanced Usage Guide](advanced-usage.md) - Additional workflow customization patterns
