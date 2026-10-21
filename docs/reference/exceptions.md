# Exceções e resultados de falha

Esta referência distingue erros de entrada, falhas agregadas no resultado e
exceções de baixo nível. Consulte também os contratos [CVM](cvm-api.md) e
[B3](b3-api.md).

## Como tratar uma chamada pública

| Situação | Comportamento |
| --- | --- |
| Parâmetro ou caminho inválido | A validação pode levantar uma exceção antes da operação principal |
| Falha de um download CVM | O resultado registra o identificador e a causa em `failed_downloads`; outros downloads continuam |
| Fonte B3 ausente, corrompida ou inválida | A fachada retorna `success=False`, detalhes em `errors` e nenhum novo `output_file` |
| Pasta B3 vazia | Retorna zero `total_files` e os anos solicitados em `integrity.missing_years` |
| Fontes B3 válidas, sem cotações após o filtro | Retorna sucesso e publica um Parquet vazio com o schema B3 |
| Cancelamento assíncrono B3 antes da decisão de commit | Aguarda os workers, limpa temporários e propaga `asyncio.CancelledError` |

Confira `result.has_errors()` na CVM e `result["success"]` na B3 antes de
consumir os artefatos. A [publicação transacional](transactional-publication.md)
descreve recuperação, cancelamento e limites de visibilidade.

## Exceções compartilhadas

Importe estes tipos de `globaldatafinance.macro_exceptions`.

| Exceção | Base | Condição |
| --- | --- | --- |
| `InvalidDestinationPathError` | `ValueError` | Caminho vazio ou composto apenas por espaços |
| `PathIsNotDirectoryError` | `ValueError` | Caminho que precisa ser diretório está ausente ou é um arquivo |
| `PathPermissionError` | `OSError` | Sem permissão para criar ou gravar no destino |
| `PathCreationError` | `OSError` | Falha ao criar o destino por outro erro de I/O |
| `FileWriteError` | `OSError` | Falha na escrita de arquivo |
| `ParquetWriteError` | `OSError` | Falha de filesystem na escrita ou reabertura do Parquet |
| `DiskFullError` | `OSError` | Falta de espaço no destino |
| `ExtractionError` | `Exception` | Falha de extração ou validação de conteúdo |
| `CorruptedZipError` | `ExtractionError` | ZIP corrompido ou ilegível |
| `SecurityError` | `Exception` | Violação da política de caminhos, arquivos ou extração |
| `NetworkError` | `Exception` | Falha de transporte traduzida pelo adaptador CVM |
| `DownloadTimeoutError` | `Exception` | Timeout de download CVM |
| `EmptyDirectoryError` | `Exception` | Tipo compartilhado que representa ausência de arquivos |

Um destino sensível é rejeitado com `SecurityError`. Erros de tipo podem
levantar o `TypeError` nativo. A fachada B3 sinaliza a pasta vazia pelo resultado
descrito acima; capturar `EmptyDirectoryError` não substitui essa conferência.

Na escrita temporária de Parquet CVM, falhas de filesystem diferentes de
`ENOSPC` viram `ParquetWriteError` com a causa preservada; `ENOSPC` vira
`DiskFullError`. A agregação registra `ParquetWrite: ...` quando aplicável e
mantém o ZIP para diagnóstico. Falhas de CSV, schema, contagem ou integridade
continuam seguindo o contrato de extração.

O adaptador CVM traduz falhas de transporte, aplica a política de
[retry](../dev-guide/retry-strategy.md) e agrega falhas persistentes em
`failed_downloads`. Uma captura síncrona de `NetworkError` ao redor da fachada
não é o mecanismo para identificar esses downloads malsucedidos.

## Exceções CVM

Os tipos abaixo ficam em
`globaldatafinance.brazil.cvm.fundamental_stocks_data.errors`. `CvmError`
herda de `Exception`; os demais tipos desta tabela herdam de `CvmError`.

| Exceção | Condição |
| --- | --- |
| `InvalidDocumentName` | Código fora do catálogo CVM |
| `InvalidDocumentType` | Um item de `list_docs` não é string |
| `InvalidFirstYear` | Ano inicial não inteiro, menor que 2003 ou maior que o ano corrente |
| `InvalidLastYear` | Ano final não inteiro, maior que o ano corrente ou menor que o inicial |
| `EmptyDocumentListError` | Tipo de resolução interna para seleção vazia |
| `MissingDownloadUrlError` | Tipo de resolução interna para documento sem URL configurada |

Um `list_docs` externo que não seja lista nem `None` levanta `TypeError`.
`None` e `[]` selecionam todos os documentos. O catálogo aceita `DFP`, `ITR`,
`FCA`, `FRE`, `CGVN`, `VLMO` e `IPE`.

O limite global de validação de ano é 2003. Os limites de cada documento
filtram as URLs: um intervalo válido anterior ao início de DFP, por exemplo,
não gera URLs DFP para esses anos. Veja os primeiros anos na
[referência CVM](cvm-api.md#tipos-de-documentos).

## Exceções B3

Os tipos ficam em
`globaldatafinance.brazil.b3_data.historical_quotes.errors`.
`B3Error(Exception)` é a base das exceções de validação desta tabela:

| Exceção | Condição |
| --- | --- |
| `EmptyAssetListError` | `assets_list` vazia ou que não é lista; `None` seleciona `todos` |
| `InvalidAssetsName` | Item não string ou alias desconhecido |
| `InvalidFirstYear` | Ano inicial fora de 1986 até o ano corrente ou de tipo inválido |
| `InvalidLastYear` | Ano final inválido, maior que o corrente ou menor que o inicial |
| `InvalidProcessingMode` | Modo diferente de `fast` ou `slow` |
| `InvalidOutputFilename` | Nome de saída inválido ou que não é basename |

Aliases aceitos: `ações`, `etf`, `opções`, `termo`, `exercicio_opcoes`,
`forward`, `leilao`, `lote_bloco` e `todos`. A validação normaliza a caixa das
letras. O nome de saída aceita `.parquet` como sufixo opcional; ele é
acrescentado quando ausente. Separadores de caminho e traversal são rejeitados.

O módulo também contém `CotahistCatalogError(ValueError)` e
`CotahistPreflightError(ExtractionError)`, usados na resolução e no preflight
internos. Eles não herdam de `B3Error`. A fachada traduz essas falhas de fonte
em um resultado malsucedido. Capturar `B3Error` cobre a validação de entrada;
falhas de processamento exigem a conferência de `result["success"]` e `errors`.

`InvalidFirstYear` e `InvalidLastYear` da CVM e da B3 são classes distintas.
As exceções específicas são importadas dos módulos de cada fonte; a raiz
`globaldatafinance` exporta as fachadas e `ExtractionResultB3`.

## Exemplos de tratamento

### CVM

O exemplo exige acesso à CVM e um destino gravável.

```python
from globaldatafinance import FundamentalStocksDataCVM
from globaldatafinance.brazil.cvm.fundamental_stocks_data.errors import CvmError
from globaldatafinance.macro_exceptions import SecurityError

try:
    result = FundamentalStocksDataCVM().download(
        destination_path="./data_cvm",
        list_docs=["DFP"],
        initial_year=2023,
        last_year=2023,
    )
except (CvmError, TypeError, ValueError, OSError, SecurityError) as error:
    raise SystemExit(f"CVM request failed: {error}") from error

if result.has_errors():
    raise RuntimeError(result.failed_downloads)
print(f"Downloaded: {result.success_count_downloads}")
```

### B3

Forneça `COTAHIST_A2023.ZIP` ou `.TXT` na pasta de entrada antes da execução.

```python
from globaldatafinance import HistoricalQuotesB3
from globaldatafinance.brazil.b3_data.historical_quotes.errors import B3Error
from globaldatafinance.macro_exceptions import SecurityError


def main() -> None:
    try:
        result = HistoricalQuotesB3().extract(
            path_of_docs="./cotahist_b3",
            assets_list=["ações", "opções"],
            initial_year=2023,
            last_year=2023,
            output_filename="quotes_2023",
        )
    except (B3Error, TypeError, ValueError, OSError, SecurityError) as error:
        raise SystemExit(f"B3 request failed: {error}") from error

    if not result["success"]:
        raise RuntimeError(result["errors"] or result["message"])
    print(f"Rows: {result['total_records']}; output: {result['output_file']}")


if __name__ == "__main__":
    main()
```
