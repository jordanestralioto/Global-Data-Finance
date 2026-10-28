# Estratégia de Retry

Documentação da estratégia de retry do Global-Data-Finance.

______________________________________________________________________

## Visão Geral

A classe `RetryStrategy` classifica exceções por tipo e mensagem e calcula o
backoff exponencial com jitter. O chamador decide quando repetir a operação.

______________________________________________________________________

## Características

- Classificação por exceção, com fallback para palavras na mensagem.
- Backoff exponencial com jitter multiplicativo e teto configurável.
- Exclusões explícitas para `PathPermissionError`, `DiskFullError` e `ValueError`.

______________________________________________________________________

## Exceções Retryable

### Sempre Retryable

- `NetworkError` - Erros de rede
- `DownloadTimeoutError` - Timeout de downloads CVM

### Baseado em Mensagem

Para qualquer outra exceção não excluída, a estratégia procura estas palavras
na mensagem convertida para minúsculas:

- `"timeout"`
- `"connection refused"`
- `"connection reset"`
- `"connection aborted"`
- `"temporarily"`
- `"unavailable"`
- `"try again"`

Esse fallback também aceita uma exceção genérica, como
`Exception("Operation timeout occurred")`. A mensagem não comprova que a
falha é transitória. Ao usar retry manual, escolha operações idempotentes ou
aplique sua própria classificação antes de repetir uma alteração de estado.

### Nunca Retryable

- `PathPermissionError` - Sem permissão
- `DiskFullError` - Disco cheio
- `ValueError` - Erro de validação

### Status HTTP nos downloads CVM

O adaptador CVM classifica o status HTTP antes de traduzir a falha para
`NetworkError`. Apenas `408`, `429`, `500`, `502`, `503` e `504` permitem
retry. Os demais status, incluindo `403`, `404` e `410`, encerram a tentativa
sem backoff adicional. O diagnóstico mantém o status original. A seleção por
status tem precedência sobre palavras presentes na mensagem ou no URL;
timeouts e falhas de conexão continuam usando a estratégia compartilhada.

### Limites e redirects HTTP

O limite de bytes do download exige `Accept-Encoding: identity`. Respostas
com outra codificação HTTP são rejeitadas antes da leitura, inclusive em
redirects; a compressão interna do ZIP continua permitida e passa pelos
limites próprios de extração. O contador limita também corpos intermediários
de redirects sem `Content-Length`. Chamadas ao adaptador compartilhado sem
limite de bytes mantêm a decodificação HTTP existente.

Downloads com codificação HTTP `identity` conferem o tamanho recebido contra
o `Content-Length` válido da própria resposta GET. Uma divergência rejeita
e remove apenas o staging da tentativa; na CVM, ela entra na política de
retry de falhas de transporte. Metadados ausentes ou inválidos não dispensam
os limites de bytes nem a validação completa do ZIP. A CVM não consulta HEAD
depois do download, evitando comparar representações de versões diferentes
quando a origem republica o arquivo.

HEAD também solicita `identity` e fecha corpos sem ler ou decodificar,
inclusive em redirects. O header `Content-Length` é preservado como metadado
do recurso; seu valor não é tratado como tamanho de um corpo HEAD.

No adaptador HTTP compartilhado, redirects que mudam esquema, host ou porta
retêm somente `Accept`, `Accept-Encoding`, `Accept-Language`, `Connection`,
`Host` e `User-Agent`. Credenciais e headers personalizados ficam restritos à
origem inicial. A configuração de headers da CVM fornece `User-Agent` quando
informado.

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
