# Global-Data-Finance

[![PyPI](https://img.shields.io/pypi/v/globaldatafinance)](https://pypi.org/project/globaldatafinance/)
[![Python](https://img.shields.io/pypi/pyversions/globaldatafinance)](https://pypi.org/project/globaldatafinance/)
[![CI](https://github.com/jordanestralioto/Global-Data-Finance/actions/workflows/pipeline.yml/badge.svg?branch=main)](https://github.com/jordanestralioto/Global-Data-Finance/actions/workflows/pipeline.yml)
[![Licença](https://img.shields.io/pypi/l/globaldatafinance)](https://github.com/jordanestralioto/Global-Data-Finance/blob/main/LICENSE)

**Português** · [English](https://github.com/jordanestralioto/Global-Data-Finance/blob/develop/README.en.md)

Biblioteca Python para baixar documentos regulatórios da CVM e converter
cotações históricas da B3 em arquivos Parquet. Oferece uma API para selecionar
fontes e anos, validar os dados e persistir os resultados em pastas escolhidas
pela aplicação.

[Documentação](https://jordanestralioto.github.io/Global-Data-Finance/)
· [Pacote no PyPI](https://pypi.org/project/globaldatafinance/)
· [Exemplos](https://github.com/jordanestralioto/Global-Data-Finance/tree/develop/examples)
· [Histórico de versões](https://github.com/jordanestralioto/Global-Data-Finance/releases)

**Status:** beta. Requer Python `>=3.12,<4.0`, com verificações de CI em
Python 3.12, 3.13 e 3.14.

## Fontes e funcionalidades

| Fonte   | Entrada                                                                                  | Saída                                             |
| ------- | ---------------------------------------------------------------------------------------- | ------------------------------------------------- |
| **CVM** | Download por tipo de documento (`DFP`, `ITR`, `FRE`, `FCA`, `CGVN`, `VLMO`, `IPE`) e ano | ZIP original e, opcionalmente, um Parquet por CSV |
| **B3**  | Arquivos anuais COTAHIST locais em ZIP ou TXT                                            | Parquet consolidado com seleção por mercado       |

- **Integridade dos dados:** validação das fontes e dos artefatos antes da publicação dos Parquets.
- **Resultados verificáveis:** status, contagens e diagnósticos para a aplicação conferir cada operação.
- **Execução síncrona ou assíncrona:** interfaces para scripts, notebooks e aplicações com event loop ativo.
- **Leitura com PyArrow:** incluído como dependência; Pandas e Polars podem ser instalados separadamente para análise.

## Instalação

Em um ambiente virtual com uma versão compatível do Python:

```bash
python -m pip install globaldatafinance
```

Em um projeto gerenciado com uv:

```bash
uv add globaldatafinance
```

Consulte o [guia de instalação](https://jordanestralioto.github.io/Global-Data-Finance/user-guide/installation/)
para criar o ambiente e conferir a instalação.

## Uso rápido

Os exemplos usam apenas 2023 para manter o escopo da primeira execução
explícito. Os anos inicial e final são inclusivos.

### Baixar documentos CVM

O download requer acesso à internet. O exemplo baixa as demonstrações
financeiras anuais (`DFP`) e converte os CSVs para Parquet:

```python
from globaldatafinance import FundamentalStocksDataCVM

result = FundamentalStocksDataCVM().download(
    destination_path="./data/cvm",
    list_docs=["DFP"],
    initial_year=2023,
    last_year=2023,
    automatic_extractor=True,
)
if result.error_count_downloads > 0 or result.success_count_downloads == 0:
    raise RuntimeError(result.failed_downloads)
print(result.successful_downloads)
```

Os arquivos ficam em `data/cvm/DFP/2023/`, e o ZIP original é preservado.
`successful_downloads` contém identificadores como `DFP_2023`; os diagnósticos
de falha ficam em `failed_downloads`. Verifique o resultado, pois um lote pode
ter sucessos e falhas.

**As colunas CVM são preservadas como texto**, incluindo zeros iniciais,
separadores decimais e campos vazios. Converta datas e números explicitamente
durante a análise. Para salvar somente os ZIPs, use
`automatic_extractor=False`, que é o padrão.

### Extrair cotações B3

Obtenha os arquivos pela [página oficial da B3](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/)
e coloque-os em uma pasta de entrada. A biblioteca aceita arquivos ZIP ou TXT
locais com nomes `COTAHIST_A{YYYY}.ZIP` ou `COTAHIST_A{YYYY}.TXT` e exige todos
os anos solicitados. O download dos arquivos B3 é feito pelo usuário.

Para executar o exemplo, prepare:

```text
cotahist/
└── COTAHIST_A2023.ZIP
```

Salve e execute o código abaixo como um script Python:

```python
from globaldatafinance import HistoricalQuotesB3


def main() -> None:
    b3 = HistoricalQuotesB3()
    result = b3.extract(
        path_of_docs="./cotahist",
        destination_path="./data/b3",
        assets_list=["ações"],
        initial_year=2023,
        last_year=2023,
        output_filename="quotes_2023",
    )
    if not result["success"]:
        raise RuntimeError(result["errors"])
    print(result["output_file"], result["total_records"])


if __name__ == "__main__":
    main()
```

A saída é `data/b3/quotes_2023.parquet`. O retorno segue o contrato
`ExtractionResultB3`: um dicionário com status e metadados da extração.
`ações` seleciona o mercado à vista (`010`) e o fracionário (`020`);
omitir `assets_list` seleciona todos os mercados válidos. O filtro seleciona
mercados, não tickers individuais.

O Parquet B3 usa preços decimais exatos e inclui informações de proveniência.
O modo padrão, `fast`, usa concorrência limitada pelos recursos disponíveis;
`processing_mode="slow"` usa um worker para reduzir o consumo de memória.
Conforme a [descrição da fonte B3](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/),
as cotações são fornecidas sem ajustes por inflação ou proventos.

## Ler o Parquet

Após a extração B3 acima, inspecione o schema e uma pequena amostra sem
carregar o arquivo inteiro na memória:

```python
import pyarrow.parquet as pq

parquet = pq.ParquetFile("./data/b3/quotes_2023.parquet")
print(parquet.schema_arrow)
for batch in parquet.iter_batches(batch_size=5):
    print(batch.to_pydict())
    break
```

## Documentação

| Objetivo                                     | Referência                                                                                                         |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Executar a primeira extração                 | [Início rápido](https://jordanestralioto.github.io/Global-Data-Finance/user-guide/quickstart/)                     |
| Escolher documentos e tratar resultados CVM  | [Guia CVM](https://jordanestralioto.github.io/Global-Data-Finance/user-guide/cvm-docs/)                            |
| Preparar COTAHIST e selecionar mercados      | [Guia B3](https://jordanestralioto.github.io/Global-Data-Finance/user-guide/b3-docs/)                              |
| Consultar argumentos, resultados e exceções  | [Referência da API](https://jordanestralioto.github.io/Global-Data-Finance/dev-guide/api-reference/)               |
| Executar exemplos com amostras B3 sintéticas | [Exemplos do repositório](https://github.com/jordanestralioto/Global-Data-Finance/blob/develop/examples/README.md) |

Em notebooks e aplicações com event loop ativo, use
`await cvm.async_download(...)` ou `await b3.extract_async(...)`. Os guias de
cada fonte descrevem os argumentos e o tratamento de falhas.

## Contribuir

Contribuições de código, testes e documentação são bem-vindas. Comece pelo
[guia de contribuição](https://github.com/jordanestralioto/Global-Data-Finance/blob/develop/CONTRIBUTING.md)
para conhecer o fluxo de branches e pull requests, as regras de testes e os
quality gates.

Após clonar o repositório, prepare o ambiente de desenvolvimento com o lockfile
versionado e instale os hooks:

```bash
uv sync --locked --all-extras --dev
uv run --locked --no-sync pre-commit install --install-hooks
```

A participação segue o [Código de Conduta](https://github.com/jordanestralioto/Global-Data-Finance/blob/develop/CODE_OF_CONDUCT.md).

## Suporte e segurança

Para relatar bugs ou sugerir melhorias, abra uma
[issue no GitHub](https://github.com/jordanestralioto/Global-Data-Finance/issues)
com a versão da biblioteca, a versão do Python e um exemplo reproduzível.
Para vulnerabilidades, siga o canal privado da
[política de segurança](https://github.com/jordanestralioto/Global-Data-Finance/blob/develop/SECURITY.md).

## Licença

Distribuído sob a [licença Apache 2.0](https://github.com/jordanestralioto/Global-Data-Finance/blob/main/LICENSE).
O uso dos dados está sujeito aos termos das respectivas fontes.
