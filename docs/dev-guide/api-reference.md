# Referência da API

Documentação completa da API pública do Global-Data-Finance.

______________________________________________________________________

## Módulo `globaldatafinance` (Exportações da Raiz)

As classes e contratos principais são exportados diretamente no nível raiz do pacote:

```python
from globaldatafinance import (
    FundamentalStocksDataCVM,
    HistoricalQuotesB3,
    ExtractionResultB3,
)
```

______________________________________________________________________

### `FundamentalStocksDataCVM`

Interface de alto nível para download e extração de demonstrativos financeiros regulatórios da CVM.

#### Métodos

**`__init__()`**

```python
def __init__(self) -> None:
    ...
```

Inicializa o cliente CVM com adaptadores assíncronos e pipelines de validação padrão.

**`download()`**

```python
def download(
    self,
    destination_path: str,
    list_docs: list[str] | None = None,
    initial_year: int | None = None,
    last_year: int | None = None,
    automatic_extractor: bool = False,
) -> DownloadResultCVM:
    ...
```

Baixa demonstrativos financeiros regulatórios da CVM para um diretório local.

**Parâmetros**:

- `destination_path` (`str`): Caminho do diretório de destino onde os arquivos serão salvos.
- `list_docs` (`list[str]`, opcional): Lista de códigos de documentos (ex.: `["DFP", "ITR"]`). Se `None`, baixa todos os tipos disponíveis.
- `initial_year` (`int`, opcional): Ano inicial da consulta (inclusivo). Se `None`, usa o ano mínimo suportado pelo documento.
- `last_year` (`int`, opcional): Ano final da consulta (inclusivo). Se `None`, usa o ano corrente do sistema.
- `automatic_extractor` (`bool`): Se `True`, extrai automaticamente os arquivos ZIP baixados para o formato Apache Parquet. Padrão: `False`.

Quando ativado, o extrator CVM usa PyArrow e o dialeto CSV `QUOTE_NONE`.
Linhas curtas recebem apenas nulos finais, linhas excedentes falham, e um CSV
somente com cabeçalho gera Parquet vazio com campos Arrow `null`. O lote de
múltiplos Parquets é publicado de forma recuperável; não há atomicidade de
visibilidade instantânea para leitores concorrentes.

**Retorno**:

- `DownloadResultCVM`: Objeto estruturado com as seguintes propriedades:
  - `success_count_downloads` (`int`): Quantidade de arquivos baixados com sucesso.
  - `error_count_downloads` (`int`): Quantidade de arquivos que falharam.
  - `successful_downloads` (`list[str]`): Lista de identificadores de documentos concluídos no formato `{DOC}_{YEAR}` (por exemplo, `DFP_2023`). Esses valores são identificadores lógicos, não caminhos completos ou nomes de arquivos.
  - `failed_downloads` (`dict[str, str]`): Mapeamento de identificadores de documentos para suas respectivas mensagens de erro.
  - `elapsed_time` (`float`): Tempo total de execução em segundos.
  - `has_errors()` (`bool`): Método auxiliar que indica se houve alguma falha.

**`async_download()`**

```python
async def async_download(
    self,
    destination_path: str,
    list_docs: list[str] | None = None,
    initial_year: int | None = None,
    last_year: int | None = None,
    automatic_extractor: bool = False,
) -> DownloadResultCVM:
    ...
```

Variante assíncrona do método `download()`. Utilize quando executar dentro de um event loop `asyncio` existente para evitar conflitos de execução.

**`get_available_docs()`**

```python
def get_available_docs(self) -> dict[str, str]:
    ...
```

Retorna um dicionário mapeando os códigos de documentos disponíveis (ex.: `"DFP"`, `"ITR"`, `"FCA"`, `"FRE"`, `"CGVN"`, `"VLMO"`, `"IPE"`) para suas descrições legais em português.

**`get_available_years()`**

```python
def get_available_years(self) -> AvailableYearsInfoCVM:
    ...
```

Retorna uma `namedtuple` `AvailableYearsInfoCVM` contendo os limites de anos disponíveis para cada categoria de documento:

- `general_min_year` (`int`): Ano mínimo para documentos gerais (ex.: 2010).
- `itr_min_year` (`int`): Ano mínimo para ITR (ex.: 2011).
- `cgvn_vlmo_min_year` (`int`): Ano mínimo para relatórios CGVN e VLMO (ex.: 2018).
- `current_year` (`int`): Ano corrente do sistema.

Também suporta conversão para dicionário via `years._asdict()`.

______________________________________________________________________

### `HistoricalQuotesB3`

Interface de alto nível para extração e consolidação de cotações históricas da B3 a partir de arquivos COTAHIST.

#### Métodos

**`__init__()`**

```python
def __init__(self) -> None:
    ...
```

Inicializa o cliente B3 com pipelines de parser posicional e formatadores padrão.

**`extract()`**

```python
def extract(
    self,
    path_of_docs: str,
    assets_list: list[str],
    initial_year: int | None = None,
    last_year: int | None = None,
    destination_path: str | None = None,
    output_filename: str = "cotahist_extracted",
    processing_mode: str = "fast",
    verbose: bool = True,
) -> ExtractionResultB3:
    ...
```

Analisa arquivos COTAHIST (`COTAHIST_A{YYYY}.ZIP` ou `.TXT`), filtra os registros conforme as classes de ativos selecionadas e gera um arquivo consolidado em formato Apache Parquet. O método público retorna um mapeamento `ExtractionResultB3` com status da operação, contagens, erros e o caminho do artefato; ele não retorna um DataFrame como contrato principal.

**Parâmetros**:

- `path_of_docs` (`str`): Diretório onde estão localizados os arquivos COTAHIST (`COTAHIST_A{YYYY}.ZIP` ou `.TXT`).
- `assets_list` (`list[str]`): Lista com as classes de ativos desejadas (ex.: `["ações", "etf"]`).
- `initial_year` (`int`, opcional): Ano inicial da extração (inclusivo, mínimo 1986).
- `last_year` (`int`, opcional): Ano final da extração (inclusivo, padrão: ano atual).
- `destination_path` (`str`, opcional): Diretório onde o arquivo Parquet será salvo. Se `None`, usa `path_of_docs`.
- `output_filename` (`str`): Nome base do arquivo de saída. Deve ser apenas um nome simples (basename), sem caminhos ou barras; o sufixo `.parquet` é opcional e é acrescentado quando omitido. Padrão: `"cotahist_extracted"`.
- `processing_mode` (`str`): Modo de processamento: `"fast"` (paralelizado, maior velocidade) ou `"slow"` (menor consumo de memória RAM). Padrão: `"fast"`.
- `verbose` (`bool`): Se `True` (padrão), exibe resumo formatado no console.

**Retorno**:

- `ExtractionResultB3` (`TypedDict`): Dicionário estruturado com as seguintes chaves:
  - `success` (`bool`): `True` se a extração ocorreu sem erros.
  - `message` (`str`): Resumo textual do resultado.
  - `total_files` (`int`): Total de arquivos de entrada processados (ZIP ou TXT).
  - `success_count` (`int`): Quantidade de arquivos processados com sucesso.
  - `error_count` (`int`): Quantidade de arquivos com falha.
  - `total_records` (`int`): Total de registros extraídos.
  - `output_file` (`str`): Caminho absoluto para o arquivo Parquet gerado.
  - `assets` (`list[str]`): Lista de classes de ativos filtradas.
  - `processing_mode` (`str`): Modo de processamento utilizado.
  - `elapsed_time` (`float`): Tempo total de extração em segundos.
- `errors` (`dict[str, str]`): Dicionário mapeando arquivos com falha para suas respectivas mensagens de erro. A chave está sempre presente e pode ser vazia.

O download oficial da B3 usa arquivos ZIP, mas a API aceita tanto
`COTAHIST_A{YYYY}.ZIP` quanto o TXT descompactado `COTAHIST_A{YYYY}.TXT`.
Quando ambos existem para o mesmo ano, o ZIP tem precedência determinística.
`output_filename` deve ser um basename sem separadores de caminho; o sufixo
`.parquet` é opcional e é acrescentado apenas quando ausente.

`EmptyDirectoryError` ocorre somente quando o diretório de entrada está
fisicamente vazio. Se o diretório não está vazio, mas não contém COTAHIST
correspondente ao ano solicitado, a API retorna um resultado vazio com
`success=True`, `total_files=0`, `total_records=0`, `output_file=""` e
`errors={}`. Inspecione `total_files` e `total_records` quando a presença de
dados for obrigatória.

Um arquivo válido cujos registros sejam todos filtrados pelo TPMERC solicitado
também retorna sucesso e publica um Parquet vazio com o schema B3. Em contraste,
qualquer registro selecionado inválido falha com contexto de fonte, membro,
linha e campo; o parser não substitui dados inválidos por zero ou nulo.

**`extract_async()`**

```python
async def extract_async(
    self,
    path_of_docs: str,
    assets_list: list[str],
    initial_year: int | None = None,
    last_year: int | None = None,
    destination_path: str | None = None,
    output_filename: str = "cotahist_extracted",
    processing_mode: str = "fast",
    verbose: bool = True,
) -> ExtractionResultB3:
    ...
```

Variante assíncrona do método `extract()`. Utilize ao chamar dentro de um event loop assíncrono em execução.

**`get_available_assets()`**

```python
def get_available_assets(self) -> list[str]:
    ...
```

Retorna a lista de todas as classes de ativos suportadas para extração:

- `'ações'`: Mercado à vista e fracionário
- `'etf'`: Exchange Traded Funds
- `'opções'`: Opções de compra e venda
- `'termo'`: Mercado a termo
- `'exercicio_opcoes'`: Exercício de opções
- `'forward'`: Contratos forward (TPMERC 050 e 060)
- `'leilao'`: Mercado de leilão

As strings em português acima são valores canônicos de `assets_list` e devem
ser passadas exatamente como mostradas. BDRs e Futures são **Planned** e não
são aceitos pelo contrato atual do runtime.

**`get_available_years()`**

```python
def get_available_years(self) -> dict[str, int]:
    ...
```

Retorna um dicionário com o intervalo de anos suportados pela B3:

- `'minimal_year'`: Ano mínimo disponível (`1986`)
- `'current_year'`: Ano corrente do sistema

______________________________________________________________________

## Veja Também

- [API CVM](../reference/cvm-api.md) - Detalhes técnicos e use cases da CVM
- [API B3](../reference/b3-api.md) - Detalhes técnicos e use cases da B3
- [Hierarquia de Exceções](../reference/exceptions.md) - Catálogo de exceções do projeto
