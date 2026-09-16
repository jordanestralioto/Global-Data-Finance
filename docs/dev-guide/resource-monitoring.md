# Monitoramento de Recursos

Documentação do sistema de monitoramento de recursos do Global-Data-Finance.

______________________________________________________________________

## Visão Geral

O `ResourceMonitor` é um sistema avançado de monitoramento de CPU e memória que:

- ✅ **Singleton**: Uma única instância global
- ✅ **Automático**: Ajusta workers e batch sizes baseado em recursos disponíveis
- ✅ **Circuit Breaker**: Para operações quando recursos estão críticos
- ✅ **Garbage Collection**: GC automático quando memória está alta

______________________________________________________________________

## Estados de Recursos

| Estado        | Descrição                | Ação                          |
| ------------- | ------------------------ | ----------------------------- |
| **HEALTHY**   | Recursos normais         | Nenhuma ação necessária       |
| **WARNING**   | Recursos acima de 70-80% | Considera ativar GC           |
| **CRITICAL**  | Recursos acima de 85-90% | Reduz workers/batch, força GC |
| **EXHAUSTED** | Recursos acima de 95%    | Ativa circuit breaker         |

______________________________________________________________________

## Configuração

### ResourceLimits

```python
from globaldatafinance.core import ResourceLimits

limits = ResourceLimits(
    memory_warning_threshold=70.0,      # % de memória para WARNING
    memory_critical_threshold=85.0,     # % de memória para CRITICAL
    memory_exhausted_threshold=95.0,    # % de memória para EXHAUSTED
    cpu_warning_threshold=80.0,         # % de CPU para WARNING
    cpu_critical_threshold=90.0,        # % de CPU para CRITICAL
    min_free_memory_mb=100,             # MB mínimo de memória livre
    auto_gc_on_warning=True,            # GC automático em WARNING
    circuit_breaker_cooldown_seconds=10,# Cooldown do circuit breaker
    circuit_breaker_enabled=True        # Habilitar circuit breaker
)
```

______________________________________________________________________

## API

### Criar Instância (Singleton)

```python
from globaldatafinance.core import ResourceLimits, ResourceMonitor

# Os limites da primeira inicialização tornam-se os limites ativos.
limits = ResourceLimits(memory_warning_threshold=60.0)
monitor = ResourceMonitor(limits)
# Chamadas posteriores devolvem o mesmo objeto e não substituem os limites.
same_monitor = ResourceMonitor(ResourceLimits(memory_warning_threshold=50.0))
assert same_monitor is monitor
assert monitor.limits.memory_warning_threshold == 60.0
```

### Verificar Estado atual

```python
from globaldatafinance.core import ResourceMonitor

monitor = ResourceMonitor()
state = monitor.check_resources()
print(state)  # HEALTHY, WARNING, CRITICAL, ou EXHAUSTED
```

### Calcular Workers Seguros

```python
# Número seguro de workers baseado em recursos
safe_workers = monitor.get_safe_worker_count(max_workers=16)
print(f"Usando {safe_workers} workers")
```

### Calcular Batch Size Seguro

```python
# Tamanho de batch seguro baseado em memória
safe_batch = monitor.get_safe_batch_size(desired_batch_size=10000)
print(f"Batch size: {safe_batch}")
```

### Aguardar Recursos Disponíveis

```python
from globaldatafinance.core import ResourceMonitor, ResourceState

monitor = ResourceMonitor()
success = monitor.wait_for_resources(
    required_state=ResourceState.WARNING,
    timeout_seconds=60
)

if success:
    print("Recursos disponíveis")
else:
    print("Timeout aguardando recursos")
```

### Memória do Processo Atual

```python
from globaldatafinance.core import ResourceMonitor

monitor = ResourceMonitor()
memory_mb = monitor.get_process_memory_mb()
print(f"Processo usando {memory_mb:.2f} MB")
```

______________________________________________________________________

## Política por Fonte

O fluxo CVM usa um semáforo estático de concorrência no
`AsyncDownloadAdapterCVM`; ele não consulta o `ResourceMonitor` para redimensionar
workers durante downloads. O limite é definido por `max_concurrent` na
construção do adapter.

O fluxo B3 usa `ResourceMonitor` por meio de `ResourcePolicyB3`. Essa política
consulta o singleton para limitar arquivos concorrentes, workers de parsing e
tamanhos de batch conforme a pressão de CPU e memória.

______________________________________________________________________

## Exemplo Manual

```python
from globaldatafinance.core import ResourceMonitor, ResourceState

monitor = ResourceMonitor()

# Checar antes de operação pesada
state = monitor.check_resources()

if state == ResourceState.EXHAUSTED:
    print("Recursos críticos! Aguardando...")
    monitor.wait_for_resources(timeout_seconds=120)

# Ajustar workers baseado em recursos
workers = monitor.get_safe_worker_count(max_workers=16)
process_data(workers=workers)

# Verificar memória do processo
memory = monitor.get_process_memory_mb()
print(f"Processo usando {memory:.2f} MB")
```

______________________________________________________________________

## Dependência

O monitoramento utiliza `psutil` para consultar métricas do sistema operacional. O pacote `psutil` é uma dependência obrigatória do `globaldatafinance` e é instalado automaticamente.

Se a instalação estiver incompleta ou o módulo não puder ser carregado, a importação falhará explicitamente. Não há modo degradado que reporte `ResourceState.HEALTHY` sem telemetria, pois esse resultado poderia liberar processamento sem os limites de segurança de memória e CPU.

______________________________________________________________________

## Documentação Relacionada

- [Retry Strategy](retry-strategy.md)
- [Advanced Usage](advanced-usage.md)
