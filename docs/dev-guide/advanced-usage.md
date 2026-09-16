# Uso Avançado

Técnicas avançadas e customização do Global-Data-Finance.

______________________________________________________________________

## Core Utilities

### Sistema de Logging

Habilite logging profissional para rastreamento e debugging:

```python
from globaldatafinance import FundamentalStocksDataCVM
from globaldatafinance.core.logging_config import (
    LoggingSettings,
    get_logger,
    log_execution_time,
    setup_logging,
)

# Configurar logging
setup_logging(LoggingSettings(level="INFO", log_file="app.log"))

# Obter logger
logger = get_logger(__name__)
cvm = FundamentalStocksDataCVM()

# Logging estruturado
logger.info(
    "Download iniciado",
    extra={"doc_type": "DFP", "year": 2023}
)

# Performance timing
with log_execution_time(logger, "Download CVM", total=5):
    result = cvm.download(
        destination_path="/data/cvm",
        list_docs=["DFP"],
        initial_year=2023,
        last_year=2023,
    )
```

[Ver documentação completa →](logging-system.md)

O logger `globaldatafinance` começa silencioso com `NullHandler` e
`propagate=False`; `setup_logging()` não altera o root logger da aplicação.
Reconfigurações substituem apenas handlers gerenciados. Se a preparação ou a
troca falhar, a configuração anterior é restaurada. `LoggingSettings` rejeita
campos extras e variáveis `DATAFIN_LOG_*` desconhecidas, incluindo o removido
`structured`.

### Configuração Global

Customize network settings via environment variables:

A biblioteca lê os valores padrão e as variáveis `DATAFINANCE_*` do ambiente
do processo. Ela não procura nem carrega automaticamente um arquivo `.env` a
partir do diretório de trabalho atual. Em casos avançados, os consumidores
podem passar `_env_file=...` diretamente para `Settings` quando quiserem que o
pydantic-settings carregue um arquivo explicitamente; isso não adiciona uma
opção dotenv às facades públicas.

```bash
# Aumentar timeout para conexões lentas
export DATAFINANCE_NETWORK_TIMEOUT=900

# Mais tentativas de retry
export DATAFINANCE_NETWORK_MAX_RETRIES=10

# Backoff mais agressivo
export DATAFINANCE_NETWORK_RETRY_BACKOFF=3.0
```

```python
from globaldatafinance import FundamentalStocksDataCVM, HistoricalQuotesB3
from globaldatafinance.core.config import NetworkSettings, Settings

# Snapshot imutável a partir do ambiente atual
settings = Settings()
print(f"Timeout: {settings.network.timeout}s")
print(f"Max retries: {settings.network.max_retries}")

# Configuração explícita injetada nas fachadas públicas
custom_settings = Settings(network=NetworkSettings(timeout=300))
cvm = FundamentalStocksDataCVM(settings=custom_settings)
b3 = HistoricalQuotesB3(settings=custom_settings)
```

### Limites de ZIP e destinos UNC

Os limites de arquivos também pertencem a `Settings`, aplicam-se tanto à CVM
quanto à B3 e são validados antes de qualquer extração. Os defaults são 2 GiB
para o ZIP compactado e para cada membro, 8 GiB descompactados no total, 10.000
membros e razão máxima de compressão de 200. Valores inválidos falham na
inicialização da configuração, não durante uma escrita parcial.

```bash
export DATAFINANCE_ARCHIVE_MAX_ARCHIVE_BYTES=2147483648
export DATAFINANCE_ARCHIVE_MAX_MEMBERS=10000
export DATAFINANCE_ARCHIVE_MAX_MEMBER_UNCOMPRESSED_BYTES=2147483648
export DATAFINANCE_ARCHIVE_MAX_TOTAL_UNCOMPRESSED_BYTES=8589934592
export DATAFINANCE_ARCHIVE_MAX_COMPRESSION_RATIO=200

# UNC permanece negado por padrão. A lista JSON só deve conter raízes confiáveis.
export DATAFINANCE_PATH_SAFETY_ALLOWED_UNC_ROOTS='["\\\\fileserver\\finance\\exports"]'
```

Raízes POSIX, roots de drive Windows, diretórios Windows de sistema e shares
UNC não autorizados são recusados antes de criar diretórios. Mesmo com uma
allowlist, shares administrativos terminados em `$` continuam proibidos. Essa
política reduz escrita acidental em destinos sensíveis; não limita um chamador
que já possui os privilégios do processo.

Os limites de ZIP vivem no namespace canônico `Settings.archive`; não use o
nome removido `Settings.archive_safety`. O helper de CRC diferencia
`infos=None` (validar o diretório central) de `infos=[]` (seleção vazia já
validada).

### Resource Monitoring

Monitore e gerencie recursos automaticamente:

```python
from globaldatafinance.core import ResourceMonitor, ResourceState

# Criar monitor
monitor = ResourceMonitor()

# Verificar estado
state = monitor.check_resources()
if state == ResourceState.CRITICAL:
    print("Recursos críticos!")

# Calcular workers seguros
safe_workers = monitor.get_safe_worker_count(max_workers=16)
print(f"Usando {safe_workers} workers")

# Aguardar recursos disponíveis
monitor.wait_for_resources(timeout_seconds=120)
```

[Ver documentação completa →](resource-monitoring.md)

`ResourceMonitor` mantém seu contrato singleton; o caminho B3 usa uma
instância isolada quando precisa de limites próprios, sem substituir o
singleton global. O cache privado dos módulos PyArrow também é lazy e só é
preenchido quando a operação Parquet é realmente usada.

### Retry Strategy

Implemente retry customizado:

```python
from globaldatafinance.core.utils.retry_strategy import RetryStrategy
import time

strategy = RetryStrategy(
    initial_backoff=1.0,
    max_backoff=30.0,
    multiplier=2.0
)

max_retries = 5  # Tentativas adicionais após a primeira execução.
for attempt in range(max_retries + 1):
    try:
        result = risky_operation()
        break
    except Exception as e:
        if not strategy.is_retryable(e):
            raise

        if attempt < max_retries:
            backoff = strategy.calculate_backoff(attempt)
            print(f"Retry {attempt + 1} após {backoff}s...")
            time.sleep(backoff)
        else:
            raise
```

[Ver documentação completa →](retry-strategy.md)

______________________________________________________________________

## Customização de Adapters

O adapter HTTP (`AsyncDownloadAdapterCVM`) e o adapter de extração (`ParquetExtractorAdapterCVM`) operam como classes concretas com contratos limpos e bem definidos. O orquestrador (`DownloadDocumentsUseCaseCVM`) aceita qualquer objeto que exponha o método público (`download_docs(tasks)`), utilizando duck typing. Para substituir o adapter, basta passar uma classe alternativa que implemente o mesmo contrato de métodos.

### Substituir o Adapter HTTP

```python
from globaldatafinance.brazil.cvm.fundamental_stocks_data.client import (
    DownloadDocumentsUseCaseCVM,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.core import (
    DownloadResultCVM,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.http import (
    DownloadTaskCVM,
)


class MyCustomAdapter:
    """Adapter alternativo de download (duck-typed)."""

    def download_docs(
        self,
        tasks: list[DownloadTaskCVM],
        *,
        automatic_extractor: bool | None = None,
    ) -> DownloadResultCVM:
        # tasks é uma lista de DownloadTaskCVM: (url, doc_name, year, destination_path).
        # Implemente sua lógica (wget, aiohttp, gsutil, etc.) e devolva o objeto de resultado.
        return DownloadResultCVM(
            successful_downloads=["DFP_2023"],
            failed_downloads={},
            elapsed_time=0.0,
        )


adapter = MyCustomAdapter()
use_case = DownloadDocumentsUseCaseCVM(repository=adapter)
result = use_case.execute(
    destination_path="./dados_cvm",
    list_docs=["DFP"],
    initial_year=2023,
    last_year=2023,
)
```

> O sistema foi desenhado visando clareza e extensibilidade: o orquestrador interage com adaptadores através do seu contrato público de métodos (duck typing), permitindo que customizações sejam injetadas sem burocracia ou herança complexa. Veja `docs/dev-guide/architecture.md` para detalhes.

______________________________________________________________________

## Logging Avançado

### Configuração Personalizada

```python
import logging
from globaldatafinance.core import get_logger

# Criar logger personalizado
logger = get_logger("meu_modulo")

# Adicionar handler para arquivo
file_handler = logging.FileHandler("globaldatafinance.log")
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Usar
logger.info("Iniciando processamento...")
```

______________________________________________________________________

## Processamento Paralelo

### Múltiplos Anos em Paralelo

O extrator B3 aceita `COTAHIST_A{YYYY}.ZIP` ou `.TXT`; se os dois formatos do mesmo ano estiverem no diretório, somente o ZIP será processado.

```python
from concurrent.futures import ProcessPoolExecutor
from globaldatafinance import HistoricalQuotesB3

def extract_year(year):
    b3 = HistoricalQuotesB3()
    return b3.extract(
        path_of_docs="/data/cotahist",
        assets_list=["ações"],
        initial_year=year,
        last_year=year,
        output_filename=f"acoes_{year}"
    )

years = range(2020, 2024)
with ProcessPoolExecutor(max_workers=4) as executor:
    results = list(executor.map(extract_year, years))

for year, result in zip(years, results):
    print(f"{year}: {result['total_records']:,} registros")
```

______________________________________________________________________

## Integração com Frameworks

!!! note "Dependências Opcionais"

    Frameworks de orquestração mencionados nesta seção (`apache-airflow`, `prefect`) são dependências externas opcionais:

    ```bash
    pip install apache-airflow prefect
    ```

### Apache Airflow

```python
from airflow import DAG
from airflow.operators.python import PythonOperator
from datetime import datetime
from globaldatafinance import FundamentalStocksDataCVM

def download_cvm_task():
    cvm = FundamentalStocksDataCVM()
    cvm.download(
        destination_path="/data/cvm",
        list_docs=["DFP"],
        initial_year=2023
    )

with DAG(
    'cvm_download_dag',
    start_date=datetime(2024, 1, 1),
    schedule_interval='@daily'
) as dag:

    download = PythonOperator(
        task_id='download_cvm',
        python_callable=download_cvm_task
    )
```

### Prefect

```python
from prefect import flow, task
from globaldatafinance import FundamentalStocksDataCVM, HistoricalQuotesB3

@task
def download_cvm():
    cvm = FundamentalStocksDataCVM()
    cvm.download(
        destination_path="/data/cvm",
        list_docs=["DFP"],
        initial_year=2023
    )

@task
def extract_b3():
    b3 = HistoricalQuotesB3()
    return b3.extract(
        path_of_docs="/data/cotahist",
        assets_list=["ações"],
        initial_year=2023
    )

@flow
def financial_data_pipeline():
    download_cvm()
    result = extract_b3()
    return result

# Executar
if __name__ == "__main__":
    financial_data_pipeline()
```

______________________________________________________________________

## Otimizações de Performance

### Projeção de colunas e filtro em batches

```python
import pyarrow.compute as pc
import pyarrow.parquet as pq

# Ler somente as colunas necessárias em batches limitados
parquet = pq.ParquetFile("cotahist.parquet")
for batch in parquet.iter_batches(
    batch_size=100_000,
    columns=["data_pregao", "ticker", "preco_fechamento"],
):
    petr4 = batch.filter(pc.equal(batch.column("ticker"), "PETR4"))
    process_chunk(petr4)
```

Polars não é dependência de runtime. Aplicações que o utilizem como leitor
downstream devem declarar essa dependência no próprio ambiente.

### Processamento em Batches (Streaming com PyArrow)

```python
import pyarrow.parquet as pq

# Processar arquivo Parquet grande em batches com streaming
parquet_file = pq.ParquetFile("cotahist.parquet")
for batch in parquet_file.iter_batches(batch_size=100000):
    process_chunk(batch)
```

O import dos módulos PyArrow usados pela escrita permanece lazy e cacheado
privadamente: a dependência só é carregada quando o caminho Parquet é
executado.

______________________________________________________________________

## Monitoramento e Métricas

### Tracking de Progresso

```python
from tqdm import tqdm
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()

years = range(2020, 2024)
for year in tqdm(years, desc="Extraindo anos"):
    result = b3.extract(
        path_of_docs="/data/cotahist",
        assets_list=["ações"],
        initial_year=year,
        last_year=year
    )
```

______________________________________________________________________

## Próximos Passos

- [Arquitetura](architecture.md)
- [Exemplos Práticos](../user-guide/examples.md)
