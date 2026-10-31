# Família de documentos de empresas CVM

Este pacote é responsável pela seleção e pelas políticas de documentos de
companhias abertas brasileiras. A facade do consumidor continua sendo
`FundamentalStocksDataCVM`.

## Responsabilidades

| Módulo      | Responsabilidade                                                    |
| ----------- | ------------------------------------------------------------------- |
| `core.py`   | Catálogo, anos iniciais, URLs anuais e contrato de anos disponíveis |
| `client.py` | Validação da solicitação, destinos de empresas e orquestração       |
| `errors.py` | Exceções de seleção e validação de empresas                         |

Download, preservação CSV, verificação de saídas, ownership do destino e
coordenação transacional ficam na [ingestão compartilhada da CVM](../ingestion/README.md).
Esse pacote nunca importa esta família. HTTP, segurança de caminhos/ZIP e
publicação transacional globais mantêm seus proprietários existentes.

## Uso

```python
from globaldatafinance import FundamentalStocksDataCVM

result = FundamentalStocksDataCVM().download(
    destination_path='./data_cvm',
    list_docs=['DFP', 'ITR'],
    initial_year=2023,
    last_year=2023,
    automatic_extractor=True,
)
if result.has_errors():
    raise RuntimeError(result.failed_downloads)
```

## Contratos atuais

`DFP`, `ITR`, `FRE`, `FCA`, `CGVN`, `IPE` e `VLMO` mantêm seleção, anos iniciais,
URLs e destinos `{DOC}/{YEAR}`. Seleção vazia ou omitida continua significando
os tipos de empresas. Novas famílias CVM não entram nessa seleção padrão.

O orquestrador e a facade usam `ingestion.http.CvmDownloadAdapter`; o resultado
é `ingestion.models.DownloadResultCVM`, com chaves `{DOC}_{YEAR}`.

Os ZIPs são retidos. Os campos permanecem texto em `exact-text-v1`, e os Parquets
mantêm o basename dos CSVs. A substituição e a preservação de arquivos existentes
seguem o [contrato de inventário](../../../../../docs/user-guide/migration-cvm-exact-text.md#inventario-das-saidas).

## Extensão e validação

Outra família CVM mantém seu catálogo e seleção de períodos e pode usar
os mecanismos comuns quando o contrato do arquivo for compatível. Ela compõe
os mesmos mecanismos e preserva os metadados atuais de identidade. Outro
dialeto ou schema financeiro exige uma decisão própria.

Testes de empresas continuam em `tests/brazil/cvm/fundamental_stocks_data/`
e `tests/application/cvm_docs/`. Testes dos mecanismos comuns e de consumidores
independentes ficam em `tests/brazil/cvm/ingestion/`. Consulte a
[referência CVM](../../../../../docs/reference/cvm-api.md) e a
[arquitetura](../../../../../docs/dev-guide/architecture.md).
