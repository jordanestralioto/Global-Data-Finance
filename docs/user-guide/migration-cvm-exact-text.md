# Migração CVM para preservação textual exata

O contrato `exact-text-v1` grava todas as colunas CVM como Arrow `string`.
Isso altera os schemas persistidos: consumidores que dependiam de `int64`,
`uint64`, `float64`, booleanos ou nulos inferidos devem migrar explicitamente.
O ZIP original permanece disponível mesmo após extração bem-sucedida.

| Entrada CSV | Parquet anterior | Parquet `exact-text-v1` |
| --- | --- | --- |
| `000012345` | Inteiro sem os zeros iniciais | `"000012345"` |
| `1.234567890123456789` | Decimal arredondado em `float64` | `"1.234567890123456789"` |
| `1e-400` | `0.0` | `"1e-400"` |
| `N/A`, `NULL`, `None` | Nulo inferido | Texto original |
| Campo vazio | Nulo inferido | `""` |
| `TrUe` | Booleano | `"TrUe"` |
| CSV apenas com cabeçalho | Colunas Arrow `null` | Colunas Arrow `string`, zero linhas |

## Regeneração e troca do consumidor

1. Guarde os ZIPs originais e a saída antiga durante a migração.
2. Regenere os Parquet em um diretório novo com `automatic_extractor=True`.
   O padrão sem extração, `automatic_extractor=False`, continua disponível.
3. Confira `has_errors()` e os identificadores `{DOC}_{YEAR}` concluídos.
4. Confira o metadata `cvm.contract=exact-text-v1` nos arquivos regenerados.
5. Converta somente as colunas necessárias conforme seu dicionário de dados e
   teste esses consumidores antes de trocar o diretório lido pela aplicação.

Um Parquet antigo que já arredondou números ou removeu zeros não permite
recuperar o texto original. Regenerar exige o ZIP correspondente ou um novo
download oficial. Misturar schemas antigos e novos em um dataset pode causar
incompatibilidade ou coerções; mantenha a migração em um destino novo.

```python
from decimal import Decimal
from pathlib import Path

import pyarrow.parquet as pq

path = Path("cvm-exact/DFP/2024/dfp_cia_aberta_DRE_con_2024.parquet")
table = pq.read_table(path)
assert table.schema.metadata[b"cvm.contract"] == b"exact-text-v1"

raw_value = table.column("VL_CONTA")[0].as_py()
amount = Decimal(raw_value) if raw_value else None
```

A conversão de valores financeiros exige também interpretar moeda, escala,
exercício, versão e tipo de demonstração conforme o conjunto CVM. O pipeline
preserva os campos fornecidos; a consistência contábil do documento declarado
permanece uma validação de negócio do consumidor.

## Integridade e operação

Antes da publicação, o pipeline compara o SHA-256 de todos os registros
decodificados com o conteúdo reaberto do Parquet. Os metadados incluem
`cvm.contract`, `cvm.content-sha256`, `cvm.source-archive`,
`cvm.source-archive-sha256`,
`cvm.source-member` e `cvm.source-encoding`. A confirmação de extração exige
todos os Parquet esperados e sua associação ao ZIP consumido. Checksums de
página, leitura completa e `fsync` protegem a publicação persistida.

Todas as passagens leem o mesmo ZIP aberto; alterações na origem interrompem
a extração antes da publicação. Se uma revisão do ZIP remover ou renomear um
CSV, os Parquets obsoletos desse arquivo impedem o reprocessamento no mesmo
destino. Preserve a saída anterior e regenere a revisão em um diretório limpo;
a biblioteca não apaga arquivos antigos automaticamente.

Aspas continuam literais no dialeto `QUOTE_NONE`. Linhas curtas recebem campos
vazios ao final; o ZIP retido preserva a diferença entre campos ausentes e
campos vazios. Linhas com campos excedentes, cabeçalhos vazios ou duplicados,
mais de 4.096 colunas ou registros físicos acima de 8 MiB em UTF-8 falham
explicitamente. Row groups usam até 50.000 linhas, reduzidas para respeitar um
orçamento estimado de 16 MiB de dados e offsets; esse orçamento não é um limite
absoluto de RSS do processo.

UTF-8 e BOM UTF-8 são validados integralmente. Fora de UTF-8, a política
documentada distingue CP1252 de Latin-1 pelos bytes observados. Uma fonte sem
declaração de encoding pode ser ambígua; os bytes originais ficam no ZIP para
conferência independente.

Chamadas concorrentes para o mesmo destino são rejeitadas antes de substituir
o ZIP. `.cvm-write-lock/owner.json` identifica o processo responsável. Após
terminação abrupta, a biblioteca conserva esse lock e exige inspeção explícita
antes da recuperação: confirme que não existe escritor ativo, preserve a
evidência e recupere o estado derivado da transação. A biblioteca nunca toma
automaticamente um lock sem verificar sua autoridade. Falhas permanecem no
resultado; não interprete apenas a existência de um Parquet como sucesso.

IPE passa a incluir 2003 em diante. `get_available_years().ipe_min_year`
informa esse limite como propriedade; os quatro campos da tupla continuam
representando documentos gerais, ITR, CGVN/VLMO e ano corrente.

Consulte a [referência CVM](../reference/cvm-api.md) e o
[guia de testes](../dev-guide/testing.md) para a campanha oficial com comparação
independente de todos os arquivos e registros.
