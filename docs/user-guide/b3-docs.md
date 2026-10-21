# Cotações históricas B3

Use `HistoricalQuotesB3` para converter arquivos anuais COTAHIST locais em um
Parquet consolidado. A biblioteca retorna status e metadados da extração.

## Preparar os arquivos

O extrator aceita ZIP ou TXT locais com nomes `COTAHIST_A{YYYY}.ZIP` ou
`COTAHIST_A{YYYY}.TXT`. Obtenha os arquivos na
[página oficial da B3](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/)
e coloque-os em uma pasta existente. A biblioteca não faz esse download.

```text
cotahist/
├── COTAHIST_A2022.ZIP
└── COTAHIST_A2023.TXT
```

Forneça **todos os anos solicitados**. Se ZIP e TXT coexistirem para um ano,
ambos são validados integralmente; o ZIP é escolhido somente quando os
conteúdos descompactados são idênticos. Conteúdos diferentes causam falha.
Mantenha os arquivos inalterados durante a extração.

Dentro do ZIP, o membro COTAHIST deve ser único, estar na raiz e usar um dos
nomes `COTAHIST_A{YYYY}.TXT`, `COTAHIST.A{YYYY}` ou `COTAHIST_A{YYYY}`,
com o mesmo ano do arquivo externo. Membros ausentes, aninhados, ambíguos ou
com ano diferente são rejeitados. A fonte deve conter ao menos um registro
`01` válido, além dos controles.

## Extrair cotações

```python
from globaldatafinance import HistoricalQuotesB3


def main() -> None:
    b3 = HistoricalQuotesB3()
    result = b3.extract(
        path_of_docs="./cotahist",
        destination_path="./data_b3",
        assets_list=["ações", "opções"],
        initial_year=2022,
        last_year=2023,
        output_filename="quotes_2022_2023",
        processing_mode="fast",
    )
    if not result["success"]:
        raise RuntimeError(result["errors"])
    print(result["output_file"], result["total_records"])


if __name__ == "__main__":
    main()
```

Esse exemplo gera `data_b3/quotes_2022_2023.parquet` após validar as fontes
e conferir o arquivo final. Os anos são inclusivos. Informe-os explicitamente;
os padrões abrangem 1986 até o ano atual.

## Escolher mercados

Os valores de `assets_list` são aliases de mercados COTAHIST. Eles não
selecionam empresas por ticker. `ações` e `etf` usam os mesmos códigos e
incluem o mercado à vista (010) e o fracionário (020).

| Valor da API | Seleção |
| --- | --- |
| `ações`, `etf` | À vista e fracionário: `010`, `020` |
| `opções` | Compra e venda: `070`, `080` |
| `termo` | Termo: `030` |
| `exercicio_opcoes` | Exercício: `012`, `013` |
| `forward` | Forward: `050`, `060` |
| `leilao` | Leilão: `017` |
| `lote_bloco` | Lote em bloco: `021` |
| `todos` | Todo TPMERC numérico válido, inclusive códigos desconhecidos |

O padrão `assets_list=None` equivale a `todos`; uma lista vazia é inválida.
`get_available_assets()` lista os aliases aceitos. Os valores da API permanecem
em português, inclusive quando o restante do programa usa outro idioma.

## Escolher modo e destino

| Opção | Quando usar |
| --- | --- |
| `processing_mode="fast"` | Padrão: processa arquivos com concorrência limitada por CPU, memória e número de fontes. |
| `processing_mode="slow"` | Usa um worker e reduz o consumo de memória. |
| `destination_path` | Pasta de saída; quando omitida, usa `path_of_docs`. |
| `output_filename` | Apenas nome base, sem pastas; `.parquet` é opcional e acrescentado quando ausente. |
| `verbose=False` | Oculta o resumo final; as barras de progresso continuam visíveis. |

Os dois modos aplicam as mesmas regras de dados e integridade. Para ajustar
workers e recursos, consulte [uso avançado](../dev-guide/advanced-usage.md).

## Conferir e consumir o resultado

O `ExtractionResultB3` contém os campos principais abaixo. A lista completa e
as exceções estão na [referência B3](../reference/b3-api.md).
Em um event loop já ativo, use `await b3.extract_async(...)`; os argumentos e
o resultado são os mesmos. Em scripts que processam várias fontes com
processos, proteja a chamada com `if __name__ == '__main__':`, conforme o
[exemplo de processamento paralelo](../dev-guide/advanced-usage.md).

| Campo | Como usar |
| --- | --- |
| `success` | Confira antes de consumir a saída. |
| `errors` | Diagnósticos de falha por fonte ou etapa. |
| `output_file` | Caminho do novo Parquet publicado; vazio em caso de falha. |
| `total_records` | Quantidade de linhas publicadas. |
| `integrity` | Cobertura anual, validações, proveniência e avisos. |

Um ano ausente ou uma fonte inválida retorna falha e não publica uma nova
saída. Se todas as fontes forem válidas, mas o filtro não selecionar cotações,
o resultado é bem-sucedido com Parquet vazio. Zero linhas não significa, por
si só, erro.

O Parquet usa [schema B3 v2](../reference/b3-schema-v2.md): preços decimais
exatos, campos de proveniência e o registro original. Leia-o com PyArrow como
no [início rápido](quickstart.md). Para arquivos gerados por versões anteriores,
consulte a [migração](migration-pyarrow-integrity.md).
