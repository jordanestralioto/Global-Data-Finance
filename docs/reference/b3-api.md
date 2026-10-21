# API B3 - Referência Técnica

Contratos de entrada, resultados e execução de `HistoricalQuotesB3`.
Para preparar os arquivos locais, consulte o [guia B3](../user-guide/b3-docs.md).

______________________________________________________________________

## HistoricalQuotesB3

### Importação

```python
from globaldatafinance import HistoricalQuotesB3
```

### Telemetria de execução

A propriedade `last_phase_timings: dict[str, Any]` disponibiliza a telemetria
da última extração para instrumentação e benchmarks. Ela começa vazia e é
reiniciada quando uma nova extração começa. As observações incluem o backend
efetivo, o limite de workers e os tempos das fases executadas. Esse diagnóstico
é separado do resultado `ExtractionResultB3` e dos metadados Parquet.

### Construção e configuração

```python
def __init__(self, *, settings: Settings | None = None) -> None:
    ...
```

Importe `Settings` de `globaldatafinance.core.config`. O argumento opcional
injeta um snapshot imutável; com `None`, o cliente cria um snapshot do ambiente
atual. A propriedade `settings` retorna a configuração usada. Consulte
[configuração](../dev-guide/advanced-usage.md#configuracao-global).

### `extract()`

```python
def extract(
    self,
    path_of_docs: str,
    assets_list: list[str] | None = None,
    initial_year: int | None = None,
    last_year: int | None = None,
    destination_path: str | None = None,
    output_filename: str = "cotahist_extracted",
    processing_mode: str = "fast",
    verbose: bool = True,
) -> ExtractionResultB3:
    ...
```

**Descrição**: Extrai cotações históricas de arquivos COTAHIST (`COTAHIST_A{YYYY}.ZIP` ou `.TXT`), filtra os ativos e consolida o resultado em formato Parquet. A API aceita os dois formatos locais; o download oficial da B3 continua sendo distribuído em ZIP.

O parser é estrito: controles `00`/`99` e linhas vazias não são persistidos,
e TPMERC fora do filtro é contabilizado como filtrado. Todos os registros `01`
são validados antes do filtro. Se uma fonte contém registros inválidos, a
fachada retorna `success=False`, `output_file=""` e detalhes contextuais em
`errors`; o consumidor deve conferir o resultado. Chamadas diretas ao parser
podem levantar `ExtractionError`. Valores financeiros inválidos não recebem
fallback para zero ou nulo.

Dentro do destino validado, um link simbólico no arquivo de saída é rejeitado
com um resultado de falha, sem alterar o arquivo apontado. A publicação também
impede que o caminho de saída substitua uma fonte COTAHIST.

**Parâmetros**:

| Nome               | Tipo                | Obrigatório | Padrão                  | Descrição                                                                                    |
| ------------------ | ------------------- | ----------- | ----------------------- | -------------------------------------------------------------------------------------------- |
| `path_of_docs`     | `str`               | Sim         | -                       | Diretório contendo arquivos COTAHIST ZIP ou TXT                                              |
| `assets_list`      | `list[str] \| None` | Não         | `None` (`["todos"]`)    | Classes; `todos` seleciona todo TPMERC numérico válido                                       |
| `initial_year`     | `int \| None`       | Não         | `None` (1986)           | Ano inicial da extração (inclusivo, >= 1986)                                                 |
| `last_year`        | `int \| None`       | Não         | `None` (ano atual)      | Ano final da extração (inclusivo)                                                            |
| `destination_path` | `str \| None`       | Não         | `None` (`path_of_docs`) | Diretório de destino do Parquet gerado                                                       |
| `output_filename`  | `str`               | Não         | `"cotahist_extracted"`  | Nome base obrigatório (basename); `.parquet` é opcional e acrescentado apenas quando ausente |
| `processing_mode`  | `str`               | Não         | `"fast"`                | Modo de processamento: `"fast"` (paralelo) ou `"slow"` (baixo consumo de RAM)                |
| `verbose`          | `bool`              | Não         | `True`                  | Se `True`, imprime o resumo formatado no console                                             |

As barras `Validating B3 files` e `Processing B3 files` aparecem em `stdout`
nos modos `fast` e `slow`, independentemente de `verbose`. Elas contam fontes
anuais encontradas: a primeira avança após a validação de uma fonte; a segunda
avança quando uma tentativa de processamento termina, inclusive com erro.
O resumo é emitido somente quando `verbose=True`. A consolidação, a leitura de
verificação e a publicação do Parquet continuam após a barra de processamento;
o resultado retornado confirma o sucesso completo. Falhas e cancelamento
encerram a linha da barra com o contador observado. Seleções sem arquivos não
exibem barras vazias.

**Retorno (`ExtractionResultB3`)**:

Objeto `TypedDict` contendo o resultado da extração:

- `success: bool` — Indica se a extração foi concluída com sucesso.
- `message: str` — Mensagem descritiva com o resumo da execução.
- `total_files: int` — Quantidade de entradas anuais resolvidas para a solicitação.
- `success_count: int` — Quantidade de fontes incluídas na saída publicada.
- `error_count: int` — Quantidade de entradas em `errors`.
- `total_records: int` — Quantidade de linhas da saída publicada.
- `output_file: str` — Caminho da nova saída publicada; vazio em caso de falha.
- `errors: dict[str, str]` — Dicionário mapeando arquivos com falha para a mensagem de erro (se houver).
- `assets: list[str]` — Lista de classes de ativos filtradas.
- `processing_mode: str` — Modo de processamento utilizado (`"fast"` ou `"slow"`).
- `elapsed_time: float` — Tempo total de execução em segundos.
- `schema_version: int` — Versão do schema Parquet (`2`).
- `integrity: B3IntegrityReport` — Cobertura, seleção, fontes, verificações,
  avisos e hash da saída publicada.

Quando o preflight falha, `integrity` preserva as fontes já validadas, os anos
ausentes e a seleção normalizada. Os contadores `success_count` e
`total_records` permanecem zerados. Cada fonte validada inclui hashes da
entrada e do conteúdo, tamanho descompactado, contagens por mercado,
controles originais em Base64, data de geração, intervalo de pregões,
convenção do trailer, linhas vazias, avisos e digests esperados e verificados.

**Semântica de entrada e resultado vazio**:

- A API aceita `COTAHIST_A{YYYY}.ZIP` e `COTAHIST_A{YYYY}.TXT`; quando os dois
  formatos existem para o mesmo ano, ambos são validados integralmente. O ZIP
  é selecionado somente quando os conteúdos descompactados são idênticos;
  conteúdos diferentes causam falha.
- Cada leitura de ZIP verifica o CRC de todos os membros, inclusive os não
  selecionados, e lê o membro COTAHIST no mesmo arquivo aberto e validado.
  As validações são renovadas a cada passagem, com os limites de descompressão
  e as verificações de identidade da fonte preservados.
- `output_filename` deve ser um basename, sem separadores de caminho. O sufixo
  `.parquet` é aceito; quando omitido, é acrescentado automaticamente uma única
  vez.
- A falta de qualquer ano solicitado retorna `success=False`, lista o ano em
  `integrity.missing_years` e não publica uma nova saída. Um diretório vazio
  informa zero arquivos resolvidos e todos os anos solicitados como ausentes.
- Se todas as fontes solicitadas são válidas e o filtro exclui todas as suas
  cotações, a extração publica um resultado vazio (`success=True`).

Se arquivos válidos não tiverem registros após o filtro de ativos, a extração
continua bem-sucedida e publica Parquet B3 vazio com schema explícito.

`assets_list=None` aplica `todos`, incluindo códigos TPMERC numéricos desconhecidos;
`lote_bloco` seleciona `021`. A implementação valida todos os campos antes de
filtrar, exige cada ano solicitado e lê a saída completa antes de publicar.
Falhas e lacunas de ano retornam `success=False`; `integrity` contém a cobertura
observada e o motivo. Veja a [referência do schema COTAHIST v2](b3-schema-v2.md)
e o [guia de migração](../user-guide/migration-pyarrow-integrity.md).

Em um cancelamento assíncrono antes do commit, o serviço aborta a publicação,
limpa o estado temporário e relança `asyncio.CancelledError`; um artefato final
anterior permanece intacto.

A preparação, a recuperação e abertura da transação, as verificações dos
Parquets, a consolidação, a reconferência dos hashes e o rollback executam
fora da thread do event loop. Trabalhadores de threads e processos recebem
um sinal de cancelamento próprio de cada execução. O cancelamento
é observado nos limites de leitura e de lotes. O serviço aguarda o término
dos leitores e escritores antes de remover seus temporários, inclusive se
receber pedidos repetidos de cancelamento. Há um ponto de cancelamento
imediatamente antes da decisão de commit. Depois que essa decisão inicia a
publicação atômica, novos pedidos de cancelamento aguardam o término e a API
retorna o resultado da publicação. O commit também executa fora do event loop.

A reconferência final dos arquivos de entrada e a decisão de publicação
executam no mesmo trabalhador, sem retornar ao event loop entre elas. A leitura
dos hashes continua cancelável; o trabalhador verifica o cancelamento uma
última vez antes de iniciar a publicação. Alterações detectadas na fonte falham
e preservam a saída anterior. O chamador deve manter os ZIP/TXT inalterados
durante a extração: essa reconferência não bloqueia escritores externos nem
oferece isolamento absoluto contra modificações concorrentes.

Uma falha de limpeza posterior ao commit durável mantém `success=True`, o
caminho, as contagens verificadas e o hash da saída publicada. O diagnóstico
fica em `integrity.warnings`: `PUBLICATION_CLEANUP_RECOVERED` indica que a
nova tentativa de limpeza funcionou; `PUBLICATION_CLEANUP_PENDING` indica que
o estado de recuperação foi preservado. Nesses avisos, `source` identifica o
nome do Parquet publicado. O diagnóstico original também fica no log.
Falhas anteriores ao commit continuam retornando falha e preservando a saída
anterior por rollback.

**Exceções**:

- `EmptyAssetListError`: Lista de ativos vazia; `None` seleciona `todos`.
- `InvalidAssetsName`: Classe de ativo não suportada.
- `InvalidFirstYear`: Ano inicial fora da faixa válida (1986 até o ano atual).
- `InvalidLastYear`: Ano final fora da faixa válida ou menor que o ano inicial.
- `InvalidOutputFilename`: Nome de arquivo de saída inválido (contém barras ou traversal).
- `InvalidProcessingMode`: Modo diferente de `"fast"` ou `"slow"`.
- `InvalidDestinationPathError`: Caminho vazio ou composto apenas por espaços.
- `PathIsNotDirectoryError`: Caminho de entrada ausente ou que não é diretório.
- `SecurityError`: Caminho rejeitado pela política de segurança.

Falhas de conteúdo e processamento são consolidadas em `errors` com
`success=False`. Consulte o [catálogo de exceções](exceptions.md) para os
tipos usados por chamadas de baixo nível.

**Exemplo**:

```python
from globaldatafinance import HistoricalQuotesB3

def main() -> None:
    b3 = HistoricalQuotesB3()
    result = b3.extract(
        path_of_docs="/data/cotahist",
        assets_list=["ações", "opções"],
        initial_year=2022,
        last_year=2023,
        processing_mode="fast",
    )
    if not result["success"]:
        raise RuntimeError(result["errors"] or result["message"])
    print(f"Extraídos {result['total_records']:,} registros")


if __name__ == "__main__":
    main()
```

### `extract_async()`

Variante assíncrona de `extract()`, com os mesmos argumentos, padrões e
resultado. Em notebooks ou aplicações com event loop ativo, use
`await client.extract_async(...)` em vez do wrapper síncrono. A assinatura
completa também está na [visão geral da API](../dev-guide/api-reference.md).

### `get_available_assets()`

```python
def get_available_assets(self) -> list[str]:
    ...
```

**Descrição**: Retorna lista de classes de ativos disponíveis.

**Retorno**: Lista de strings

**Exemplo**:

```python
assets = b3.get_available_assets()
# ['ações', 'etf', 'opções', 'termo', 'exercicio_opcoes', 'forward', 'leilao', 'lote_bloco', 'todos']
```

### `get_available_years()`

```python
def get_available_years(self) -> dict[str, int]:
    ...
```

**Descrição**: Retorna dicionário com os limites dos anos disponíveis.

**Retorno**: Dicionário contendo `minimal_year` e `current_year`.

**Exemplo**:

```python
years = b3.get_available_years()
# `current_year` corresponde ao ano corrente de execução.
```

### Propriedades da instância

- `settings: Settings`: Snapshot imutável da configuração de runtime do cliente.

______________________________________________________________________

## Relatório de integridade

`result["integrity"]` é um `B3IntegrityReport`. Todas as chaves abaixo estão
presentes, inclusive em falhas; valores anuláveis usam `None`. Datas são strings
ISO `YYYY-MM-DD`. Contagens e flags se referem às fontes fornecidas, sem
reconciliação com um calendário ou cadastro externo de instrumentos.

| Chave | Tipo | Significado |
| --- | --- | --- |
| `status` | `Literal["passed", "failed", "not_run"]` | Estado da verificação |
| `schema_version` | `int` | Versão do schema, `2` |
| `verification_method` | `str` | Método de verificação ou `"not completed"` |
| `requested_years` | `list[int]` | Anos solicitados |
| `selected_years` | `list[int]` | Anos das fontes selecionadas e validadas |
| `missing_years` | `list[int]` | Anos solicitados sem fonte |
| `complete_market_selection` | `bool` | Seleção `todos`, incluindo códigos numéricos desconhecidos |
| `market_codes` | `list[str]` | Códigos selecionados; vazio na seleção completa |
| `asset_classes` | `list[str]` | Aliases normalizados e sem duplicatas |
| `raw_quotes` | `int` | Total de registros `01` nas fontes validadas |
| `selected_quotes` | `int` | Registros selecionados pelo filtro |
| `intentional_exclusions` | `int` | Registros excluídos pelo filtro |
| `excluded_records` | `int` | Mesmo valor de `intentional_exclusions` |
| `written_rows` | `int` | Linhas escritas |
| `verified_rows` | `int` | Linhas conferidas na leitura de verificação |
| `selection_complete` | `bool` | Verificação passou e selecionadas = escritas = verificadas |
| `source_complete` | `bool` | Seleção completa em linhas, sem exclusões, e brutas = escritas = verificadas |
| `source_first_trading_date` | `str \| None` | Primeira data nas fontes validadas |
| `source_last_trading_date` | `str \| None` | Última data nas fontes validadas |
| `output_first_trading_date` | `str \| None` | Primeira data na saída verificada |
| `output_last_trading_date` | `str \| None` | Última data na saída verificada |
| `unknown_market_counts` | `dict[str, int]` | Contagens por TPMERC desconhecido |
| `warnings` | `list[B3IntegrityWarning]` | Avisos associados a uma fonte ou saída publicada |
| `sources` | `list[B3SourceIntegrityReport]` | Evidência por fonte, detalhada abaixo |
| `ignored_duplicate_sources` | `list[str]` | TXTs equivalentes preteridos em favor do ZIP |
| `output_sha256` | `str \| None` | SHA-256 da saída publicada; `None` sem saída confirmada |

Cada item de `sources` contém estas chaves obrigatórias:

| Chave | Tipo | Significado |
| --- | --- | --- |
| `source` | `str` | Nome do arquivo de entrada |
| `year` | `int` | Ano da fonte |
| `member` | `str` | Membro ZIP; vazio para TXT |
| `outer_sha256` | `str` | SHA-256 do arquivo de entrada |
| `content_sha256` | `str` | SHA-256 dos bytes COTAHIST descompactados |
| `uncompressed_bytes` | `int` | Tamanho do conteúdo descompactado |
| `market_counts` | `dict[str, int]` | Contagens por TPMERC |
| `unknown_market_counts` | `dict[str, int]` | Contagens por TPMERC desconhecido |
| `header_records` | `int` | Contagem de controles `00` |
| `trailer_records` | `int` | Contagem de controles `99` |
| `generation_date` | `str` | Data de geração declarada |
| `blank_lines` | `int` | Linhas vazias observadas |
| `warnings` | `list[B3SourceWarningReport]` | Avisos da fonte |
| `raw_quotes` | `int` | Total de registros `01` |
| `selected_quotes` | `int` | Registros selecionados |
| `intentional_exclusions` | `int` | Registros excluídos pelo filtro |
| `excluded_records` | `int` | Mesmo valor de `intentional_exclusions` |
| `written_rows` | `int` | Linhas escritas desta fonte |
| `verified_rows` | `int` | Linhas verificadas desta fonte |
| `declared_records` | `int` | Contagem declarada no trailer |
| `trailer_convention` | `str` | Convenção usada na contagem do trailer |
| `first_trading_date` | `str` | Primeira data de pregão da fonte |
| `last_trading_date` | `str` | Última data de pregão da fonte |
| `header_base64` | `str` | Controle `00` original em Base64 |
| `trailer_base64` | `str` | Controle `99` original em Base64 |
| `expected_rows_sha256` | `str` | Digest ordenado das linhas selecionadas no preflight |
| `verified_rows_sha256` | `str \| None` | Digest conferido na saída; `None` antes da verificação |

`B3SourceWarningReport` contém `code: str`, `count: int` e `explanation: str`.
`B3IntegrityWarning` acrescenta `source: str`, o nome da fonte ou do Parquet
publicado. Os códigos de limpeza pós-commit estão descritos em `extract()`.
O [schema B3 v2](b3-schema-v2.md) define o framing do digest de linhas.

## Configuração de Execução e Variáveis de Ambiente

`GDF_B3_EXECUTOR_BACKEND` é resolvido ao construir `HistoricalQuotesB3()` e não
altera uma instância existente. `GDF_B3_WORKER_LIMIT` é lido pela política de
recursos ao calcular a admissão de workers. Essas opções não adicionam parâmetros
ao construtor público. O padrão `process` é aplicado em `fast` com duas fontes, dois
workers e contexto compatível com `spawn`. As condições e medições estão no
[guia de performance COTAHIST](../dev-guide/cotahist-performance.md).

- `GDF_B3_EXECUTOR_BACKEND`: Aceita `"thread"` ou `"process"`; o padrão é `"process"`.
  - `"thread"`: Usa `ThreadPoolExecutor`, com menor custo de inicialização e buffers no processo pai.
  - `"process"`: Usa `ProcessPoolExecutor` com `spawn` nas condições elegíveis. Isola buffers por fonte e pode aumentar o RSS agregado. Avalie tempo completo, CPU e memória no corpus do consumidor.
  - Fallback: `slow`, uma fonte ou limite de um worker usam um worker de thread. Daemons e sessões sem módulo principal importável ou script legível usam threads. O logger registra a incompatibilidade e `last_phase_timings['effective_backend']` informa o backend efetivo. Falhas após a submissão mantêm diagnósticos e limpeza normal.
  - Preflight anual: Em `fast` com `process`, admite processos quando a política permite pelo menos dois workers, o contexto é compatível e os candidatos anuais somam pelo menos 64 MiB armazenados. ZIP e TXT coexistentes entram na soma. Cargas menores e erros de leitura do tamanho seguem validação serial. Ordem, primeiro erro, causas tipadas e encerramento dos workers antes da limpeza são preservados.
  - Os workers filhos criam leitores e parsers padrão; colaboradores customizados injetados internamente não são serializados. Use threads para esses colaboradores.
  - Scripts devem proteger a chamada com `if __name__ == '__main__':`. Defina `GDF_B3_EXECUTOR_BACKEND=thread` para selecionar threads explicitamente. Valores inválidos geram `ValueError` na construção.
- `GDF_B3_WORKER_LIMIT`: Limite opcional de workers para o modo `fast`. Use um inteiro positivo; o limite efetivo continua sendo o menor entre esse valor, a quantidade de arquivos, CPUs disponíveis e orçamento de memória. O modo `slow` continua com um worker. Um valor não numérico preserva o teto padrão; valores menores que um são limitados a um worker.

______________________________________________________________________

## Classes de Ativos

| Código             | Descrição           | Códigos TPMERC B3                                     |
| ------------------ | ------------------- | ----------------------------------------------------- |
| `ações`            | Ações               | 010 (Mercado à Vista), 020 (Mercado Fracionário)      |
| `etf`              | ETFs                | 010 (Mercado à Vista), 020 (Mercado Fracionário)      |
| `opções`           | Opções              | 070 (Opções de Compra), 080 (Opções de Venda)         |
| `termo`            | Mercado a Termo     | 030 (Mercado a Termo)                                 |
| `exercicio_opcoes` | Exercício de Opções | 012 (Exercício Compra), 013 (Exercício Venda)         |
| `forward`          | Contratos forward   | 050 (Forward c/ Ganho), 060 (Forward c/ Movimentação) |
| `leilao`           | Leilão              | 017 (Mercado de Leilão)                               |
| `lote_bloco`       | Lote em bloco       | 021 (BBT e Midpoint)                                  |
| `todos`            | Seleção completa    | Todo TPMERC numérico válido                           |

As strings em português desta tabela são os aliases aceitos por `assets_list`.
A validação converte os valores para minúsculas; grafia e acentos continuam
relevantes. `ações` e `etf` selecionam os mesmos mercados `010` e `020`, sem
distinguir ações de ETFs ou classificar emissores. Os aliases `bdr` e `futuro`
não estão no catálogo. Use `get_available_assets()` para consultar os valores
aceitos na versão instalada.

______________________________________________________________________

## Modos de Processamento

| Modo | Execução | Uso |
| --- | --- | --- |
| `fast` | Fontes concorrentes dentro dos limites de CPU, memória e quantidade de arquivos; teto padrão de 4 workers | Permitir paralelismo por fonte |
| `slow` | Um worker de fonte e lotes menores | Limitar concorrência e uso de memória |

Ambos usam lotes limitados e o mesmo schema e validações. `slow` não reduz o
conjunto solicitado nem o espaço necessário para os temporários e a saída.
As [medições COTAHIST](../dev-guide/cotahist-performance.md) registram ambiente,
corpus e resultados. Os números do schema anterior permanecem nos
[benchmarks históricos](../dev-guide/benchmarks.md).

Para consumidores que importam `ProcessingModeEnumB3` pelo namespace da fonte,
os valores `FAST` e `SLOW` permanecem. Na revisão de 20/10/2026, foram removidas
as propriedades `desired_concurrent_files`, `desired_workers`,
`use_parallel_parsing` e `memory_threshold_mb`, que não controlavam a extração.
Os limites efetivos continuam sendo calculados por `ResourcePolicyB3`, e o
backend e a quantidade efetiva de workers são expostos pela telemetria.

______________________________________________________________________

## Documentação Relacionada

- [Guia de Uso B3](../user-guide/b3-docs.md)
- [Exceções](exceptions.md)
