# Migração major: PyArrow e integridade de ingestão

Esta versão major substitui os caminhos produtivos de ingestão por PyArrow,
remove Polars das dependências da biblioteca e fortalece as garantias de
integridade de CVM e B3. As três fachadas públicas raiz e suas assinaturas
permanecem estáveis:

```python
from globaldatafinance import (
    ExtractionResultB3,
    FundamentalStocksDataCVM,
    HistoricalQuotesB3,
)
```

## Mudanças para consumidores

| Mudança | Ação necessária |
| --- | --- |
| Parser B3 estrito | Corrija o arquivo-fonte ou trate `ExtractionError`; valores inválidos não recebem fallback para zero, string vazia ou nulo. |
| Polars removido | Instale Polars explicitamente caso sua aplicação queira usá-lo para ler Parquet. |
| `ExtractorAdapter.extract_csv_from_zip_to_parquet` removido | Migre código interno para a fachada CVM ou para uma interface pública apropriada. |
| Metadata pandas removida | Não dependa de metadata física `b'pandas'`; use schema e valores lógicos. |
| B3 totalmente filtrado | Trate Parquet vazio como resultado válido quando o filtro TPMERC não encontra ativos. |

## CVM

O CSV CVM continua com `QUOTE_NONE`: aspas são texto literal, não quoting RFC.
Linhas curtas recebem somente valores nulos finais, linhas excedentes falham e
um arquivo apenas com cabeçalho gera Parquet vazio. A publicação de vários
Parquets de um ZIP é failure-atomic e recuperável por manifesto, staging,
backup e lock. Ela não oferece visibilidade instantaneamente atômica para
leitores concorrentes de todos os nomes de arquivo.

## B3

Somente linhas `01` selecionadas são convertidas. Linhas vazias e controles
`00`/`99` são contados, e qualquer outro identificador não vazio falha. A
extração valida largura, datas, textos obrigatórios, inteiros e decimais antes
de persistir. Os modos `fast` e `slow` preservam o mesmo schema, ordem e valores
lógicos; eles diferem apenas na política de concorrência e pressão de memória.

## Dependências e medição

Pandas continua instalado pela compatibilidade pública do `ReadFilesAdapter`,
com import sob demanda. PyArrow é o único engine produtivo de CSV/Parquet.
Use `scripts/benchmark_ingestion.py` para medições locais em processo novo;
seus números dependem de hardware, ambiente e corpus, portanto não são uma
garantia universal de tempo ou RSS.
