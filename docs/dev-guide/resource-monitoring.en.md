# Resource Monitoring

Comprehensive documentation detailing the telemetry and resource monitoring subsystem built into Global-Data-Finance.

______________________________________________________________________

## Overview

The `ResourceMonitor` class represents an advanced, dynamic CPU and RAM telemetry engine offering:

- ✅ **Singleton Architecture**: Guaranteed singular telemetry instance across application lifecycles
- ✅ **Automated Throttling**: Automatically adjusts concurrent worker limits and batch dimensions according to real-time resources
- ✅ **Circuit Breaker Integration**: Temporarily pauses I/O processing operations whenever hardware saturation reaches critical thresholds
- ✅ **Automated Garbage Collection**: Explicitly invokes memory garbage collection cycles during memory pressure spikes

______________________________________________________________________

## Resource Saturation States

| State Definition | Operational Description              | Triggered Response Action             |
| ---------------- | ------------------------------------ | ------------------------------------- |
| **HEALTHY**      | Normal execution resource footprint  | No throttling or remediation required |
| **WARNING**      | Resource consumption exceeds 70-80%  | Evaluates and registers GC execution  |
| **CRITICAL**     | Consumption exceeds 85-90%           | Downscales workers/batches, forces GC |
| **EXHAUSTED**    | System usage surpasses 95% threshold | Activates execution circuit breaker   |

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

The B3 flow consumes `ResourceMonitor` through `ResourcePolicyB3`. This policy
uses the singleton to limit concurrent files, parsing workers, and batch sizes
according to CPU and memory pressure.

______________________________________________________________________

## Practical Standalone Scripting

```python
from globaldatafinance.core import ResourceMonitor, ResourceState

monitor = ResourceMonitor()

# Verify operational headroom prior to running intensive data operations
state = monitor.check_resources()

if state == ResourceState.EXHAUSTED:
    print("System entering EXHAUSTED capacity state! Awaiting cooldown...")
    monitor.wait_for_resources(timeout_seconds=120)

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
