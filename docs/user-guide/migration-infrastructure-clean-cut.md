# Migração: corte limpo de infraestrutura

Esta versão major remove APIs genéricas obsoletas e a dependência automática de
Pandas. As fachadas raiz, as assinaturas públicas de CVM/B3, os nomes de saída,
os schemas Parquet e a publicação transacional continuam iguais. A mudança é
intencionalmente incompatível: não há alias, warning, shim ou fallback para os
nomes removidos.

## Timeout de download

Antes:

```text
from globaldatafinance.macro_exceptions import TimeoutError
```

Depois:

```python
from globaldatafinance.macro_exceptions import DownloadTimeoutError

try:
    download()
except DownloadTimeoutError:
    recover_or_report()
```

`DownloadTimeoutError` mantém o construtor `(doc_name, timeout=None)` e o
formato da mensagem anterior. O nome antigo não pode mais ser importado. O
`TimeoutError` nativo do Python continua sendo um erro de transporte interno
reconhecido pelo adapter CVM; não o confunda com a classe de domínio.

## Adapters genéricos removidos

`ExtractorAdapter` e `ReadFilesAdapter` não fazem mais parte de
`globaldatafinance.macro_infra`, e os módulos
`globaldatafinance.macro_infra.extractor_file` e
`globaldatafinance.macro_infra.read_files` foram removidos.

Antes:

```python
from globaldatafinance.macro_infra import ExtractorAdapter, ReadFilesAdapter
```

Depois, use a fronteira da fonte que conhece o contrato do dado:

```python
from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    ParquetExtractorAdapterCVM,
)

cvm_extractor = ParquetExtractorAdapterCVM()
convert_zip = cvm_extractor.extract
convert_zip('download.zip', 'cvm-output')
```

Para leitura ou inspeção de arquivos B3, use a fachada `HistoricalQuotesB3` e
os componentes source-owned documentados em [Cotações Históricas B3](b3-docs.md).
Não recrie um adapter genérico para reproduzir os módulos removidos: CVM e B3
têm regras de formato, anos mínimos e diagnósticos diferentes.

## Pandas deixou de ser dependência automática

O runtime da biblioteca usa PyArrow para CSV e Parquet. Um consumidor que ainda
precisar de DataFrames deve declarar a dependência por conta própria:

```bash
python -m pip install pandas
```

Para o caminho recomendado e limitado por memória, nenhuma instalação adicional
é necessária além das dependências da biblioteca:

```python
import pyarrow.parquet as pq

for batch in pq.ParquetFile('cotahist.parquet').iter_batches(
    batch_size=200_000
):
    consume(batch)
```

Pandas e Polars podem continuar sendo usados como leitores downstream opcionais,
mas não são instalados nem importados pelo pacote.

## Fronteira de captura B3

As exceções concretas B3 preservam seus tipos e agora herdam de `B3Error`:

```python
from globaldatafinance.brazil.b3_data.historical_quotes.errors import B3Error

try:
    run_b3_operation()
except B3Error as error:
    handle_b3_input_or_processing_error(error)
```

`B3Error` é source-local e não é exportado por `globaldatafinance` nem usado
como base global. As regras de ano continuam separadas das regras CVM: o limite
mínimo B3 continua sendo 1986, e `InvalidFirstYear`/`InvalidLastYear` de cada
fonte continuam sendo classes distintas.

## Falhas de escrita Parquet CVM

Falhas de filesystem durante criação, escrita, fechamento ou reabertura do
Parquet staged agora são `ParquetWriteError`, com a causa original preservada.
`ENOSPC` continua produzindo `DiskFullError`; erros de CSV, Arrow, schema,
contagem de linhas, ZIP corrompido e falha combinada de rollback continuam sendo
`ExtractionError` quando esse é o contrato apropriado.

Na agregação de downloads, uma falha conhecida aparece como:

```text
ParquetWrite: Failed to write Parquet file '...'
```

O ZIP de origem é mantido para diagnóstico. Consumidores que tratavam qualquer
`ExtractionError` podem adicionar uma captura explícita para
`ParquetWriteError` quando precisarem distinguir falha de infraestrutura de
falha de conteúdo.

## Destinos e temporários internos

Os owners CVM e B3 compartilham apenas a normalização e a preparação de
destinos invariantes. A criação de diretórios continua sendo responsabilidade
do owner da fonte, e o publicador transacional não cria o destino. Downloads e
writers Parquet reservam arquivos temporários ocultos no mesmo diretório do
destino para preservar a elegibilidade de publicação no mesmo filesystem.
