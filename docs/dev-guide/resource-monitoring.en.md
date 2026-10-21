# Resource Monitoring

Resource measurements, limits, and admission helpers used by Global-Data-Finance.

______________________________________________________________________

## Overview

`ResourceMonitor` measures CPU and memory and offers operations to its caller:

- A singleton constructor for shared use, or `create_isolated()` for isolation.
- Manual helpers to size workers and batches and wait for resources.
- States and a circuit breaker consulted by the flow using the monitor.
- Garbage collection on warning when enabled in the limits.

A reported state does not automatically resize an operation already running.

______________________________________________________________________

## Resource Saturation States

| State         | Description                                                                                         | Action                                    |
| ------------- | --------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| **HEALTHY**   | Memory and CPU below warning thresholds                                                              | No action required                        |
| **WARNING**   | Memory or CPU warning threshold reached                                                              | Considers GC when enabled                 |
| **CRITICAL**  | Critical threshold reached or resource telemetry failed                                              | Caller decides how to reduce work         |
| **EXHAUSTED** | Memory exhaustion threshold reached, insufficient free memory, or circuit breaker still active        | Activates the circuit breaker when enabled |

Thresholds are configurable through `ResourceLimits`; the example below shows
the defaults. High CPU alone reaches `CRITICAL`.

______________________________________________________________________

## Configuration

### Configuring `ResourceLimits`

```python
from globaldatafinance.core import ResourceLimits

limits = ResourceLimits(
    memory_warning_threshold=70.0,      # RAM % threshold triggering WARNING state
    memory_critical_threshold=85.0,     # RAM % threshold triggering CRITICAL state
    memory_exhausted_threshold=95.0,    # RAM % threshold triggering EXHAUSTED state
    cpu_warning_threshold=80.0,         # CPU % threshold triggering WARNING state
    cpu_critical_threshold=90.0,        # CPU % threshold triggering CRITICAL state
    min_free_memory_mb=100,             # Absolute minimum available RAM allowance (MB)
    auto_gc_on_warning=True,            # Automatically fire garbage collector on WARNING
    circuit_breaker_cooldown_seconds=10,# Mandatory rest timeout during breaker trips
    circuit_breaker_enabled=True        # Enable hardware circuit breaker protection
)
```

______________________________________________________________________

## Public API

### Instantiate Singleton Monitor

```python
from globaldatafinance.core import ResourceLimits, ResourceMonitor

# The first initialization defines the active limits.
limits = ResourceLimits(memory_warning_threshold=60.0)
monitor = ResourceMonitor(limits)
# Later calls return the same object and do not replace its limits.
same_monitor = ResourceMonitor(ResourceLimits(memory_warning_threshold=50.0))
assert same_monitor is monitor
assert monitor.limits.memory_warning_threshold == 60.0
```

### Inspect Current Resource State

```python
from globaldatafinance.core import ResourceMonitor

monitor = ResourceMonitor()
state = monitor.check_resources()
print(f"Current telemetry assessment: {state}")  # Returns HEALTHY, WARNING, CRITICAL, or EXHAUSTED
```

### Calculate Safe Worker Concurrency

```python
# Derive permissible concurrent worker allocation matching available memory and cpu room
safe_workers = monitor.get_safe_worker_count(max_workers=16)
print(f"Allocating {safe_workers} worker threads")
```

### Calculate Safe Batch Size

```python
# Dynamically scale data ingestion batch chunking limits
safe_batch = monitor.get_safe_batch_size(desired_batch_size=10000)
print(f"Optimal adjusted batch size: {safe_batch}")
```

### Pause Until Resources Free Up

```python
from globaldatafinance.core import ResourceMonitor, ResourceState

monitor = ResourceMonitor()
success = monitor.wait_for_resources(
    required_state=ResourceState.WARNING,
    timeout_seconds=60
)

if success:
    print("✓ Resource availability restored within operating boundaries")
else:
    print("⚠️ Timeout exceeded awaiting resource release")
```

### Query Current Process RAM Footprint

```python
from globaldatafinance.core import ResourceMonitor

monitor = ResourceMonitor()
memory_mb = monitor.get_process_memory_mb()
print(f"Active process consuming: {memory_mb:.2f} MB")
```

`get_process_memory_mb()` uses `0.0` as a sentinel when `psutil` cannot read
telemetry; it is not a real zero-usage measurement. A known telemetry failure
in `check_resources()` produces `ResourceState.CRITICAL`.

______________________________________________________________________

## Source-Specific Policy

The CVM flow uses a static concurrency semaphore in
`AsyncDownloadAdapterCVM`; it does not query `ResourceMonitor` to resize
workers during downloads. The limit is set by `max_concurrent` when the
adapter is constructed.

`ResourcePolicyB3` creates an isolated monitor, without warning GC or CPU
utilization as a trigger. `fast` bounds workers by source count, CPU count,
available RAM, and `GDF_B3_WORKER_LIMIT` (default 4); `slow` uses one worker.
Admission waits under critical memory and fails on exhaustion or timeout.
The singleton's manual helpers do not resize B3 batches.

______________________________________________________________________

## Practical Standalone Scripting

```python
from globaldatafinance.core import ResourceMonitor, ResourceState

monitor = ResourceMonitor()

# Verify operational headroom prior to running intensive data operations
state = monitor.check_resources()

if state == ResourceState.EXHAUSTED:
    print("System entering EXHAUSTED capacity state! Awaiting cooldown...")
    if not monitor.wait_for_resources(timeout_seconds=120):
        raise TimeoutError("Resources remain unavailable")

# Retrieve safe concurrent worker threshold
workers = monitor.get_safe_worker_count(max_workers=16)
process_data(workers=workers)

# Track memory footprint
memory = monitor.get_process_memory_mb()
print(f"Final runtime consumption: {memory:.2f} MB")
```

______________________________________________________________________

## External Dependencies

The monitoring module utilizes `psutil` to query OS-level process and system metrics. The `psutil` package is a mandatory core dependency of `globaldatafinance` and is installed automatically.

If the installation is incomplete or the module cannot be loaded, importing the package fails explicitly. There is no degraded mode that reports `ResourceState.HEALTHY` without telemetry, because that result could admit work without the memory and CPU safety limits.

______________________________________________________________________

## Related Documentation

- [Retry Strategy Guide](retry-strategy.md) - Exponential retry loop configuration
- [Advanced Usage Guide](advanced-usage.md) - Optimization techniques and workflow integration
