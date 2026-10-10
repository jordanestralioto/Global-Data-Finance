# Exemplos de uso

Comece pelos exemplos 01 e 02. Cada script usa a API pública da
`globaldatafinance`, informa onde salvou o resultado e encerra com erro se o
processamento falhar. Parquet é o formato de saída; você pode lê-lo com
PyArrow, já instalado com a biblioteca.

| Exemplo                                                | O que faz                                  | O que você precisa fornecer             |
| ------------------------------------------------------ | ------------------------------------------ | --------------------------------------- |
| [01_quickstart_cvm.py](01_quickstart_cvm.py)           | Baixa DFP da CVM e converte em Parquet     | Conexão com a internet                  |
| [02_quickstart_b3.py](02_quickstart_b3.py)             | Extrai cotações dos mercados de ações      | Arquivo COTAHIST local do ano escolhido |
| [03_advanced_options_b3.py](03_advanced_options_b3.py) | Seleciona mercados de ações, ETFs e opções | Arquivo COTAHIST local do ano escolhido |

Os três exemplos processam **somente 2023** por padrão. Você pode mudar o ano,
o intervalo e a pasta de saída por opções de linha de comando.

## Preparar o ambiente

Requisitos: Python `>=3.12,<4.0` e `uv`. Consulte o
[guia de instalação](../docs/user-guide/installation.md) se ainda não preparou
seu ambiente.

Execute na **raiz do repositório**, onde está o `pyproject.toml`:

```bash
uv sync --locked --all-extras --dev
```

Essa preparação é feita uma vez. Os comandos seguintes usam `--no-sync` para
reutilizar o ambiente. As pastas relativas, como `./dados_b3`, são resolvidas a
partir da pasta em que você executa o comando.

## 1. Baixar demonstrações financeiras da CVM

```bash
uv run --locked --no-sync python examples/01_quickstart_cvm.py
```

O exemplo baixa o ZIP de **Demonstrações Financeiras Padronizadas (DFP)** de
2023, converte seus CSVs em Parquet e salva os arquivos em `./dados_cvm`.
Essa seleção reúne demonstrações de várias empresas e pode levar alguns
minutos. Uma execução bem-sucedida remove o ZIP após a conversão.

Para escolher outro período e destino:

```bash
uv run --locked --no-sync python examples/01_quickstart_cvm.py \
  --initial-year 2022 --last-year 2023 --destination-path ./dados_cvm
```

## 2. Extrair cotações de ações da B3

A biblioteca **processa arquivos locais ZIP ou TXT**; ela não baixa COTAHIST
da B3. Obtenha o arquivo anual conforme o
[guia B3](../docs/user-guide/b3-docs.md) e organize a entrada assim:

```text
cotahist_b3/
└── COTAHIST_A2023.ZIP
```

Você também pode usar `COTAHIST_A2023.TXT`. Preserve o nome oficial do arquivo
para cada ano. Os arquivos de entrada não são incluídos nos exemplos.

```bash
uv run --locked --no-sync python examples/02_quickstart_b3.py
```

Saída padrão: `./dados_b3/cotacoes_acoes_2023.parquet`. O exemplo seleciona
cotações dos mercados à vista (010) e fracionário (020). A seleção é por mercado,
e não por uma lista de tickers; ETFs desses mercados também podem aparecer.

Se os arquivos estiverem em outra pasta, use `--path-of-docs`. Caminhos com
espaços devem ficar entre aspas:

```bash
uv run --locked --no-sync python examples/02_quickstart_b3.py \
  --path-of-docs "/caminho/para/COTAHIST" \
  --initial-year 2022 --last-year 2023 --destination-path ./dados_b3
```

Todos os anos do intervalo precisam existir na pasta. Nesse comando, a saída
será `cotacoes_acoes_2022_2023.parquet`.

## 3. Selecionar mais mercados e ajustar o processamento

```bash
uv run --locked --no-sync python examples/03_advanced_options_b3.py
```

Saída padrão: `./dados_b3/carteira_completa_2023.parquet`. Este exemplo passa
`assets_list=['ações', 'etf', 'opções']` para incluir também os mercados de
opções de compra e venda.

Os dois exemplos B3 aceitam `--processing-mode fast` (padrão, voltado a
throughput) e `--processing-mode slow` (menor uso de memória). Para processar
2022 e 2023 em modo `slow`:

```bash
uv run --locked --no-sync python examples/03_advanced_options_b3.py \
  --initial-year 2022 --last-year 2023 --processing-mode slow
```

Ao informar apenas `--initial-year`, o ano final acompanha o inicial. Por
exemplo, `--initial-year 2022` processa somente 2022 nos três scripts.

Para preservar todos os mercados, omita `assets_list` ou use `['todos']` em
seu próprio código:

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs='./cotahist_b3',
    initial_year=2023,
    last_year=2023,
    assets_list=['todos'],
    destination_path='./dados_b3',
    output_filename='cotahist_completo_2023',
    verbose=False,
)
if not result['success'] or result['total_records'] == 0:
    raise SystemExit(f'Extração incompleta: {result["errors"]}')
print(result['output_file'])
```

## Ler o Parquet gerado

Após executar o exemplo 02, abra o Python no mesmo ambiente:

```bash
uv run --locked --no-sync python
```

Cole este código para ver a contagem e as cinco primeiras cotações sem carregar
o arquivo inteiro:

```python
import pyarrow.parquet as pq

parquet = pq.ParquetFile('./dados_b3/cotacoes_acoes_2023.parquet')
print(f'Registros: {parquet.metadata.num_rows}')
for batch in parquet.iter_batches(
    batch_size=5,
    columns=['data_pregao', 'ticker', 'preco_fechamento'],
):
    print(batch.to_pydict())
    break
```

Troque o caminho para ler outra saída. Pandas e Polars são leitores opcionais;
os exemplos não exigem sua instalação.

## Ajuda e problemas comuns

Cada script lista suas opções e padrões com `--help`:

```bash
uv run --locked --no-sync python examples/01_quickstart_cvm.py --help
uv run --locked --no-sync python examples/02_quickstart_b3.py --help
uv run --locked --no-sync python examples/03_advanced_options_b3.py --help
```

- **`ModuleNotFoundError: globaldatafinance`**: execute a preparação do ambiente
  e use os comandos `uv run` acima.
- **COTAHIST ausente ou ano indisponível**: confira `--path-of-docs`, os nomes
  `COTAHIST_AYYYY.ZIP` ou `COTAHIST_AYYYY.TXT` e todos os anos solicitados.
- **Nenhum registro selecionado**: confira se os mercados escolhidos existem
  no arquivo de entrada; uma saída vazia não é apresentada como sucesso.
- **Falha de download CVM**: leia o diagnóstico exibido, confira a conexão e a
  disponibilidade dos arquivos na fonte antes de tentar novamente.

`cli.py` e `result_validation.py` são módulos de apoio; os exemplos executáveis
são os três scripts numerados.

## Validar os exemplos

Na raiz do repositório:

```bash
uv run --locked --no-sync pytest tests/examples
```

Os testes executam os três scripts com entradas controladas, leem os Parquet
gerados e verificam os filtros e as falhas. O HTTP da CVM é substituído por
respostas locais nos testes; eles não dependem da internet nem exigem arquivos
COTAHIST oficiais. Executar o exemplo 01 normalmente acessa a fonte CVM.

Para os contratos completos, consulte os guias
[CVM](../docs/user-guide/cvm-docs.md), [B3](../docs/user-guide/b3-docs.md) e os
[exemplos adicionais](../docs/user-guide/examples.md).
