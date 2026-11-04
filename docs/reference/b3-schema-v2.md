# Schema Parquet B3 v2

O schema Parquet padrão produzido por `HistoricalQuotesB3` é a versão `2`. Os
20 campos históricos mantêm a ordem e os valores lógicos; a versão acrescenta
campos oficiais do COTAHIST, tipo do registro, proveniência e os bytes originais.
Todos os campos são obrigatórios, exceto `data_vencimento`. O footer contém o
manifesto de integridade e a impressão digital lógica do schema.

## Colunas

| Coluna                   | Tipo                         | Descrição                                         |
| ------------------------ | ---------------------------- | ------------------------------------------------- |
| `data_pregao`            | `date32[day]`                | Data do pregão                                    |
| `codigo_bdi`             | `large_string`               | Código BDI                                        |
| `ticker`                 | `large_string`               | Código de negociação (ex.: PETR4)                 |
| `tipo_mercado`           | `large_string`               | Tipo de mercado                                   |
| `nome_resumido`          | `large_string`               | Nome resumido da empresa                          |
| `especificacao_papel`    | `large_string`               | Especificação do papel (ex.: ON, PN)              |
| `preco_abertura`         | `decimal128(38, 2)`          | Preço de abertura                                 |
| `preco_maximo`           | `decimal128(38, 2)`          | Preço máximo do dia                               |
| `preco_minimo`           | `decimal128(38, 2)`          | Preço mínimo do dia                               |
| `preco_medio`            | `decimal128(38, 2)`          | Preço médio do dia                                |
| `preco_fechamento`       | `decimal128(38, 2)`          | Preço de fechamento                               |
| `melhor_oferta_compra`   | `decimal128(38, 2)`          | Melhor oferta de compra                           |
| `melhor_oferta_venda`    | `decimal128(38, 2)`          | Melhor oferta de venda                            |
| `numero_negocios`        | `int64`                      | Número de negócios efetuados                      |
| `quantidade_total`       | `int64`                      | Quantidade total de títulos negociados            |
| `volume_total`           | `decimal128(38, 2)`          | Volume financeiro total                          |
| `data_vencimento`        | `date32[day]`                | Vencimento de opções/termo; anulável              |
| `fator_cotacao`          | `int64`                      | Fator de cotação                                  |
| `codigo_isin`            | `large_string`               | Código ISIN                                       |
| `numero_distribuicao`    | `int64`                      | Número de distribuição                            |
| `prazo_termo`            | `large_string`               | PRAZOT preservado como texto, inclusive zeros     |
| `moeda_referencia`       | `large_string`               | MODREF, código da moeda de referência             |
| `preco_exercicio`        | `decimal128(38, 2)`          | PREEXE, decimal exato com escala 2                |
| `indicador_correcao`     | `large_string`               | INDOPC, código preservado, inclusive `"0"`        |
| `preco_exercicio_pontos` | `decimal128(38, 6)`          | PTOEXE, decimal exato com escala 6                |
| `tipo_registro`          | `large_string`               | Identificador do registro (`"01"`)                |
| `id_fonte`               | `large_string`               | SHA-256 do conteúdo COTAHIST descompactado         |
| `arquivo_origem`         | `large_string`               | Nome do arquivo COTAHIST de entrada               |
| `membro_origem`          | `large_string`               | Membro ZIP selecionado; vazio para TXT            |
| `ano_origem`             | `int64`                      | Ano validado pelo nome do arquivo                 |
| `linha_origem`           | `int64`                      | Linha física de origem, começando em 1            |
| `registro_original`      | `fixed_size_binary[245]`     | Bytes originais do registro `01`, sem terminador  |

`preco_exercicio` e `preco_exercicio_pontos` são decimais exatos com escalas 2
e 6; valores financeiros não passam por ponto flutuante. As posições seguem o
[layout oficial da B3](https://www.b3.com.br/data/files/33/67/B9/50/D84057102C784E47AC094EA8/SeriesHistoricas_Layout.pdf).

## Leitura e migração

### Digest ordenado das linhas

Cada fonte tem um SHA-256 calculado em ordem de schema e de linha física.
O prefixo é `GLOBALDATAFINANCE-B3-ROW-DIGEST` seguido de um byte zero, versão
`2` como inteiro unsigned de 4 bytes e quantidade de colunas como inteiro
unsigned de 2 bytes; todos os inteiros do framing usam big-endian. Cada nome
de coluna recebe a tag `N`, seu comprimento UTF-8 em 8 bytes e o conteúdo.

Cada linha começa com a tag `R`. Nulo usa apenas `Z`; textos, datas ISO,
inteiros decimais e valores financeiros na escala declarada usam a tag `S`,
comprimento UTF-8 em 8 bytes e conteúdo. `registro_original` usa a tag `B`,
comprimento em 8 bytes e os bytes ASCII de seu Base64 padrão, com padding.
Isso mantém nulo distinto de vazio e preserva ordem e ocorrências repetidas.
O oracle implementa esse contrato independentemente e compara os digests e
as demais informações do manifesto aos dados brutos reconciliados.

Preflight, replay e leitura de verificação usam a mesma implementação de
digest. Preflight e replay agrupam o framing por linha. A leitura de
verificação usa operações Arrow para agrupar as colunas canônicas em
segmentos limitados, preservando exatamente o fluxo de bytes da versão 2.
Cada segmento termina na fronteira da fonte correspondente; fontes sem
cotações selecionadas também têm seu digest conferido.

Os cabeçalhos de comprimento mais frequentes usam tabelas constantes de
tamanho limitado. Essas tabelas contêm somente tags e comprimentos, sem
armazenar valores financeiros ou conteúdo das fontes.

Antes do merge, cada Parquet temporário tem seu schema, footer completo,
manifesto e contagem conferidos. O merge reaplica a validação de schema e
metadados ao abrir cada temporário e compara os batches consumidos com a
contagem do footer, independentemente dos flushes de row groups. A conversão
CSV para Arrow também exige uma linha por registro original antes de montar
o buffer de proveniência. O arquivo final recebe uma leitura
completa, em lotes limitados, para conferir valores, proveniência, ordem e
digests por fonte antes da publicação transacional. As verificações de
replay e identidade das fontes continuam obrigatórias.

A leitura de verificação converte datas, inteiros e decimais em strings
canônicas por coluna com Arrow, preservando a escala decimal e sem usar
ponto flutuante. O framing dessas colunas também usa operações Arrow, com
Base64 padrão para os bytes originais. Todas as 32 colunas participam do
digest. As verificações de proveniência, datas, nulidade, ordem e contagens
continuam cobrindo cada linha, inclusive quando um lote atravessa fontes.

### Leitura

Campos numéricos de origem devem conter somente dígitos ASCII em toda a largura;
espaços nas extremidades não são aceitos. `indicador_correcao` valida o único
dígito de INDOPC e o preserva como texto. Campos alfanuméricos como BDI, PRAZOT,
MODREF e ISIN mantêm seu contrato textual. `data_vencimento` aceita oito espaços
ou `00000000` como ausência e preserva datas válidas, inclusive `99991231`.

Use `pyarrow.parquet.read_table()` para carregar a tabela completa ou
`pyarrow.parquet.ParquetFile(...).iter_batches()` com `batch_size=200_000` para
limitar o uso de memória. PyArrow é o engine produtivo recomendado; Pandas
continua compatível como leitor downstream, mas precisa ser instalado pelo
consumidor.

Arquivos com schema v1 não podem ser promovidos nem preenchidos com dados
ausentes. Regenere-os a partir dos COTAHIST originais conforme o
[guia de migração da versão 2](../user-guide/migration-pyarrow-integrity.md#b3-schema-v2-e-regeneracao).
