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
- ✅ Progress tracking detalhado

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

> `ações` e `etf` são aliases de seleção que compartilham os códigos de mercado à vista (010) e fracionário (020).

BDRs e Futures são **Planned** e não são aceitos pelo contrato atual de
`HistoricalQuotesB3`. As strings em português da tabela são valores canônicos
da API e devem ser passadas exatamente como mostradas.

!!! info "Dados Históricos"
    Cotações históricas da B3 estão disponíveis desde **1986** até o ano atual.

______________________________________________________________________

## Uso Básico

Antes de chamar `extract()`, coloque arquivos oficiais `COTAHIST_A{YYYY}.ZIP` ou
`COTAHIST_A{YYYY}.TXT` no diretório existente de `path_of_docs`; a biblioteca não baixa nem preenche esse diretório. Obtenha-os na [página oficial de Cotações Históricas da B3](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/); o ZIP prevalece quando ambos existem.
Um arquivo selecionado precisa conter ao menos um registro `01`; arquivo vazio ou somente com header/trailer não é uma extração válida.

### Exemplo de Início Rápido

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()

# Extrair cotações de ações de um ano histórico fechado
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=2023,
)

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

#### Parâmetros

| Parâmetro          | Tipo          | Obrigatório | Descrição                                             |
| ------------------ | ------------- | ----------- | ----------------------------------------------------- |
| `path_of_docs`     | `str`         | ✅ Sim      | Diretório contendo arquivos COTAHIST ZIP ou TXT       |
| `assets_list`      | `list[str]`   | ✅ Sim      | Lista de classes de ativos a extrair                  |
| `initial_year`     | `int \| None` | ❌ Não      | Ano inicial (padrão: 1986)                            |
| `last_year`        | `int \| None` | ❌ Não      | Ano final (padrão: ano atual)                         |
| `destination_path` | `str \| None` | ❌ Não      | Diretório de saída (padrão: mesmo que `path_of_docs`) |
| `output_filename`  | `str`         | ❌ Não      | Basename obrigatório; `.parquet` opcional e acrescentado apenas quando ausente |
| `processing_mode`  | `str`         | ❌ Não      | Modo de processamento: `"fast"` ou `"slow"`           |
| `verbose`          | `bool`        | ❌ Não      | Se `True` (padrão), imprime resumo no console         |

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

Para um arquivo COTAHIST selecionado, `success=True` exige um Parquet gerado,
inclusive quando todas as linhas `01` forem filtradas pelas classes solicitadas.
Nesse caso válido, o Parquet tem o schema B3 explícito e zero linhas. Um arquivo
sem registro `01` continua inválido; registros `01` selecionados com tamanho,
data, texto, inteiro ou decimal inválidos falham com `ExtractionError`
contextual, sem converter valores ausentes em zero ou nulo.

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

if result['success']:
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
# ['ações', 'etf', 'opções', 'termo', 'exercicio_opcoes', 'forward', 'leilao']
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

- **Performance**: Alto desempenho
- **CPU**: Uso intensivo (multi-core)
- **RAM**: Maior consumo de memória
- **Recomendado para**: Máquinas com bons recursos, processamento de grandes volumes

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

- **Performance**: Moderada
- **CPU**: Uso reduzido (single-core ou poucos cores)
- **RAM**: Menor consumo de memória
- **Recomendado para**: Máquinas com recursos limitados, processamento em background

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

*Medição de benchmark em dataset completo (picos gerais variam de ~2 GB a 4.2 GB no modo `fast` e ~500 MB a 1.5 GB no modo `slow` conforme hardware e volume).*

| Modo     | Throughput medido | CPU   | Pico de RAM (Benchmark) | Cenário Indicado   |
| -------- | ----------------- | ----- | ----------------------- | ------------------ |
| **fast** | ~12.317 reg/s     | Alto  | ~4.260 MB               | ✅ Padrão (rápido) |
| **slow** | ~8.557 reg/s      | Baixo | ~1.571 MB               | Recursos limitados |

______________________________________________________________________

## Exemplos Avançados

### Todas as Classes Atualmente Suportadas

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()

# Obter todas as classes de ativos atualmente suportadas
all_assets = b3.get_available_assets()

# Extrair todas as classes atualmente suportadas
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=all_assets,  # Todas as classes suportadas
    initial_year=2023,
    output_filename="todos_ativos_2023"
)

print(f"✓ Extraídos {result['total_records']:,} registros de {len(all_assets)} classes suportadas")
```

### Extração Incremental por Ano

```python
from globaldatafinance import HistoricalQuotesB3
import os

b3 = HistoricalQuotesB3()
base_path = "/data/cotahist"
output_path = "/data/cotacoes_extraidas"

# Extrair cada ano separadamente
for year in range(2020, 2024):
    output_file = f"acoes_{year}"

    result = b3.extract(
        path_of_docs=base_path,
        destination_path=output_path,
        assets_list=["ações"],
        initial_year=year,
        last_year=year,
        output_filename=output_file
    )

    if result['success']:
        print(f"✓ {year}: {result['total_records']:,} registros")
    else:
        print(f"✗ {year}: Erro na extração")
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
| `EmptyDirectoryError` | Ocorre somente se o diretório estiver fisicamente vazio; diretório que não está vazio sem COTAHIST correspondente retorna resultado vazio (`success=True`, contadores 0, `output_file=""`, `errors={}`) | Inspecionar `total_files` e `total_records` |
| `ExtractionError`     | Erro ao processar arquivo COTAHIST | Verificar integridade dos arquivos     |

______________________________________________________________________

## Formato dos Arquivos COTAHIST

### Nomenclatura

Os arquivos oficiais da B3 seguem o padrão `COTAHIST_A{YYYY}.ZIP` (ex: `COTAHIST_A2023.ZIP`), onde `{YYYY}` é o ano com 4 dígitos. O extrator também aceita arquivos de texto descompactados no formato `COTAHIST_A{YYYY}.TXT`. Se ZIP e TXT do mesmo ano coexistirem, somente o ZIP será selecionado, de forma determinística.

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
O filtro TPMERC é aplicado antes da conversão dos demais campos. Portanto,
registros fora do filtro são contabilizados como filtrados, enquanto um registro
selecionado inválido nunca produz um valor financeiro padrão.

O texto literal `__GLOBALDATAFINANCE_NULL__` é reservado pelo writer interno e é
rejeitado como dado de entrada em registros e linhas canônicas. Use `None` para
valor nulo. A session interna tem estados `NEW`, `OPEN` e `CLOSED`; após fechar,
inclusive depois de falha de validação, ela não pode ser reaberta.

______________________________________________________________________

## Estrutura do Arquivo Parquet Gerado

### Colunas

O arquivo Parquet gerado contém as seguintes colunas:

| Coluna                 | Tipo      | Descrição                              |
| ---------------------- | --------- | -------------------------------------- |
| `data_pregao`          | `date`    | Data do pregão                         |
| `codigo_bdi`           | `string`  | Código BDI                             |
| `ticker`               | `string`  | Código de negociação (ex: PETR4)       |
| `tipo_mercado`         | `string`  | Tipo de mercado                        |
| `nome_resumido`        | `string`  | Nome resumido da empresa               |
| `especificacao_papel`  | `string`  | Especificação do papel (ex: ON, PN)    |
| `preco_abertura`       | `decimal` | Preço de abertura                      |
| `preco_maximo`         | `decimal` | Preço máximo do dia                    |
| `preco_minimo`         | `decimal` | Preço mínimo do dia                    |
| `preco_medio`          | `decimal` | Preço médio do dia                     |
| `preco_fechamento`     | `decimal` | Preço de fechamento                    |
| `melhor_oferta_compra` | `decimal` | Melhor oferta de compra                |
| `melhor_oferta_venda`  | `decimal` | Melhor oferta de venda                 |
| `numero_negocios`      | `int`     | Número de negócios efetuados           |
| `quantidade_total`     | `int`     | Quantidade total de títulos negociados |
| `volume_total`         | `decimal` | Volume total financeiro                |
| `data_vencimento`      | `date`    | Data de vencimento (opções/termo)      |
| `fator_cotacao`        | `int`     | Fator de cotação                       |
| `codigo_isin`          | `string`  | Código ISIN                            |
| `numero_distribuicao`  | `int`     | Número de distribuição                 |

### Leitura

Use `pandas.read_parquet()` para carregar uma tabela inteira. Para processamento
limitado por memória, use `pyarrow.parquet.ParquetFile(...).iter_batches()`
com `batch_size=200_000`; PyArrow é o engine produtivo e Pandas permanece pelo
contrato legado do adaptador CSV.

______________________________________________________________________

## Boas Práticas

### 1. Use Modo Fast para Grandes Volumes

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
# ✅ Recomendado para grandes volumes
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=1986,  # 23+ anos
    processing_mode="fast",
)
```

### 2. Separe Extrações por Classe de Ativo

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
# ✅ Recomendado: arquivos separados por classe
for asset in ["ações", "etf", "opções"]:
    result = b3.extract(
        path_of_docs="/data/cotahist",
        assets_list=[asset],
        initial_year=2023,
        output_filename=f"{asset}_2023",
    )
```

### 3. Verifique Espaço em Disco

```python
import shutil

stats = shutil.disk_usage("/data")
free_gb = stats.free / (1024**3)

if free_gb < 5:
    print(f"⚠️  Pouco espaço: {free_gb:.2f} GB")
    # Use modo slow ou processe menos anos
else:
    # Prosseguir normalmente
    pass
```

______________________________________________________________________

## Próximos Passos

- 📄 **[Documentos CVM](cvm-docs.md)** - Aprenda a baixar documentos CVM
- 💻 **[Exemplos Práticos](examples.md)** - Veja casos de uso completos
- 🔧 **[API Reference](../reference/b3-api.md)** - Documentação técnica detalhada
- ❓ **[FAQ](faq.md)** - Perguntas frequentes

______________________________________________________________________

!!! tip "Dica de Análise"
    Após extrair para Parquet, use leitura em batches com PyArrow para limitar a
    memória de análises grandes. Polars pode ser instalado separadamente por
    consumidores que o prefiram como leitor downstream.
