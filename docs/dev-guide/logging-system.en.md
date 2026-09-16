# Logging System

Complete technical reference covering the advanced centralized logging infrastructure implemented across Global-Data-Finance.

______________________________________________________________________

## Overview

Global-Data-Finance incorporates a professional centralized logging subsystem designed specifically for high-throughput library distribution:

- ✅ **Lazy Initialization**: Logging remains silently disabled by default (respecting standard Python library citizenship practices)
- ✅ **Multi-Target Handlers**: Configurable simultaneous routing to console outputs and filesystem files
- ✅ **Granular Level Filtering**: Full support for standard severity thresholds (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`)
- ✅ **Performance Benchmarking**: Integrated timing context managers designed to capture operation latencies automatically
- ✅ **Structured Metadata Binding**: Context-aware log emission supporting structured parameter propagation
- ✅ **Environment Override Compatibility**: Runtime configuration via confirmed OS environment variables

______________________________________________________________________

## Initial State and Isolation

Importing the library does not configure the application root logger or attach
visible output handlers. The `globaldatafinance` logger starts with a
`NullHandler` and `propagate=False`, so events remain quiet until the consumer
explicitly calls `setup_logging()`. Configuration affects only this logger
hierarchy.

`LoggingSettings` accepts only its documented fields: `level`, `format`,
`log_file`, and `detailed_format`. Extra fields, including the removed
`structured` field, raise `ValidationError`.

Supported environment variables are `DATAFIN_LOG_LEVEL`,
`DATAFIN_LOG_FORMAT`, `DATAFIN_LOG_FILE`, and
`DATAFIN_LOG_DETAILED_FORMAT`. `DATAFIN_LOG_LOG_FILE` is also accepted for
compatibility with the field-derived name. Any other `DATAFIN_LOG_*` variable,
including `DATAFIN_LOG_STRUCTURED`, raises `ValidationError` when
`LoggingSettings()` is created.

The formatter performs best-effort redaction for common URL parameters and
sensitive context fields such as `token`, `password`, `authorization`, and
`cookie`. This does not replace the consumer's responsibility: secrets must
not be passed in messages, exceptions, or logging context.

`log_file` must point to a consumer-approved application path. Before creating
directories or the file, `setup_logging()` rejects system roots, protected
directories, and untrusted UNC destinations using the same path-safety policy
as the data facades. Use an application-owned directory or `/tmp` for local
diagnostics.

## Reconfiguration and Rollback

`setup_logging()` builds and configures every candidate handler before touching
the package logger. On success, only library-managed handlers are replaced;
external handlers are preserved. If file creation or the handler swap fails,
the candidates are closed and the previous level, propagation setting, and
handlers are restored.

This lets applications reconfigure library logging without losing the active
configuration:

```python
from globaldatafinance.core.logging_config import LoggingSettings, setup_logging

setup_logging(LoggingSettings(level="INFO"))
setup_logging(LoggingSettings(level="DEBUG", log_file="app-debug.log"))
```

## Architecture

### Primary Subsystem Components

```text
src/core/logging_config.py
├── setup_logging()           # Subsystem configuration entrypoint
├── get_logger()              # Module logger registry retrieval
├── log_execution_time()      # Latency tracking performance context manager
├── log_with_context()        # Structured key-value event logger
├── LoggingSettings           # Pydantic configuration container
├── StructuredFormatter       # Custom formatting layout engine
└── ContextFilter             # Metadata enrichment logging filter
```

______________________________________________________________________

## Basic Usage

### 1. Enable Library Logging

In accordance with Python best practices for dependency distributions, logging is **disabled by default**. To activate event reporting:

```python
from globaldatafinance.core.logging_config import LoggingSettings, setup_logging

# Activate logging across the library hierarchy at severity INFO
setup_logging(LoggingSettings(level="INFO"))
```

### 2. Retrieve a Module Logger Instance

```python
from globaldatafinance.core.logging_config import get_logger

logger = get_logger(__name__)
logger.info("Processing job started")
logger.debug("Detailed debug tracing")
logger.warning("Potential configuration warning")
logger.error("Exception encountered during operational step")
```

### 3. Structured Context Logging

```python
logger.info(
    "Dataset normalization completed",
    extra={
        "file_target": "dfp_cia_aberta_2023.csv",
        "records": 1000,
        "elapsed_ms": 250
    }
)
```

**Console Output**:

```text
2025-11-25 17:30:00 | INFO     | my_pipeline_module | Dataset normalization completed | file_target=dfp_cia_aberta_2023.csv | records=1000 | elapsed_ms=250
```

______________________________________________________________________

## Configuration

### Severity Level Thresholds

| Severity Level | Operational Scope                         | Typical Example Event                              |
| -------------- | ----------------------------------------- | -------------------------------------------------- |
| **DEBUG**      | Deep diagnostic execution traces          | Variable parameter inspections, worker loop steps  |
| **INFO**       | Standard operational lifecycle metrics    | "Download initiated", "Parquet file persisted"     |
| **WARNING**    | Recoverable anomalies or degradations     | "Target archive exists, skipping", "Timeout retry" |
| **ERROR**      | Non-fatal operation exceptions            | "Failed downloading individual DFP table slice"    |
| **CRITICAL**   | Severe failures impacting overall runtime | "Storage exhaustion detected", "Out of memory"     |

### Programmatic Configuration

```python
from globaldatafinance.core.logging_config import LoggingSettings, setup_logging

# Standard activation
setup_logging(LoggingSettings(level="INFO"))

# Route logging outputs directly to a filesystem log destination
setup_logging(
    LoggingSettings(
        level="DEBUG",
        log_file="/tmp/datafinance/execution.log",
    )
)

# Enable detailed formatting (includes precise line numbers and symbol signatures)
setup_logging(
    LoggingSettings(
        level="DEBUG",
        detailed_format=True,
    )
)
```

### Environment Variable Configuration

Confirmed environment configuration parameter names:

```bash
# Define threshold level
export DATAFIN_LOG_LEVEL=DEBUG

# Direct logging output to file destination
export DATAFIN_LOG_FILE=/tmp/datafin.log

# Enable detailed structural reporting
export DATAFIN_LOG_DETAILED_FORMAT=true
```

Unknown `DATAFIN_LOG_*` variables are rejected so removed or misspelled
options cannot appear to have been applied.

```python
from globaldatafinance.core.logging_config import setup_logging

# Ingest settings directly from environment declarations (default LoggingSettings snapshot)
setup_logging()
```

______________________________________________________________________

## Advanced Capabilities

### Performance Timing & Latency Profiling

Leverage the automated `log_execution_time()` context manager to track operational durations:

```python
from globaldatafinance.core.logging_config import log_execution_time, get_logger

logger = get_logger(__name__)

with log_execution_time(logger, "Parse COTAHIST ZIP archive", file_target="COTAHIST_A2023.ZIP"):
    parse_file("COTAHIST_A2023.ZIP")
```

**Console Output**:

```text
Starting: Parse COTAHIST ZIP archive | operation=Parse COTAHIST ZIP archive | file_target=COTAHIST_A2023.ZIP
Completed: Parse COTAHIST ZIP archive | operation=Parse COTAHIST ZIP archive | elapsed_seconds=2.45 | file_target=COTAHIST_A2023.ZIP
```

Upon encountering runtime failures:

```text
Failed: Parse COTAHIST ZIP archive | operation=Parse COTAHIST ZIP archive | elapsed_seconds=1.23 | error=File not found | file_target=COTAHIST_A2023.ZIP
```

### Contextual Event Reporting

```python
from globaldatafinance.core.logging_config import log_with_context, get_logger

logger = get_logger(__name__)

log_with_context(
    logger,
    "info",
    "Parallel download batch completed",
    url="https://example.com/bundle.zip",
    file_target="bundle.zip",
    size_mb=125.5,
    duration_seconds=45
)
```

### Confirming Active Configuration State

```python
from globaldatafinance.core.logging_config import (
    LoggingSettings,
    is_logging_configured,
    setup_logging,
)

if not is_logging_configured():
    setup_logging(LoggingSettings(level="INFO"))
```

### Configuration Snapshot

`setup_logging()` returns the immutable `LoggingSettings` snapshot applied to the library hierarchy:

```python
from globaldatafinance.core.logging_config import LoggingSettings, setup_logging

settings = setup_logging(LoggingSettings(level="INFO"))
print(f"Active threshold level: {settings.level}")
print(f"Registered file sink: {settings.log_file}")
print(f"Detailed syntax enabled: {settings.detailed_format}")
```

______________________________________________________________________

## Practical Examples

### Example 1: Standard Application Logging Integration

```python
from globaldatafinance import FundamentalStocksDataCVM
from globaldatafinance.core.logging_config import (
    LoggingSettings,
    get_logger,
    setup_logging,
)

# Activate operational logging
setup_logging(LoggingSettings(level="INFO", log_file="pipeline.log"))

logger = get_logger(__name__)
logger.info("Application execution commenced")

# Execute library operations
cvm = FundamentalStocksDataCVM()
cvm.download(
    destination_path="/data/cvm",
    list_docs=["DFP"],
    initial_year=2023
)

logger.info("Application execution finished successfully")
```

### Example 2: Diagnostic Debugging Configuration

```python
from globaldatafinance import HistoricalQuotesB3
from globaldatafinance.core.logging_config import LoggingSettings, setup_logging

# Enable DEBUG intensity alongside detailed function line signatures
setup_logging(
    LoggingSettings(
        level="DEBUG",
        log_file="/tmp/datafinance_debug.log",
        detailed_format=True,
    )
)

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=2023
)
```

### Example 3: Dedicated Module Logger Patterns

```python
# my_processing_pipeline.py
from globaldatafinance import FundamentalStocksDataCVM
from globaldatafinance.core.logging_config import (
    LoggingSettings,
    get_logger,
    log_execution_time,
    setup_logging,
)

setup_logging(LoggingSettings(level="INFO"))
logger = get_logger(__name__)

def process_financial_filings():
    logger.info("Starting filing processing workflow")

    with log_execution_time(logger, "CVM Document Extraction"):
        cvm = FundamentalStocksDataCVM()
        cvm.download(
            destination_path="/data/cvm",
            list_docs=["DFP"],
            initial_year=2023
        )

    logger.info("Workflow execution completed cleanly")

if __name__ == "__main__":
    process_financial_filings()
```

______________________________________________________________________

## Log Layout specifications

### Default Syntax

```text
2025-11-25 17:30:00 | INFO     | module.name | Log text content
```

### Detailed Syntax

Appends exact module line numbering and caller function terminology:

```text
2025-11-25 17:30:00 | INFO     | module.name:123 | caller_function_name | Log text content
```

### Context-Enriched Syntax

```text
2025-11-25 17:30:00 | INFO     | module.name | Message | key1=value1 | key2=value2
```

______________________________________________________________________

## Best Practices

### 1. Consistently Register Module Hierarchies via `get_logger(__name__)`

```python
# ✅ Correct - preserve clean namespace nesting
logger = get_logger(__name__)

# ❌ Discouraged - using isolated literal identifier names
logger = get_logger("my_logger")
```

### 2. Match Severity Levels Accurately to Impact

```python
# ✅ Correct usage
logger.debug("Inspected iteration state variable: %s", value)
logger.info("Extraction loop commenced")
logger.warning("Archive verification checksum bypassed")
logger.error("Failed decompressing archive file", exc_info=True)

# ❌ Discouraged usage
logger.info("Loop index variable: %s", value)  # Should utilize DEBUG
logger.error("Completed extraction step")      # Should utilize INFO
```

### 3. Rely on Structured Metadata Dictionaries

```python
# ✅ Correct - explicit structured field assignment
logger.info(
    "Dataframe normalized",
    extra={"file_target": "cotahist.parquet", "size_mb": 10.5}
)

# ❌ Discouraged - mixing unparseable values within string interpolation
logger.info(f"File cotahist.parquet processed with size: 10.5 MB")
```

### 4. Harness Context Managers for Latency Profiling

```python
# ✅ Correct - automated exception tracking and duration timing
with log_execution_time(logger, "Download Workflow"):
    time.sleep(1)

# ❌ Discouraged - manual timer bookkeeping
start = time.time()
time.sleep(1)
logger.info(f"Execution took {time.time() - start} seconds")
```

______________________________________________________________________

## Troubleshooting

### Log outputs are not displayed in the console

```python
# Confirm explicit initialization was performed
from globaldatafinance.core.logging_config import LoggingSettings, setup_logging
setup_logging(LoggingSettings(level="INFO"))
```

### Duplicate log statements emitting simultaneously

```python
# Re-invoking setup_logging() safely replaces only library-managed handlers
setup_logging(LoggingSettings(level="DEBUG"))
```

### Filesystem log generation fails with permissions exceptions

```python
# Use an application-owned directory or /tmp; roots and protected directories
# are rejected before any creation or write.
setup_logging(LoggingSettings(level="INFO", log_file="/tmp/app.log"))
```

______________________________________________________________________

## Related Documentation

- [Global Configuration](advanced-usage.md#global-configuration-tuning) - Settings & environment variables
- [Advanced Usage](advanced-usage.md) - Deep optimization patterns and integration recipes
