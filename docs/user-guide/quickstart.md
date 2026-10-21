# Início rápido

Após [instalar a biblioteca](installation.md), escolha uma fonte. CVM requer
internet; B3 usa arquivos locais. Os exemplos abaixo processam somente 2023.

## Baixar documentos CVM

```python
from globaldatafinance import FundamentalStocksDataCVM

result = FundamentalStocksDataCVM().download(
    destination_path="./data_cvm",
    list_docs=["DFP"],
    initial_year=2023,
    last_year=2023,
    automatic_extractor=True,
)
if result.error_count_downloads > 0 or result.success_count_downloads == 0:
    raise RuntimeError(result.failed_downloads)
print(result.successful_downloads)
```

O download salva o ZIP original e converte seus CSVs em Parquet na pasta
indicada. As colunas CVM são texto; datas e números são convertidos na análise,
quando necessário. Para baixar somente ZIPs, use `automatic_extractor=False`.

Confira o [guia CVM](cvm-docs.md) para escolher documentos e tratar falhas
parciais.

## Extrair cotações B3

Obtenha os arquivos na [página oficial da B3](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/)
e coloque o ano desejado na pasta de entrada. O extrator aceita ZIP ou TXT
locais, com nomes `COTAHIST_A{YYYY}.ZIP` ou `COTAHIST_A{YYYY}.TXT`.
A biblioteca não baixa esses arquivos. Para este exemplo, forneça 2023:

```text
cotahist/
└── COTAHIST_A2023.ZIP
```

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="./cotahist",
    destination_path="./data_b3",
    assets_list=["ações"],
    initial_year=2023,
    last_year=2023,
)
if not result["success"]:
    raise RuntimeError(result["errors"])
print(result["output_file"], result["total_records"])
```

`ações` seleciona os mercados à vista e fracionário. O resultado é um dicionário
com status e metadados; os dados ficam no Parquet informado em `output_file`.
Veja o [guia B3](b3-docs.md) para outros mercados, anos e modos de processamento.

## Ler o Parquet

Use o caminho retornado pela extração B3 anterior. Para inspecionar uma pequena
amostra sem carregar o arquivo inteiro:

```python
import pyarrow.parquet as pq

parquet = pq.ParquetFile(result["output_file"])
print(parquet.schema_arrow)
for batch in parquet.iter_batches(batch_size=5):
    print(batch.to_pydict())
    break
```

Para executar os exemplos do repositório com amostras B3 sintéticas já
incluídas, consulte [exemplos práticos](examples.md).
