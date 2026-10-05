# B3 Parquet Schema v2

The default Parquet schema produced by `HistoricalQuotesB3` is version `2`.
The 20 historical fields retain their order and logical values; v2 adds
official COTAHIST fields, the record type, provenance, and original bytes.
Every field is required except `data_vencimento`. The footer carries the
integrity manifest and logical schema fingerprint.

## Columns

| Column                   | Type                         | Description                                       |
| ------------------------ | ---------------------------- | ------------------------------------------------- |
| `data_pregao`            | `date32[day]`                | Trading session date                              |
| `codigo_bdi`             | `large_string`               | BDI market classification code                   |
| `ticker`                 | `large_string`               | Trading symbol (e.g., PETR4)                      |
| `tipo_mercado`           | `large_string`               | Market type                                       |
| `nome_resumido`          | `large_string`               | Issuer short name                                 |
| `especificacao_papel`    | `large_string`               | Security specification (e.g., ON, PN)             |
| `preco_abertura`         | `decimal128(38, 2)`          | Opening price                                     |
| `preco_maximo`           | `decimal128(38, 2)`          | Session high price                                |
| `preco_minimo`           | `decimal128(38, 2)`          | Session low price                                 |
| `preco_medio`            | `decimal128(38, 2)`          | Average price                                     |
| `preco_fechamento`       | `decimal128(38, 2)`          | Closing price                                     |
| `melhor_oferta_compra`   | `decimal128(38, 2)`          | Best bid                                          |
| `melhor_oferta_venda`    | `decimal128(38, 2)`          | Best ask                                          |
| `numero_negocios`        | `int64`                      | Number of trades                                  |
| `quantidade_total`       | `int64`                      | Total traded quantity                             |
| `volume_total`           | `decimal128(38, 2)`          | Total monetary turnover                           |
| `data_vencimento`        | `date32[day]`                | Options/term expiration date; nullable            |
| `fator_cotacao`          | `int64`                      | Quotation scaling factor                          |
| `codigo_isin`            | `large_string`               | ISIN code                                         |
| `numero_distribuicao`    | `int64`                      | Distribution number                               |
| `prazo_termo`            | `large_string`               | PRAZOT kept as text, including leading zeros      |
| `moeda_referencia`       | `large_string`               | MODREF reference currency code                    |
| `preco_exercicio`        | `decimal128(38, 2)`          | PREEXE exact decimal with scale 2                 |
| `indicador_correcao`     | `large_string`               | INDOPC code preserved, including `"0"`            |
| `preco_exercicio_pontos` | `decimal128(38, 6)`          | PTOEXE exact decimal with scale 6                 |
| `tipo_registro`          | `large_string`               | Record identifier (`"01"`)                        |
| `id_fonte`               | `large_string`               | SHA-256 of uncompressed COTAHIST contents          |
| `arquivo_origem`         | `large_string`               | COTAHIST input filename                           |
| `membro_origem`          | `large_string`               | Selected ZIP member; empty for TXT                |
| `ano_origem`             | `int64`                      | Year validated from the filename                  |
| `linha_origem`           | `int64`                      | One-based physical source line                    |
| `registro_original`      | `fixed_size_binary[245]`     | Original `01` record bytes without a terminator   |

`preco_exercicio` and `preco_exercicio_pontos` use exact decimals with scales
2 and 6; financial values never pass through floating point. Positions follow
the [official B3 layout](https://www.b3.com.br/data/files/33/67/B9/50/D84057102C784E47AC094EA8/SeriesHistoricas_Layout.pdf).

## Reading and migration

### Ordered row digest

Each source has a SHA-256 computed in schema and physical-line order. The
prefix is `GLOBALDATAFINANCE-B3-ROW-DIGEST` followed by a zero byte, version
`2` as a 4-byte unsigned integer, and the column count as a 2-byte unsigned
integer. All framing integers are big-endian. Each column name receives an
`N` tag, its UTF-8 byte length as an 8-byte integer, and its content.

Each row starts with `R`. Null uses only `Z`; text, ISO dates, decimal
integers, and financial values at their declared scale use `S`, an 8-byte
UTF-8 byte length, and content. `registro_original` uses `B`, an 8-byte
length, and the ASCII bytes of its standard padded Base64 representation.
This distinguishes null from empty text and preserves order and repeated
occurrences. The oracle implements this contract independently and compares
the digests and other manifest facts with reconciled raw source data.

### Reading

Source numeric fields must contain only ASCII digits across their full width;
leading and trailing spaces are rejected. `indicador_correcao` validates the
single INDOPC digit and preserves it as text. Alphanumeric BDI, PRAZOT, MODREF,
and ISIN retain their text contracts. `data_vencimento` accepts eight spaces or
`00000000` as absence and preserves valid dates, including `99991231`.

Use `pyarrow.parquet.read_table()` to load the complete table, or
`pyarrow.parquet.ParquetFile(...).iter_batches()` with `batch_size=200_000` for
memory-bounded work. PyArrow is the production engine and the recommended
reader. Pandas remains compatible as a downstream reader, but consumers must
install it separately.

Schema v1 files cannot be promoted or filled with missing data. Regenerate
them from the original COTAHIST files using the
[v2 migration guide](../user-guide/migration-pyarrow-integrity.en.md#b3-schema-v2-and-regeneration).
