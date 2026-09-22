# Exceções

Catálogo completo de exceções do Global-Data-Finance.

______________________________________________________________________

## Visão Geral

O Global-Data-Finance adota uma política rigorosa de tratamento de erros:

- **Validação Antecipada (Fail-Fast)**: Erros de parâmetros de entrada, tipos de documentos, classes de ativos ou caminhos inseguros disparam exceções tipadas de forma síncrona antes do início das operações de I/O.
- **Resiliência em Rede**: Em downloads assíncronos da CVM, falhas transitórias de conexão acionam retries automáticos com backoff exponencial. Falhas persistentes são agregadas no atributo `failed_downloads` do `DownloadResultCVM`, sem abortar downloads de outros arquivos.
- **Hierarquia Clara**: Não há exceção genérica fictícia (como `GlobalDataFinanceError`); cada fonte e infraestrutura possui classes específicas e previsíveis.

______________________________________________________________________

## Exceções de Infraestrutura (`macro_exceptions`)

As exceções de infraestrutura representam erros transversais de sistema de arquivos, rede, validação de caminhos e integridade de arquivos.

### Sistema de Arquivos e Permissões

#### `InvalidDestinationPathError`

```python
class InvalidDestinationPathError(ValueError):
    """Caminho de destino inválido ou bloqueado por política de segurança."""
```

- **Herança**: `ValueError`
- **Quando ocorre**: Caminho de destino aponta para diretório de sistema protegido, arquivo em vez de pasta, ou viola regras de traversal.

#### `PathIsNotDirectoryError`

```python
class PathIsNotDirectoryError(ValueError):
    """Caminho fornecido não é um diretório."""
```

- **Herança**: `ValueError`

#### `PathPermissionError`

```python
class PathPermissionError(OSError):
    """Permissão insuficiente para criar ou acessar diretório."""
```

- **Herança**: `OSError`

#### `PathCreationError`

```python
class PathCreationError(OSError):
    """Falha ao criar diretório no sistema de arquivos."""
```

- **Herança**: `OSError`

#### `FileWriteError` e `ParquetWriteError`

```python
class FileWriteError(OSError):
    """Falha ao gravar arquivo no disco."""


class ParquetWriteError(OSError):
    """Falha ao serializar ou gravar arquivo Parquet."""
```

- **Herança**: `OSError`

Na escrita staged de Parquet CVM, falhas de filesystem diferentes de
`ENOSPC` são reportadas como `ParquetWriteError` e preservam a causa original;
`ENOSPC` continua sendo `DiskFullError`. A agregação de downloads registra
`ParquetWrite: ...` e mantém o ZIP para diagnóstico.

#### `DiskFullError`

```python
class DiskFullError(OSError):
    """Espaço em disco insuficiente."""
```

- **Herança**: `OSError`

### Operações de Extração e Arquivos

#### `EmptyDirectoryError`

```python
class EmptyDirectoryError(Exception):
    """Diretório de entrada fisicamente vazio."""
```

- **Quando ocorre**: Somente quando o diretório de entrada está fisicamente vazio.
  Um diretório que não está vazio, mas não contém COTAHIST correspondente ao
  ano solicitado, retorna um resultado vazio (`success=True`, `total_files=0`,
  `total_records=0`, `output_file=""` e `errors={}`).

#### `ExtractionError` e `CorruptedZipError`

```python
class ExtractionError(Exception):
    """Erro durante o processo de extração de dados."""


class CorruptedZipError(ExtractionError):
    """Arquivo ZIP corrompido ou ilegível."""
```

- **Herança**: `CorruptedZipError` herda de `ExtractionError`.

#### `SecurityError`

```python
class SecurityError(Exception):
    """Violação de segurança detectada em operações de arquivo ou caminho."""
```

### Rede e HTTP de Baixo Nível

#### `NetworkError` e `DownloadTimeoutError`

```python
class NetworkError(Exception):
    """Falha de conectividade traduzida durante downloads CVM."""


class DownloadTimeoutError(Exception):
    """Tempo limite de requisição excedido durante downloads CVM."""
```

- **Origem e Tradução no Pipeline**:
  1. O adapter HTTP de baixo nível (`RequestsAdapter.async_download_file`) executa o streaming via `httpx` e pode propagar exceções de transporte (`httpx.RequestError`, `httpx.HTTPStatusError`, `httpx.TimeoutException`, `ConnectionError`) ou erros de escrita em disco.
  2. O adapter CVM (`AsyncDownloadAdapterCVM._download_with_retry`) intercepta essas exceções de transporte e as traduz para as exceções de domínio `NetworkError` e `DownloadTimeoutError`.
  3. A camada `RetryStrategy` aplica tentativas automáticas com recuo exponencial (*exponential backoff*).
  4. Falhas persistentes após o esgotamento dos retries são consolidadas no dicionário `result.failed_downloads` do `DownloadResultCVM`, sem abortar downloads concorrentes de outros anos ou documentos.

______________________________________________________________________

## Exceções CVM (`fundamental_stocks_data.errors`)

Todas as exceções específicas da CVM herdam de `CvmError`.

```python
class CvmError(Exception):
    """Exceção base para todas as falhas de domínio CVM."""
```

### `InvalidDocumentName` e `InvalidDocumentType`

```python
class InvalidDocumentName(CvmError):
    """Nome ou código de documento CVM inválido."""


class InvalidDocumentType(CvmError):
    """Tipo de dado inválido para a lista de documentos."""
```

- **Quando ocorrem**: Documento não pertence ao catálogo oficial (`"DFP"`, `"ITR"`, `"FCA"`, `"FRE"`, `"CGVN"`, `"VLMO"`, `"IPE"`), ou o parâmetro não é uma lista/string válida.

### `InvalidFirstYear` e `InvalidLastYear`

```python
class InvalidFirstYear(CvmError):
    """Ano inicial fora do intervalo permitido para o documento."""


class InvalidLastYear(CvmError):
    """Ano final inválido ou menor que o ano inicial."""
```

- **Quando ocorrem**: Ano informado é inferior ao ano mínimo histórico daquele documento ou superior ao ano corrente do sistema.

### `EmptyDocumentListError` e `MissingDownloadUrlError`

```python
class EmptyDocumentListError(CvmError):
    """Nenhum documento disponível para download após resolução interna."""


class MissingDownloadUrlError(CvmError):
    """URL de download não configurada para o documento solicitado."""
```

- **Nota de semântica**: Na API pública `FundamentalStocksDataCVM.download()`, passar `list_docs=None` ou `list_docs=[]` é interpretado como solicitação de **todos os documentos disponíveis**. `EmptyDocumentListError` é uma exceção interna usada quando a resolução de URLs resulta em conjunto vazio.

______________________________________________________________________

## Exceções B3 (`historical_quotes.errors`)

Exceções do domínio de cotações históricas da B3. Todas as classes concretas
herdam de `B3Error`, que é a fronteira de captura específica da fonte.

### `InvalidAssetsName` e `EmptyAssetListError`

```python
class B3Error(Exception):
    """Base das exceções do domínio B3."""


class InvalidAssetsName(B3Error):
    """Classe de ativo não suportada pela B3."""


class EmptyAssetListError(B3Error):
    """Lista de classes de ativos vazia."""
```

- **Quando ocorrem**: `assets_list` está vazia ou contém identificadores fora do catálogo suportado (`'ações'`, `'etf'`, `'opções'`, `'termo'`, `'exercicio_opcoes'`, `'forward'`, `'leilao'`).

### `InvalidProcessingMode`

```python
class InvalidProcessingMode(B3Error):
    """Modo de processamento inválido (deve ser 'fast' ou 'slow')."""
```

### `InvalidOutputFilename`

```python
class InvalidOutputFilename(B3Error):
    """Nome de arquivo de saída inválido (deve ser apenas basename sem caminhos)."""
```

- **Quando ocorre**: `output_filename` contém barras (`/` ou `\`) ou `..`. O sufixo `.parquet` é opcional e é acrescentado automaticamente quando omitido.

### `InvalidFirstYear` e `InvalidLastYear` (B3)

```python
class InvalidFirstYear(B3Error):
    """Ano inicial inferior a 1986 ou superior ao ano atual."""


class InvalidLastYear(B3Error):
    """Ano final inferior ao ano inicial ou superior ao ano atual."""
```

______________________________________________________________________

## Hierarquia de Exceções

```
Exception
├── macro_exceptions
│   ├── EmptyDirectoryError
│   ├── NetworkError
│   ├── DownloadTimeoutError
│   ├── ExtractionError
│   │   └── CorruptedZipError
│   └── SecurityError
├── CvmError
│   ├── InvalidDocumentName
│   ├── InvalidDocumentType
│   ├── InvalidFirstYear
│   ├── InvalidLastYear
│   ├── EmptyDocumentListError
│   └── MissingDownloadUrlError
└── B3Error
    ├── InvalidAssetsName
    ├── EmptyAssetListError
    ├── InvalidProcessingMode
    ├── InvalidOutputFilename
    ├── InvalidFirstYear
    └── InvalidLastYear

ValueError
├── InvalidDestinationPathError
└── PathIsNotDirectoryError

OSError
├── PathPermissionError
├── PathCreationError
├── FileWriteError
├── ParquetWriteError
└── DiskFullError
```

______________________________________________________________________

## Exemplos de Tratamento

### Exemplo 1: Tratamento na API CVM

```python
from globaldatafinance import FundamentalStocksDataCVM
from globaldatafinance.brazil.cvm.fundamental_stocks_data.errors import (
    CvmError,
    InvalidDocumentName,
    InvalidFirstYear,
    InvalidLastYear,
)
from globaldatafinance.macro_exceptions import (
    InvalidDestinationPathError,
    PathPermissionError,
)

cvm = FundamentalStocksDataCVM()

try:
    # 1. Validação síncrona de parâmetros e diretórios
    result = cvm.download(
        destination_path="/data/cvm",
        list_docs=["DFP"],
        initial_year=2022,
        last_year=2023,
    )

    # 2. Inspeção do resultado agregado (falhas de rede são retentadas e reportadas no resultado)
    if result.has_errors():
        print(f"Houve {result.error_count_downloads} falha(s) persistente(s):")
        for doc_key, message in result.failed_downloads.items():
            print(f"  • {doc_key}: {message}")
    else:
        print(f"Sucesso: {result.success_count_downloads} arquivos baixados.")

except InvalidDocumentName as exc:
    print(f"Documento inválido: {exc}")
except (InvalidFirstYear, InvalidLastYear) as exc:
    print(f"Intervalo de anos inválido: {exc}")
except InvalidDestinationPathError as exc:
    print(f"Caminho de destino inseguro ou inválido: {exc}")
except PathPermissionError as exc:
    print(f"Sem permissão no diretório: {exc}")
except CvmError as exc:
    print(f"Erro geral do módulo CVM: {exc}")
```

### Exemplo 2: Tratamento na API B3

```python
from globaldatafinance import HistoricalQuotesB3
from globaldatafinance.brazil.b3_data.historical_quotes.errors import (
    EmptyAssetListError,
    InvalidAssetsName,
    InvalidFirstYear,
    InvalidLastYear,
    InvalidOutputFilename,
    InvalidProcessingMode,
)
from globaldatafinance.macro_exceptions import (
    EmptyDirectoryError,
    InvalidDestinationPathError,
)

b3 = HistoricalQuotesB3()

try:
    result = b3.extract(
        path_of_docs="/data/cotahist",
        assets_list=["ações", "etf"],
        initial_year=2023,
        output_filename="cotacoes_2023",
        processing_mode="fast",
    )
    print(
        f"Extraídos {result['total_records']:,} registros em {result['output_file']}"
    )

except EmptyAssetListError:
    print("A lista de classes de ativos não pode ser vazia.")
except InvalidAssetsName as exc:
    print(f"Classe de ativo inválida: {exc}")
except (InvalidFirstYear, InvalidLastYear) as exc:
    print(f"Intervalo de anos B3 inválido: {exc}")
except InvalidOutputFilename as exc:
    print(f"Nome de arquivo de saída inválido: {exc}")
except InvalidProcessingMode as exc:
    print(f"Modo de processamento deve ser 'fast' ou 'slow': {exc}")
except EmptyDirectoryError as exc:
    print(f"Diretório sem arquivos COTAHIST: {exc}")
except InvalidDestinationPathError as exc:
    print(f"Caminho inválido: {exc}")
```

______________________________________________________________________

Veja também:

- [API CVM](cvm-api.md)
- [API B3](b3-api.md)
- [FAQ](../user-guide/faq.md)
