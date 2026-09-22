# Estratégia de Retry

Documentação da estratégia de retry do Global-Data-Finance.

______________________________________________________________________

## Visão Geral

A classe `RetryStrategy` determina quais exceções garantem retry e calcula o tempo de backoff exponencial.

______________________________________________________________________

## Características

- ✅ **Inteligente**: Apenas retries em erros transientes
- ✅ **Backoff Exponencial**: Aumenta tempo de espera progressivamente
- ✅ **Configurável**: Backoff inicial, máximo e multiplicador customizáveis
- ✅ **Type-safe**: Usa hierarquia de exceções do projeto

______________________________________________________________________

## Exceções Retryable

### Sempre Retryable

- `NetworkError` - Erros de rede
- `DownloadTimeoutError` - Timeout de downloads CVM

### Baseado em Mensagem

Erros com keywords retryáveis na mensagem:

- `"timeout"`
- `"connection refused"`
- `"connection reset"`
- `"connection aborted"`
- `"temporarily"`
- `"unavailable"`
- `"try again"`

### Nunca Retryable

- `PathPermissionError` - Sem permissão
- `DiskFullError` - Disco cheio
- `ValueError` - Erro de validação

______________________________________________________________________

## API

### Criar Instância

```python
from globaldatafinance.core.utils.retry_strategy import RetryStrategy

strategy = RetryStrategy(
    initial_backoff=1.0,    # Backoff inicial (segundos)
    max_backoff=60.0,       # Backoff máximo (segundos)
    multiplier=2.0          # Multiplicador exponencial
)
```

### Verificar se Exceção é Retryable

```python
from globaldatafinance.macro_exceptions import NetworkError

try:
    download_file()
except Exception as e:
    if strategy.is_retryable(e):
        print("Erro retryable, tentando novamente")
    else:
        print("Erro não-retryable, parando")
        raise
```

### Calcular Backoff

```python
# Calcula tempo de espera para cada tentativa
for retry_count in range(3):
    backoff = strategy.calculate_backoff(retry_count)
    print(f"Tentativa {retry_count + 1}: esperar {backoff}s")
```

**Exemplo de Saída Estimada (initial=1.0, multiplier=2.0 com jitter multiplicativo limitado [0.5, 1.5])**:

```text
Tentativa 1: esperar ~1.0s (ex.: 0.92s)
Tentativa 2: esperar ~2.0s (ex.: 2.15s)
Tentativa 3: esperar ~4.0s (ex.: 3.80s)
```

> Nota: O método `calculate_backoff` aplica jitter multiplicativo limitado
> aleatório, com fator uniforme entre `0.5` e `1.5`, sobre o valor exponencial
> determinístico. Isso evita colisões simultâneas de retries (*thundering herd
> problem*).

______________________________________________________________________

## Exemplo de Uso

### Retry Manual com Backoff

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

# max_retries conta tentativas adicionais após a primeira execução.
for attempt in range(max_retries + 1):
    try:
        result = download_file()
        break  # Sucesso
    except Exception as e:
        if not strategy.is_retryable(e):
            raise  # Erro não-retryable

        if attempt < max_retries:
            backoff = strategy.calculate_backoff(attempt)
            print(f"Tentativa {attempt + 1} falhou. Aguardando {backoff}s...")
            time.sleep(backoff)
        else:
            raise  # Esgotou tentativas
```

______________________________________________________________________

## Uso Automático nos Adapters

Os adapters de download usam `RetryStrategy` automaticamente:

```python
from globaldatafinance import FundamentalStocksDataCVM

# AsyncDownloadAdapterCVM já implementa retry com backoff
cvm = FundamentalStocksDataCVM()
result = cvm.download(
    destination_path="/data/cvm",
    list_docs=["DFP"],
    initial_year=2023,
    last_year=2023,
)
```

O adapter faz:

1. Tenta download
2. Se falhar, verifica se é retryable
3. Calcula backoff
4. Aguarda e tenta novamente
5. Repete até a execução inicial mais `max_retries` tentativas adicionais, ou sucesso

______________________________________________________________________

## Configuração de Retry

Via configuração global:

```bash
# Máximo de retries
export DATAFINANCE_NETWORK_MAX_RETRIES=5

# Multiplicador de backoff
export DATAFINANCE_NETWORK_RETRY_BACKOFF=2.0
```

______________________________________________________________________

## Exceções do Projeto

O `RetryStrategy` usa as exceções definidas em `macro_exceptions`:

```python
from globaldatafinance.macro_exceptions import (
    NetworkError,          # Erro de rede
    DownloadTimeoutError,  # Timeout de download
    PathPermissionError,   # Sem permissão
    DiskFullError          # Disco cheio
)
```

______________________________________________________________________

## Documentação Relacionada

- [Exceções](../reference/exceptions.md)
- [Configuration](advanced-usage.md#configuracao-global)
- [Advanced Usage](advanced-usage.md)
