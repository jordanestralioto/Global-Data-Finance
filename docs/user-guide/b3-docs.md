# Cotações Históricas B3

Guia completo para usar a API `HistoricalQuotesB3` e extrair cotações históricas da B3 (Brasil, Bolsa, Balcão) a partir de arquivos COTAHIST.

______________________________________________________________________

## Visão Geral

A classe `HistoricalQuotesB3` fornece uma interface poderosa para processar arquivos COTAHIST da B3, extraindo cotações históricas de diferentes classes de ativos e convertendo-as para o formato Parquet otimizado para análise.

### Características

- ✅ Extração de múltiplas classes de ativos
- ✅ Processamento de alto desempenho (modo fast/slow)
- ✅ Conversão automática para formato Parquet
- ✅ Suporte a dados desde 1986
- ✅ Filtragem inteligente por tipo de ativo
- ✅ Barras de progresso por arquivo na validação e no processamento

______________________________________________________________________

## Classes de Ativos Disponíveis

A B3 disponibiliza cotações históricas para as seguintes classes de ativos:

| Código               | Descrição           | Códigos TPMERC B3 Incluídos               |
| -------------------- | ------------------- | ----------------------------------------- |
| **ações**            | Ações               | Mercado à vista (010) e fracionário (020) |
| **etf**              | ETFs                | Mercado à vista (010) e fracionário (020) |
| **opções**           | Opções              | Calls (070) e Puts (080)                  |
| **termo**            | Mercado a Termo     | Contratos a termo (030)                   |
| **exercicio_opcoes** | Exercício de Opções | Exercício Compra (012) e Venda (013)      |
| **forward**          | Contratos forward   | Forward c/ Ganho (050) e Mov. (060)       |
| **leilao**           | Leilão              | Mercado de leilão (017)                   |
| **lote_bloco**       | Lote em bloco       | [BBT](https://www.b3.com.br/pt_br/solucoes/negociacao-de-grandes-lotes/book-of-block-trade-bbt/) e [Midpoint](https://www.b3.com.br/pt_br/solucoes/negociacao-de-grandes-lotes/midpoint-order-book/) (021) |
| **todos**            | Seleção completa    | Todo código TPMERC numérico de 3 dígitos  |

> `ações` e `etf` são aliases de seleção que compartilham os códigos de mercado à vista (010) e fracionário (020).

BDRs e Futures são **Planned** e não são aceitos pelo contrato atual de
`HistoricalQuotesB3`. A seleção `todos` também preserva TPMERCs numéricos ainda
desconhecidos e os relata como tal. As strings em português da tabela são
valores canônicos da API e devem ser passadas exatamente como mostradas.

!!! info "Dados Históricos"
    Cotações históricas da B3 estão disponíveis desde **1986** até o ano atual.

______________________________________________________________________

## Uso Básico

Antes de chamar `extract()`, coloque arquivos oficiais `COTAHIST_A{YYYY}.ZIP` ou
`COTAHIST_A{YYYY}.TXT` no diretório existente de `path_of_docs`; a biblioteca não baixa nem preenche esse diretório. Obtenha-os na [página oficial de Cotações Históricas da B3](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/); o ZIP prevalece quando ambos existem.
Um arquivo selecionado precisa conter ao menos um registro `01`; arquivo vazio ou somente com header/trailer não é uma extração válida.

### Exemplo de Início Rápido

```python
from pathlib import Path
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()

# Extrair cotações de ações de um ano histórico fechado
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=2023,
    last_year=2023,
)

if not result['success']:
    raise SystemExit(result['errors'])
print(f"✓ Extraídos {result['total_records']:,} registros")
```

______________________________________________________________________

## Métodos Principais

### `extract()`

Extrai cotações históricas de arquivos COTAHIST (arquivos ZIP ou TXT descompactados) e consolida os dados filtrados em formato Parquet.

#### Assinatura

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

#### Parâmetros

| Parâmetro          | Tipo          | Obrigatório | Descrição                                             |
| ------------------ | ------------- | ----------- | ----------------------------------------------------- |
| `path_of_docs`     | `str`         | ✅ Sim      | Diretório contendo arquivos COTAHIST ZIP ou TXT       |
| `assets_list`      | `list[str] \| None` | ❌ Não | `None` (`["todos"]`) | Classes a extrair; `"todos"` seleciona cada TPMERC numérico válido |
| `initial_year`     | `int \| None` | ❌ Não      | Ano inicial (padrão: 1986)                            |
| `last_year`        | `int \| None` | ❌ Não      | Ano final (padrão: ano atual)                         |
| `destination_path` | `str \| None` | ❌ Não      | Diretório de saída (padrão: mesmo que `path_of_docs`) |
| `output_filename`  | `str`         | ❌ Não      | Basename obrigatório; `.parquet` opcional e acrescentado apenas quando ausente |
| `processing_mode`  | `str`         | ❌ Não      | Modo de processamento: `"fast"` ou `"slow"`           |
| `verbose`          | `bool`        | ❌ Não      | Se `True` (padrão), imprime o resumo final; as barras de progresso aparecem também com `False` |

Consulte os detalhes de [progresso e resumo final](../reference/b3-api.md#extract).

#### Retorno (`ExtractionResultB3`)

| Chave             | Tipo             | Descrição                                             |
| ----------------- | ---------------- | ----------------------------------------------------- |
| `success`         | `bool`           | `True` se a extração foi concluída com sucesso        |
| `message`         | `str`            | Mensagem resumida do resultado                        |
| `total_files`     | `int`            | Total de arquivos de entrada processados (ZIP ou TXT) |
| `success_count`   | `int`            | Arquivos processados com sucesso                      |
| `error_count`     | `int`            | Arquivos com erro                                     |
| `total_records`   | `int`            | Total de registros extraídos                          |
| `output_file`     | `str`            | Caminho completo do arquivo Parquet gerado            |
| `errors`          | `dict[str, str]` | Dicionário mapeando arquivos com erro à mensagem      |
| `assets`          | `list[str]`      | Lista de classes de ativos extraídas                  |
| `processing_mode` | `str`            | Modo de processamento utilizado                       |
| `elapsed_time`    | `float`          | Tempo total de execução em segundos                   |
| `schema_version`  | `int`            | Versão do schema Parquet (`2`)                         |
| `integrity`       | `B3IntegrityReport` | Cobertura, seleção, fontes, verificações, avisos e hash do resultado |

`assets_list=None` equivale a `["todos"]`. Esse seletor inclui qualquer TPMERC
de três dígitos ASCII, inclusive códigos numéricos desconhecidos, que também
aparecem em `integrity.unknown_market_counts`. `lote_bloco` seleciona `021`;
`ações` e `etf` continuam aliases de seleção para `010` e `020` e não
classificam independentemente a categoria financeira do ativo. Repetir aliases
que se sobrepõem não duplica ocorrências.

Cada cotação `01` é validada em todos os campos antes de aplicar um filtro de
classe. TPMERC inválido e campos malformados falham mesmo quando a cotação seria
excluída pelo filtro. Linhas vazias e controles `00`/`99` são contados, não
persistidos. O validador aceita apenas os totais de trailer observados:
cotações mais os dois controles ou apenas cotações; o segundo caso produz um
aviso estruturado.

`success=True` exige todos os anos solicitados, fontes validadas, todas as
linhas selecionadas escritas e verificadas por leitura completa do Parquet e
publicação concluída. Um ano ausente ou uma verificação incompleta falha sem
publicar uma nova saída. A saída filtrada válida pode ter zero linhas; o
relatório distingue `selection_complete` de `source_complete` e registra as
exclusões intencionais. O resultado informa hashes do ZIP/TXT, do conteúdo
descompactado e do Parquet publicado.

Consulte [avisos de limpeza e cancelamento](../reference/b3-api.md).

Como os anos padrão continuam sendo 1986 até o ano atual, uma pasta com um
recorte local deve passar os limites disponíveis explicitamente. A cobertura
real é a dos arquivos fornecidos e não confirma datas fora deles.

#### Exemplos

**Exemplo 1: Extração básica de ações**

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=2022,
    last_year=2023,
)

if not result['success']:
    raise SystemExit(result['errors'])
print(f"✓ Arquivo gerado: {result['output_file']}")
print(f"✓ Total de registros: {result['total_records']:,}")
```

**Exemplo 2: Múltiplas classes de ativos**

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações", "etf", "opções"],
    initial_year=2020,
    last_year=2023,
    output_filename="multi_ativos_2020_2023",
)
```

**Exemplo 3: Modo de baixa performance (economia de recursos)**

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=2023,
    processing_mode="slow",  # Usa menos CPU/RAM
)
```

**Exemplo 4: Destino personalizado**

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist_zips",
    destination_path="/data/cotacoes_extraidas",
    assets_list=["ações", "etf"],
    initial_year=2023,
    output_filename="acoes_etf_2023",
)
# Arquivo salvo em: /data/cotacoes_extraidas/acoes_etf_2023.parquet
```

______________________________________________________________________

### `get_available_assets()`

Retorna lista de todas as classes de ativos disponíveis.

#### Assinatura

```python
def get_available_assets(self) -> list[str]:
    ...
```

#### Retorno

Lista de strings com códigos das classes de ativos.

#### Exemplo

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
assets = b3.get_available_assets()
# ['ações', 'etf', 'opções', 'termo', 'exercicio_opcoes', 'forward', 'leilao', 'lote_bloco', 'todos']
print(f"Disponíveis {len(assets)} classes de ativos")
```

______________________________________________________________________

### `get_available_years()`

Retorna informações sobre o intervalo de anos disponível.

#### Assinatura

```python
def get_available_years(self) -> dict[str, int]:
    ...
```

#### Retorno

Dicionário com `minimal_year` (1986) e `current_year`.

#### Exemplo

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
years = b3.get_available_years()
# `current_year` corresponde ao ano corrente de execução.
print(f"Dados de {years['minimal_year']} até {years['current_year']}")
```

______________________________________________________________________

## Modos de Processamento

A extração suporta dois modos de processamento:

### Modo Fast (Padrão) ⚡

Usa o parser canônico e escrita Arrow em lotes de até 25.000 registros. Pode
processar várias fontes em paralelo, conforme CPUs, memória disponível e
quantidade de arquivos; o limite padrão é de quatro workers.

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    processing_mode="fast",  # Padrão
)
```

### Modo Slow 🐢

Usa o mesmo parser canônico e schema, com lotes de até 10.000 registros e um
worker de extração. Ambos os modos leem a fonte de forma limitada e conferem
integralmente os dados antes de publicar.

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    processing_mode="slow",
)
```

### Comparação de Performance

*Referência histórica da implementação v3: 27 arquivos (2000–2026) e 22.303.577 registros, sem 2.283 cotações TPMERC `021`. Essa medição não representa o schema v2 e não é diretamente comparável. Veja os [detalhes do benchmark](../dev-guide/benchmarks.md).*

| Modo     | Throughput medido | Pico RSS medido | Paralelismo padrão                                  | Cenário Indicado        |
| -------- | ----------------- | --------------- | --------------------------------------------------- | ----------------------- |
| **fast** | 34.313,8 reg/s    | 429,88 MiB      | Até 4 workers, limitado por CPUs, memória e arquivos-fonte | ✅ Priorizar velocidade |
| **slow** | 29.759,9 reg/s    | 331,11 MiB      | 1 worker                                            | Reduzir uso de memória  |

RSS e tempo dependem da carga; `fast` não garante menor tempo que `slow`.
Veja as [medições atuais e condições de uso](../dev-guide/cotahist-performance.md).

______________________________________________________________________

## Exemplos Avançados

### Seleção Completa de Mercados

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()

# `todos` inclui TPMERCs numéricos desconhecidos, além das classes conhecidas
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["todos"],
    initial_year=2023,
    last_year=2023,
    output_filename="todos_ativos_2023"
)

if not result['success']:
    raise SystemExit(result['errors'])
print(f"✓ Extraídos {result['total_records']:,} registros; mercados desconhecidos: {result['integrity']['unknown_market_counts']}")
```

### Extração Incremental por Ano

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
base_path = "/data/cotahist"
output_dir = "/data/cotacoes_extraidas"

# Extrair cada ano separadamente
for year in range(2020, 2024):
    output_file = f"acoes_{year}"

    result = b3.extract(
        path_of_docs=base_path,
        destination_path=output_dir,
        assets_list=["ações"],
        initial_year=year,
        last_year=year,
        output_filename=output_file
    )

    if not result['success']:
        raise SystemExit(result['errors'])
    print(f"✓ {year}: {result['total_records']:,} registros")
```

### Validação Antes da Extração

```python
import os
import re
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
path_docs = "/data/cotahist"

# 1. Verificar se diretório existe
if not os.path.exists(path_docs):
    print(f"✗ Diretório não encontrado: {path_docs}")
    exit(1)

# 2. Verificar se há arquivos COTAHIST válidos (ZIP ou TXT com 4 dígitos de ano)
pattern = re.compile(r"^COTAHIST_A\d{4}\.(?:ZIP|TXT)$", re.IGNORECASE)
files = [f for f in os.listdir(path_docs) if pattern.match(f)]
if not files:
    print(f"✗ Nenhum arquivo COTAHIST encontrado em {path_docs}")
    exit(1)

print(f"✓ Encontrados {len(files)} arquivos COTAHIST")

# 3. Validar classes de ativos
requested_assets = ["ações", "etf"]
available_assets = b3.get_available_assets()
invalid_assets = [a for a in requested_assets if a not in available_assets]
if invalid_assets:
    print(f"✗ Ativos inválidos: {invalid_assets} (disponíveis: {available_assets})")
    exit(1)

# 4. Prosseguir com extração
result = b3.extract(
    path_of_docs=path_docs,
    assets_list=requested_assets,
    initial_year=2023
)
```

______________________________________________________________________

## Tratamento de Erros

### Exceções Comuns

| Exceção               | Quando ocorre                      | Como tratar                            |
| --------------------- | ---------------------------------- | -------------------------------------- |
| `EmptyAssetListError` | `assets_list` está vazio           | Fornecer pelo menos um ativo           |
| `InvalidAssetsName`   | Ativo inválido em `assets_list`    | Verificar com `get_available_assets()` |
| `InvalidFirstYear`    | `initial_year` fora do intervalo   | Usar 1986 ≤ ano ≤ ano atual            |
| `InvalidLastYear`     | `last_year` inválido               | Usar `initial_year` ≤ ano ≤ ano atual  |
| `EmptyDirectoryError` | Diretório de entrada fisicamente vazio | Fornecer um diretório existente com COTAHIST |
| `ExtractionError`     | Erro ao processar arquivo COTAHIST | Verificar integridade dos arquivos     |

Se faltar um arquivo de qualquer ano solicitado, a API retorna `success=False`,
lista a lacuna em `integrity.missing_years` e não publica uma nova saída.

______________________________________________________________________

## Formato dos Arquivos COTAHIST

### Nomenclatura

Os arquivos oficiais da B3 seguem o padrão `COTAHIST_A{YYYY}.ZIP` (ex: `COTAHIST_A2023.ZIP`), onde `{YYYY}` é o ano com 4 dígitos. O extrator também aceita arquivos de texto descompactados no formato `COTAHIST_A{YYYY}.TXT`. Se ZIP e TXT do mesmo ano coexistirem, ambos são validados. O ZIP tem precedência somente quando os conteúdos descompactados são idênticos; conteúdos divergentes fazem a extração retornar `success=False`, sem publicar saída.

### Estrutura Interna

Cada arquivo ZIP contém um arquivo TXT com layout de largura fixa:

```
COTAHIST_A2023.ZIP
└── COTAHIST_A2023.TXT  (arquivo de texto com largura fixa)
```

Arquivos históricos também podem conter `COTAHIST.A{YYYY}` (`COTAHIST.A2000`) ou
`COTAHIST_A{YYYY}` sem extensão (`COTAHIST_A2001`). O leitor exige exatamente um
membro candidato não aninhado, com ano interno igual ao nome externo; membro ausente,
ambíguo ou divergente é rejeitado. Registros `01` precisam ter 245 caracteres,
com espaços finais preservados; TXT e o membro selecionado precisam ter ao menos
um registro `01`, pois header/trailer isolado falha antes do parser. Antes de
consumir um ZIP, a biblioteca valida metadados e limites de tamanho, membros,
expansão e compressão; formato inseguro ou corrompido falha com
`ExtractionError`/`CorruptedZipError`, sem produzir resultado de sucesso.

O parser é estrito: linhas vazias e controles `00`/`99` são apenas contadas;
um identificador não vazio diferente de `01`, `00` ou `99` aborta a extração.
Todos os campos de cada registro `01` são validados antes do filtro TPMERC,
inclusive em cotações que serão excluídas. Um campo inválido nunca produz um
valor financeiro padrão.

O texto literal `__GLOBALDATAFINANCE_NULL__` é reservado pelo writer interno e é
rejeitado como dado de entrada em registros e linhas canônicas. Use `None` para
valor nulo. A session interna tem estados `NEW`, `OPEN` e `CLOSED`; após fechar,
inclusive depois de falha de validação, ela não pode ser reaberta.

______________________________________________________________________

## Estrutura do Arquivo Parquet Gerado

O schema padrão é a versão `2`. Os 20 campos históricos mantêm a mesma ordem;
a versão acrescenta campos oficiais, tipo de registro, proveniência e os bytes
originais. Todos são obrigatórios, exceto `data_vencimento`. O footer inclui o
manifesto de integridade e a impressão digital lógica do schema.

Consulte a [referência técnica do schema v2](../reference/b3-schema-v2.md) para
a lista completa de campos, tipos, leitura e proveniência. Arquivos de schema
v1 precisam ser regenerados a partir dos COTAHIST originais conforme o
[guia de migração da versão 2](migration-pyarrow-integrity.md#b3-schema-v2-e-regeneracao).

Para recomendações de operação, particionamento e consumo dos artefatos, veja
[Boas práticas B3](b3-operations.md).
