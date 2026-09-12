# API B3 - Referência Técnica

Documentação técnica detalhada da API B3.

______________________________________________________________________

## HistoricalQuotesB3

### Classe Principal

```python
class HistoricalQuotesB3:
    """Interface de alto nível para cotações B3."""
```

### Métodos

#### `extract()`

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

**Descrição**: Extrai cotações históricas de arquivos COTAHIST (`COTAHIST_A{YYYY}.ZIP` ou `.TXT`), filtra os ativos e consolida o resultado em formato Parquet. A API aceita os dois formatos locais; o download oficial da B3 continua sendo distribuído em ZIP.

O parser é estrito: controles `00`/`99` e linhas vazias não são persistidos,
TPMERC fora do filtro é contabilizado como filtrado, e um registro `01`
selecionado inválido levanta `ExtractionError` contextual. Valores financeiros
inválidos não recebem fallback para zero ou nulo.

**Parâmetros**:

| Nome               | Tipo                | Obrigatório | Padrão                 | Descrição                                                                      |
| ------------------ | ------------------- | ----------- | ---------------------- | ------------------------------------------------------------------------------ |
| `path_of_docs`     | `str`               | Sim         | -                      | Diretório contendo arquivos COTAHIST ZIP ou TXT                                 |
| `assets_list`      | `list[str]`         | Sim         | -                      | Classes de ativos a extrair (ex.: `["ações", "etf"]`)                          |
| `initial_year`     | `int \| None`       | Não         | `None` (1986)          | Ano inicial da extração (inclusivo, >= 1986)                                   |
| `last_year`        | `int \| None`       | Não         | `None` (ano atual)     | Ano final da extração (inclusivo)                                              |
| `destination_path` | `str \| None`       | Não         | `None` (`path_of_docs`)| Diretório de destino do Parquet gerado                                         |
| `output_filename`  | `str`               | Não         | `"cotahist_extracted"` | Nome base obrigatório (basename); `.parquet` é opcional e acrescentado apenas quando ausente |
| `processing_mode`  | `str`               | Não         | `"fast"`               | Modo de processamento: `"fast"` (paralelo) ou `"slow"` (baixo consumo de RAM) |
| `verbose`          | `bool`              | Não         | `True`                 | Se `True`, imprime o resumo formatado no console                               |

**Retorno (`ExtractionResultB3`)**:

Objeto `TypedDict` contendo o resultado da extração:

- `success: bool` — Indica se a extração foi concluída com sucesso.
- `message: str` — Mensagem descritiva com o resumo da execução.
- `total_files: int` — Quantidade total de arquivos de entrada processados (ZIP ou TXT).
- `success_count: int` — Quantidade de arquivos processados com sucesso.
- `error_count: int` — Quantidade de arquivos que falharam no processamento.
- `total_records: int` — Quantidade total de registros extraídos.
- `output_file: str` — Caminho completo para o arquivo Parquet gerado.
- `errors: dict[str, str]` — Dicionário mapeando arquivos com falha para a mensagem de erro (se houver).
- `assets: list[str]` — Lista de classes de ativos filtradas.
- `processing_mode: str` — Modo de processamento utilizado (`"fast"` ou `"slow"`).
- `elapsed_time: float` — Tempo total de execução em segundos.

**Semântica de entrada e resultado vazio**:

- A API aceita `COTAHIST_A{YYYY}.ZIP` e `COTAHIST_A{YYYY}.TXT`; quando os dois
  formatos existem para o mesmo ano, o ZIP tem precedência determinística.
- `output_filename` deve ser um basename, sem separadores de caminho. O sufixo
  `.parquet` é aceito; quando omitido, é acrescentado automaticamente uma única
  vez.
- `EmptyDirectoryError` ocorre somente quando o diretório de entrada está
  fisicamente vazio. Se o diretório não está vazio, mas não contém um COTAHIST
  correspondente aos anos solicitados, a API retorna um resultado vazio com
  `success=True`, `total_files=0`, `total_records=0`, `output_file=""` e
`errors={}`. Inspecione esses contadores quando a presença de dados for
obrigatória.

Se arquivos válidos não tiverem registros após o filtro de ativos, a extração
continua bem-sucedida e publica Parquet B3 vazio com schema explícito.

**Exceções**:

- `EmptyAssetListError`: Lista de ativos vazia ou não fornecida.
- `InvalidAssetsName`: Classe de ativo não suportada.
- `InvalidFirstYear`: Ano inicial fora da faixa válida (1986 até o ano atual).
- `InvalidLastYear`: Ano final fora da faixa válida ou menor que o ano inicial.
- `EmptyDirectoryError`: Diretório de entrada fisicamente vazio.
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
# ['ações', 'etf', 'opções', 'termo', 'exercicio_opcoes', 'forward', 'leilao']
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

As strings em português desta tabela são valores canônicos de `assets_list` e
devem ser passadas exatamente como mostradas. BDRs e Futures são **Planned** e
não são aceitos pelo contrato atual do runtime.

______________________________________________________________________

## Modos de Processamento

| Modo     | Throughput medido | Uso de CPU | Faixa de RAM           | Cenário Indicado                     |
| -------- | ----------------- | ---------- | ---------------------- | ------------------------------------ |
| **fast** | ~12.300 reg/s     | Alto       | ~2 GB – 4.2 GB (pico)  | Padrão, máquinas com múltiplos núcleos |
| **slow** | ~8.500 reg/s      | Baixo      | ~500 MB – 1.5 GB (pico)| Ambientes com restrição de memória   |

______________________________________________________________________

## Documentação Relacionada

- [Guia de Uso B3](../user-guide/b3-docs.md)
- [Exceções](exceptions.md)
