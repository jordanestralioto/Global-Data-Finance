# Monitoramento de Recursos

Documentação do sistema de monitoramento de recursos do Global-Data-Finance.

______________________________________________________________________

## Visão Geral

`ResourceMonitor` mede CPU e memória e oferece operações para o chamador:

- Construtor singleton para uso compartilhado ou `create_isolated()` para isolamento.
- Helpers manuais para calcular workers, batches e aguardar recursos.
- Estados e circuit breaker consultados pelo fluxo que usa o monitor.
- Garbage collection em warning quando habilitado nos limites.

O estado informado não redimensiona automaticamente uma operação em andamento.

______________________________________________________________________

## Estados de Recursos

| Estado        | Descrição                                                                                           | Ação                                         |
| ------------- | --------------------------------------------------------------------------------------------------- | -------------------------------------------- |
| **HEALTHY**   | Memória e CPU abaixo dos limites de aviso                                                            | Nenhuma ação necessária                      |
| **WARNING**   | Limite de aviso de memória ou CPU atingido                                                           | Considera GC quando habilitado               |
| **CRITICAL**  | Limite crítico atingido ou falha na leitura de recursos                                               | Chamador decide reduzir carga                |
| **EXHAUSTED** | Limite de esgotamento de memória atingido, memória livre insuficiente ou circuit breaker ainda ativo | Ativa o circuit breaker quando habilitado    |

Os limites são configuráveis em `ResourceLimits`; o exemplo abaixo mostra os
padrões. CPU alta, isoladamente, chega a `CRITICAL`.

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

`get_process_memory_mb()` usa `0.0` como sentinela quando o `psutil` não pode
ler a telemetria; não é uma medição real de consumo zero. Uma falha conhecida
de telemetria em `check_resources()` produz `ResourceState.CRITICAL`.

______________________________________________________________________

## Política por Fonte

O fluxo CVM usa um semáforo estático de concorrência no
`AsyncDownloadAdapterCVM`; ele não consulta o `ResourceMonitor` para redimensionar
workers durante downloads. O limite é definido por `max_concurrent` na
construção do adapter.

`ResourcePolicyB3` cria um monitor isolado, sem GC em warning e sem usar a
utilização de CPU como gatilho. `fast` calcula o limite de workers pelo número
de fontes, CPUs, RAM disponível e teto `GDF_B3_WORKER_LIMIT` (padrão 4);
`slow` usa um worker. A admissão aguarda memória crítica e falha em exaustão
ou timeout. Helpers manuais do singleton não redimensionam os batches da B3.

______________________________________________________________________

## Exemplo Manual

```python
from globaldatafinance.core import ResourceMonitor, ResourceState

monitor = ResourceMonitor()

# Checar antes de operação pesada
state = monitor.check_resources()

if state == ResourceState.EXHAUSTED:
    print("Recursos críticos! Aguardando...")
    if not monitor.wait_for_resources(timeout_seconds=120):
        raise TimeoutError("Resources remain unavailable")

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
