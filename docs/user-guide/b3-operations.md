# Boas práticas B3

Orientações para processar arquivos locais `COTAHIST_A{YYYY}.ZIP` ou
`COTAHIST_A{YYYY}.TXT` e consumir os Parquets. A API aceita ZIP e TXT; consulte
o [guia B3](b3-docs.md) para preparar as entradas.

## Planeje o intervalo e os recursos

Informe o início e o fim do intervalo: cada ano solicitado precisa ter uma
fonte válida. O ano final omitido usa o ano corrente; omitir o inicial solicita
desde 1986. As extrações não baixam fontes ausentes.

`fast` permite fontes concorrentes dentro dos limites de CPU, memória e
quantidade de arquivos. `slow` usa um worker de fonte e lotes menores.
Os dois modos validam os mesmos dados e publicam o mesmo schema. As
[medições COTAHIST](../dev-guide/cotahist-performance.md) informam o corpus e o
ambiente de cada comparação.

## Separe mercados quando necessário

`ações` e `etf` são aliases para os mesmos TPMERCs `010` e `020`. Gerar um
arquivo com cada alias duplica essa seleção; o filtro não distingue ações de
ETFs dentro desses mercados. Para separar instrumentos, o consumidor precisa
de um cadastro externo. O exemplo abaixo separa os mercados à vista/fracionário
dos mercados de opções, usando intervalos explícitos:

```python
from globaldatafinance import HistoricalQuotesB3


def main() -> None:
    b3 = HistoricalQuotesB3()
    for asset, filename in [("ações", "cash_2023"), ("opções", "options_2023")]:
        result = b3.extract(
            path_of_docs="./cotahist_b3",
            assets_list=[asset],
            initial_year=2023,
            last_year=2023,
            output_filename=filename,
            processing_mode="fast",
        )
        if not result["success"]:
            raise RuntimeError(result["errors"] or result["message"])
        print(result["output_file"])


if __name__ == "__main__":
    main()
```

## Reserve espaço para temporários e publicação

O espaço necessário inclui as fontes, os Parquets temporários por fonte e a
saída consolidada; a publicação recuperável também preserva a saída anterior
quando ela existe. O tamanho depende dos dados e da compressão. Verifique o
filesystem do destino e reduza o intervalo solicitado quando necessário.
`slow` limita concorrência e memória; ele não reduz os dados solicitados ou o
espaço dos artefatos correspondentes.

```python
import shutil

free_bytes = shutil.disk_usage("./cotahist_b3").free
print(f"Available storage: {free_bytes / 1024**3:.2f} GiB")
```

## Leia a saída em lotes

Confira o resultado antes de abrir o arquivo. Para análises que não precisam
carregar toda a tabela, use lotes PyArrow e ajuste `batch_size` ao consumidor:

```python
import pyarrow.parquet as pq

for batch in pq.ParquetFile("./cotahist_b3/cash_2023.parquet").iter_batches(
    batch_size=200_000
):
    print(batch.num_rows)
```

Polars e pandas são leitores opcionais, instalados separadamente pelo
consumidor. Veja a [API B3](../reference/b3-api.md), o
[schema v2](../reference/b3-schema-v2.md), os [exemplos](examples.md) e a
[FAQ](faq.md).
