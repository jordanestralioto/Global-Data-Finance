# Ingestão compartilhada de arquivos CVM

Este pacote oferece processamento de arquivos CVM compatíveis com
`exact-text-v1`, sem depender de documentos, URLs ou anos de companhias abertas.

## Componentes

| Componente                                                     | Responsabilidade                                                 |
| -------------------------------------------------------------- | ---------------------------------------------------------------- |
| `http.py`                                                      | `CvmDownloadAdapter`: downloads limitados, retry e finalização   |
| `extract.py`                                                   | `CvmParquetExtractor`: extração com ownership e transação        |
| `csv_pipeline/`                                                | Encoding, registros CSV, schema textual e escrita em lotes       |
| `source_inventory.py`                                          | Identidade da origem e inventário exato de saídas                |
| `content_fingerprint.py`, `parquet_validation.py`              | Comparação dos registros de origem com os dados persistidos      |
| `destination_io.py`, `write_ownership.py`, `transaction_io.py` | Diretórios abertos, escritor exclusivo e operações transacionais |
| `transaction.py`                                               | Coordenação da publicação recuperável global                     |
| `models.py`                                                    | Resultado de uma operação de download CVM                        |

## Contrato e dependências

O CSV usa `;` entre campos, um registro por linha física e aspas literais. Todos
os campos Parquet são `string`; vazios permanecem strings vazias. O pacote
preserva ZIPs, basenames, metadados `cvm.*` e verificação completa antes da
publicação. Arrow só é carregado quando o processamento precisa dele.

As fundações em `core/` e `macro_infra/` continuam responsáveis por configuração,
segurança, HTTP, temporários e publicação transacional. O lock `.cvm-write-lock`
protege download e extração e mantém seu ciclo separado do lock do publisher.

## Composição e identidade das saídas

Cada família seleciona seu catálogo e seus períodos fora deste pacote e usa
`CvmDownloadAdapter` e `CvmParquetExtractor` diretamente. O resultado é
`ingestion.models.DownloadResultCVM`.

A extração automática verifica o inventário e a identidade de origem antes de
chamar o extrator e novamente depois da chamada. Arquivos obsoletos identificados
por `cvm.source-archive` impedem a execução do colaborador, preservando as saídas
existentes. O extrator fornecido responde por suas escritas e transação; a
verificação posterior detecta violações, mas não desfaz efeitos arbitrários.

O chamador prepara os destinos e segue o
[contrato de inventário](https://jordanestralioto.github.io/Global-Data-Finance/user-guide/migration-cvm-exact-text/#inventario-das-saidas)
para arquivos existentes. A facade de empresas valida e prepara os destinos
das suas operações.

## Validação

`tests/brazil/cvm/ingestion/` cobre os mecanismos comuns e o reúso por uma família
sintética independente. As regressões preservam as facades e a integridade
dos dados atuais. O contrato de imports impede dependência deste pacote na família de
empresas. Veja a [decisão de ownership](https://jordanestralioto.github.io/Global-Data-Finance/decisions/cvm-ingestion-ownership/).
