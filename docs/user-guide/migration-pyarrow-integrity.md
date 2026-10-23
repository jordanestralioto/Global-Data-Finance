# Migração 0.2.0: PyArrow e integridade de ingestão

A versão `0.2.0` substitui os caminhos produtivos de ingestão por PyArrow,
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
| Namespace de arquivo canônico | Use `Settings.archive`; `Settings.archive_safety` não existe mais e não há alias de compatibilidade. |
| Configuração de logging estrita | Use apenas os campos e variáveis documentados de `LoggingSettings`; `LoggingSettings(structured=True)` e variáveis `DATAFIN_LOG_*` desconhecidas agora falham com `ValidationError`. |
| Destino e contexto de logging | Use um `log_file` em diretório aprovado pela aplicação; raízes/diretórios protegidos são rejeitados, e campos comuns de segredo recebem redação de melhor esforço. Não envie segredos ao logging. |
| Preservação CVM exata | Regenere os Parquets como `exact-text-v1`; todas as colunas são `string` e conversões numéricas são explícitas. |
| Corte interno B3 | Remova `data_writer` de integrações que constroem `ExtractionServiceB3` e não passe `resource_monitor` para `ParquetWriterB3`; use as fachadas e as assinaturas atuais. |
| Sentinela B3 reservada | O texto literal `__GLOBALDATAFINANCE_NULL__` não é um valor aceito; use `None` para nulos. |

## CVM

O contrato CVM atual é `exact-text-v1`: colunas `string`, campos vazios como
`""`, valores originais preservados e ZIP retido após extração. `QUOTE_NONE`
mantém aspas literais e linhas curtas recebem somente campos vazios finais.
A publicação de vários Parquets permanece recuperável por lote, com confirmação
de todos os registros antes da promoção. Consulte a
[migração CVM exata](migration-cvm-exact-text.md) para regeneração dos arquivos,
conversões explícitas e inspeção de locks após interrupção.

O logging da biblioteca não altera o root logger da aplicação. Antes de uma
chamada explícita a `setup_logging()`, o namespace `globaldatafinance` usa
`NullHandler` e permanece silencioso; uma falha ao reconfigurar handlers
preserva a configuração anterior.

## B3

### Notas para a release 0.2.0

O texto abaixo é o corpo preparado para a release 0.2.0 no GitHub.
O workflow existente `.github/workflows/publish.yml` executa os gates e a
publicação a partir do evento de release publicada. A versão, tag e publicação
devem aguardar a aprovação das evidências de aceitação; este texto não afirma
que a release já foi publicada.

**Mudanças incompatíveis do contrato COTAHIST:**

- A seleção padrão agora preserva todas as cotações `01`, incluindo TPMERC
  `021` e mercados numéricos desconhecidos. Omita `assets_list` ou use `todos`;
  use classes explícitas quando o consumidor precisar de um filtro.
- O Parquet passa para o schema versionado `2`, com 32 colunas. Os 20 campos
  anteriores mantêm sua ordem e valores; as 12 adições incluem os campos
  oficiais antes ausentes, proveniência e os 245 bytes originais.
- Regenere Parquets v1 a partir dos ZIP/TXT originais. Append e merge entre
  schemas incompatíveis falham; uma conversão dos arquivos v1 não recupera os
  dados ausentes. Siga os procedimentos de corte e rollback desta página.
- Informe um intervalo anual disponível: qualquer ano solicitado ausente ou
  registro inválido, inclusive em mercado excluído pelo filtro, falha a extração.
- A publicação exige leitura integral da saída staged e verificação exata dos
  dados e do manifesto. Falhas preservam a saída anterior; consumidores devem
  verificar `success`, `schema_version` e `integrity` antes de mudar de arquivo.

O corpus local de aceitação cobre 2000–2026 e seu snapshot termina em
2026-09-02. A release deve anexar as evidências finais do corpus congelado e os
manifestos de checksums; esses limites não são uma confirmação externa de
completude da bolsa ou de disponibilidade de todos os anos históricos.

Todas as linhas `01` são validadas e convertidas antes da seleção de mercados.
Linhas vazias e controles `00`/`99` são contados, e qualquer outro identificador
não vazio falha. Ambos os modos usam a conversão canônica e lotes limitados
de linhas CSV pelo Arrow. `fast` usa lotes de até 25.000 registros e pode
processar fontes em paralelo; `slow` usa lotes de até 10.000 registros e um
worker. Os modos preservam o mesmo schema, ordem e valores lógicos.

### B3 schema v2 e regeneração

O contrato persistido COTAHIST mudou de forma incompatível para o schema
versionado `2`. O padrão agora é `assets_list=None`, equivalente a
`assets_list=["todos"]`: todas as cotações `01` com TPMERC numérico são
preservadas, incluindo `021` e códigos ainda desconhecidos. A saída tem 32
colunas, incluindo os cinco campos oficiais antes ausentes, coordenadas da
fonte e os 245 bytes originais de cada cotação. Valores financeiros são
decimais exatos; `preco_exercicio_pontos` usa escala 6.

Parquets v1 não contêm linhas TPMERC `021`, todos os campos oficiais nem bytes
originais. Não converta nem acrescente esses arquivos para v2: regenere a partir
dos ZIP/TXT brutos e valide o resultado antes de trocar o consumidor.

Procedimento de corte:

1. Preserve as fontes COTAHIST e registre seus hashes.
2. Escolha o intervalo anual realmente disponível. Informe
   `initial_year` e `last_year`; os padrões continuam cobrindo 1986 até o ano
   atual e uma lacuna no intervalo solicitado falha a extração.
3. Gere a saída em outro diretório, usando `assets_list=["todos"]` (ou omita
   `assets_list`).
4. Exija `result["success"] is True` e `result["schema_version"] == 2`.
   Confirme `result["integrity"]["selection_complete"]`,
   `source_complete`, contagens, anos selecionados e `output_sha256` conforme
   a necessidade do consumidor.
5. Leia o schema Arrow e adapte os consumidores às 12 colunas adicionais e
   aos tipos exatos listados na [referência do schema B3 v2](../reference/b3-schema-v2.md).
6. Troque os consumidores para a saída verificada e retenha os arquivos v1 até
   aceitar o corte.

Procedimento de rollback:

1. Preserve juntos a versão anterior do pacote, a configuração dos consumidores
   e os caminhos dos Parquets v1 até aceitar a migração. Registre o SHA-256 de
   cada saída anterior e gere v2 em um diretório separado.
2. Se a aceitação falhar, restaure a versão anterior do pacote e a configuração
   dos consumidores para ler os caminhos v1 preservados. Mantenha os COTAHIST
   originais e os artefatos v2 separados disponíveis para diagnóstico.
3. Confira os hashes v1 preservados e reabra esses arquivos com o consumidor
   anterior. Não sobrescreva v2 com v1 nem acrescente linhas entre versões.

A biblioteca publica uma saída escolhida pelo chamador; mudar o caminho lido
pelo consumidor pertence à aplicação. Uma extração malsucedida preserva o
arquivo anterior nesse caminho e retorna `output_file=""`. Essas garantias são
exercitadas por `tests/application/b3_docs/test_publication_integrity.py` e
`tests/application/b3_docs/test_schema_migration.py`.

Um Parquet v2 filtrado pode ter zero linhas e ainda ser completo para a seleção
solicitada; consulte `selection_complete`, `source_complete` e as contagens de
exclusões no relatório. `source_complete=True` exige nenhuma exclusão. Os
relatórios incluem hashes externos e descompactados, controles codificados,
convenção do trailer, datas observadas, digest das linhas e hash do Parquet.
Esse hash atesta os arquivos fornecidos; não confirma calendário de negociação
ou instrumentos fora do corpus. A faixa anterior a 2000 exige suas próprias
fontes, que não fazem parte do corpus local auditado.

Integrações que dependiam de objetos internos removidos devem migrar para o
fluxo da fachada. A session B3 agora tem ciclo de vida explícito (`NEW` →
`OPEN` → `CLOSED`) e não pode ser reaberta depois do fechamento, inclusive
quando a validação final falha.

Os workers internos usam apenas a conversão canônica de `CotahistParserB3`,
incluindo as verificações de releitura e digest para subclasses. Fábricas
customizadas que ofereciam somente `parse_line()` devem implementar o contrato
completo do parser; o caminho alternativo de dicionários foi removido. O helper
interno `normalize_decimal_v99` e os tipos sem consumidores
`ZipProcessingResult`/`ProcessSingleFileResult` foram removidos. Use
`normalize_decimal` com escala explícita em extensões internas.

As interfaces de leitura textual e `ParquetWriterB3` com consumidores existentes
continuam disponíveis sobre a implementação atual. A documentação do módulo
fica em `README.md` e `README.en.md`; a cópia antiga `README.pt.md` foi removida.

## Dependências e medição

O `ReadFilesAdapter` foi removido junto com a dependência automática de Pandas;
consumidores que ainda quiserem DataFrames devem instalar Pandas por conta
própria. PyArrow é o único engine produtivo de CSV/Parquet. A migração completa
de timeout, adapters genéricos, fronteira de captura B3 e falhas de escrita está
em [Corte limpo de infraestrutura](migration-infrastructure-clean-cut.md).
Use `scripts/benchmark_ingestion.py` para medições locais em processo novo;
seus números dependem de hardware, ambiente e corpus, portanto não são uma
garantia universal de tempo ou RSS.
