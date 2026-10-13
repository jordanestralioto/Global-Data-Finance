# API B3 - Referência Técnica

Documentação técnica detalhada da API B3.

______________________________________________________________________

## HistoricalQuotesB3

### Classe Principal

```python
class HistoricalQuotesB3:
    """Interface de alto nível para cotações B3."""
```

### Telemetria de execução

A propriedade `last_phase_timings: dict[str, Any]` disponibiliza a telemetria
da última extração para instrumentação e benchmarks. Ela começa vazia e é
reiniciada quando uma nova extração começa. As observações incluem o backend
efetivo, o limite de workers e os tempos das fases executadas. Esse diagnóstico
é separado do resultado `ExtractionResultB3` e dos metadados Parquet.

### Métodos

#### `extract()`

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

| Nome               | Tipo                | Obrigatório | Padrão                 | Descrição                                                                      |
| ------------------ | ------------------- | ----------- | ---------------------- | ------------------------------------------------------------------------------ |
| `path_of_docs`     | `str`               | Sim         | -                      | Diretório contendo arquivos COTAHIST ZIP ou TXT                                 |
| `assets_list`      | `list[str] \| None` | Não         | `None` (`["todos"]`)   | Classes; `todos` seleciona todo TPMERC numérico válido                           |
| `initial_year`     | `int \| None`       | Não         | `None` (1986)          | Ano inicial da extração (inclusivo, >= 1986)                                   |
| `last_year`        | `int \| None`       | Não         | `None` (ano atual)     | Ano final da extração (inclusivo)                                              |
| `destination_path` | `str \| None`       | Não         | `None` (`path_of_docs`)| Diretório de destino do Parquet gerado                                         |
| `output_filename`  | `str`               | Não         | `"cotahist_extracted"` | Nome base obrigatório (basename); `.parquet` é opcional e acrescentado apenas quando ausente |
| `processing_mode`  | `str`               | Não         | `"fast"`               | Modo de processamento: `"fast"` (paralelo) ou `"slow"` (baixo consumo de RAM) |
| `verbose`          | `bool`              | Não         | `True`                 | Se `True`, imprime o resumo formatado no console                               |

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
- `ExtractionError`: Erro durante a leitura ou escrita dos dados.

**Exemplo**:

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações", "etf"],
    initial_year=2022,
    last_year=2023,
    processing_mode="fast",
)
print(f"Extraídos {result['total_records']:,} registros")
```

#### `get_available_assets()`

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

#### `get_available_years()`

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

#### Propriedades da Instância

- `settings: Settings`: Snapshot imutável da configuração de runtime do cliente.

______________________________________________________________________

## Configuração de Execução e Variáveis de Ambiente

As variáveis abaixo são resolvidas ao construir `HistoricalQuotesB3()`. Elas não
alteram uma instância já existente, nem adicionam parâmetros ao construtor
público. O backend por processos é experimental e requer ativação explícita.
Avalie o tempo completo, CPU e RSS agregado no corpus do consumidor antes de
adotá-lo. As condições e medições estão no
[guia de performance COTAHIST](../dev-guide/cotahist-performance.md).

- `GDF_B3_EXECUTOR_BACKEND`: Define o backend executor de paralelismo no modo `fast` (`"thread"` ou `"process"`). O padrão é `"thread"`.
  - `"thread"`: Utiliza `ThreadPoolExecutor`. Menor sobrecarga de inicialização e menor consumo global de memória. Recomendado para a maioria dos fluxos.
  - `"process"`: Utiliza `ProcessPoolExecutor` com contexto `spawn` somente para experimentos controlados. Ele pode reduzir o RSS medido do processo pai ao isolar buffers de cada arquivo em processos separados, mas também acrescenta custo de `spawn`, pode aumentar a soma de RSS dos workers e não oferece ganho de tempo garantido.
  - Fallback automático: Se `processing_mode="slow"`, houver apenas 1 arquivo de entrada ou o limite de workers for inferior a 2, o sistema realiza fallback seguro para `"thread"`.
  - Preflight anual: Em `fast` com `process`, a validação pode usar processos quando a política admite pelo menos dois workers e os candidatos anuais somam pelo menos 64 MiB armazenados. ZIP e TXT coexistentes entram na soma. Cargas menores e erros de leitura do tamanho seguem a validação serial. A ordem das fontes, o primeiro erro e suas causas tipadas são preservados; todos os workers são encerrados antes de concluir um cancelamento ou uma falha.
  - Limitações de contrato:
    1. Os workers filhos criam instâncias padrão de leitor e parser; colaboradores customizados injetados internamente não são serializados entre processos nesta versão.
    2. O multiprocessing via `spawn` requer módulos Python importáveis e não oferece suporte à execução interativa via `<stdin>` (`python -`).
- `GDF_B3_WORKER_LIMIT`: Limite opcional de workers para o modo `fast`. Use um inteiro positivo; o limite efetivo continua sendo o menor entre esse valor, a quantidade de arquivos, CPUs disponíveis e orçamento de memória. O modo `slow` continua com um worker. Um valor não numérico preserva o teto padrão; valores menores que um são limitados a um worker.

______________________________________________________________________

## Classes de Ativos

| Código           | Descrição           | Códigos TPMERC B3                                       |
| ---------------- | ------------------- | ------------------------------------------------------- |
| `ações`          | Ações               | 010 (Mercado à Vista), 020 (Mercado Fracionário)        |
| `etf`            | ETFs                | 010 (Mercado à Vista), 020 (Mercado Fracionário)        |
| `opções`         | Opções              | 070 (Opções de Compra), 080 (Opções de Venda)           |
| `termo`          | Mercado a Termo     | 030 (Mercado a Termo)                                   |
| `exercicio_opcoes`| Exercício de Opções| 012 (Exercício Compra), 013 (Exercício Venda)           |
| `forward`        | Contratos forward   | 050 (Forward c/ Ganho), 060 (Forward c/ Movimentação)  |
| `leilao`         | Leilão              | 017 (Mercado de Leilão)                                 |
| `lote_bloco`     | Lote em bloco       | 021 (BBT e Midpoint)                                    |
| `todos`          | Seleção completa    | Todo TPMERC numérico válido                             |

As strings em português desta tabela são valores canônicos de `assets_list` e
devem ser passadas exatamente como mostradas. BDRs e Futures são **Planned** e
não são aceitos pelo contrato atual do runtime.

______________________________________________________________________

## Modos de Processamento

| Modo     | Throughput medido* | Pico RSS medido* | Paralelismo padrão                                  | Cenário Indicado        |
| -------- | -----------------: | ---------------: | --------------------------------------------------- | ----------------------- |
| **fast** | 34.313,8 reg/s    | 429,88 MiB       | Até 4 workers, limitado por CPUs, memória e arquivos-fonte | Priorizar velocidade    |
| **slow** | 29.759,9 reg/s    | 331,11 MiB       | 1 worker                                            | Reduzir uso de memória  |

*Medição histórica da implementação v3 em 27 arquivos anuais (2000–2026),
22.303.577 registros e sem 2.283 cotações `021`. Não representa o schema v2 e
não é comparável diretamente. Consulte os [detalhes do benchmark](../dev-guide/benchmarks.md).*

O modo `fast` coordena o paralelismo por arquivo-fonte. O modo `slow` utiliza um
único worker para reduzir o consumo de memória.

______________________________________________________________________

## Documentação Relacionada

- [Guia de Uso B3](../user-guide/b3-docs.md)
- [Exceções](exceptions.md)
