# Início Rápido

Bem-vindo ao **Global-Data-Finance**! Este guia irá ajudá-lo a dar os primeiros passos com a biblioteca através de exemplos práticos e simples.

______________________________________________________________________

## Pré-requisitos

Antes de começar, certifique-se de que você:

- ✅ Instalou o Global-Data-Finance ([ver guia de instalação](installation.md))
- ✅ Possui Python >=3.12,<4.0
- ✅ Tem acesso à internet para downloads

______________________________________________________________________

## Primeiro Exemplo: Documentos CVM

Vamos começar baixando documentos fundamentalistas da CVM (Comissão de Valores Mobiliários).

### Código Básico

```python
from globaldatafinance import FundamentalStocksDataCVM

# 1. Criar instância do cliente CVM
cvm = FundamentalStocksDataCVM()

# 2. Baixar documentos DFP (Demonstrações Financeiras Padronizadas)
cvm.download(
    destination_path="/home/usuario/dados_cvm",
    list_docs=["DFP"],
    initial_year=2022,
    last_year=2023
)
```

### O que acontece?

1. **Criação do cliente**: Inicializa o cliente CVM com configurações padrão
2. **Download**: Baixa todos os arquivos DFP dos anos 2022 e 2023
3. **Resultado**: Arquivos ZIP são salvos em `/home/usuario/dados_cvm`

### Saída Esperada

```text
📥 CVM Documents Download
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Documents downloaded successfully!

📊 Summary:
  • Total files: 2
  • Success: 2
  • Errors: 0
  • Elapsed time: 45.3s

📁 Downloaded files:
  ✓ DFP - 2022
  ✓ DFP - 2023
```

______________________________________________________________________

## Segundo Exemplo: Cotações Históricas B3

Agora vamos extrair cotações históricas da B3 (Bolsa de Valores do Brasil).

!!! note "Obtenção dos Arquivos COTAHIST da B3"

    Diferente dos dados CVM que são baixados via HTTP pela biblioteca, as cotações históricas da B3 são fornecidas em arquivos anuais no portal oficial da B3 ([Cotações Históricas B3](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/)).
    Baixe os arquivos anuais no formato oficial `COTAHIST_A{YYYY}.ZIP` (por exemplo, `COTAHIST_A2023.ZIP` e `COTAHIST_A2024.ZIP`) e coloque-os no diretório de entrada desejado (ex: `/home/usuario/cotahist_zips`). `path_of_docs` é esse diretório de entrada existente; a biblioteca não baixa nem o preenche automaticamente. O extrator também aceita o TXT descompactado `COTAHIST_A{YYYY}.TXT`; quando ZIP e TXT do mesmo ano coexistem, o ZIP é escolhido.

### Código Básico

```python
from globaldatafinance import HistoricalQuotesB3

# 1. Criar instância do cliente B3
b3 = HistoricalQuotesB3()

# 2. Extrair cotações de ações
result = b3.extract(
    path_of_docs="/home/usuario/cotahist_zips",
    assets_list=["ações"],
    initial_year=2023,
    destination_path="/home/usuario/cotacoes_extraidas"
)

```

### O que acontece?

1. **Criação do cliente**: Inicializa o cliente B3
1. **Extração**: Processa arquivos COTAHIST (ZIP ou TXT) e extrai dados da classe de ações nos mercados à vista (010) e fracionário (020)
2. **Conversão**: Converte para formato Parquet otimizado
3. **Resultado**: Arquivo `.parquet` com todas as cotações

### Saída Esperada

```text
📊 B3 Historical Quotes Extraction
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✓ Extraction completed successfully!

📈 Summary:
  • Processed files: 2
  • Total records: 836,978
  • Asset classes: ações
  • Processing mode: fast
  • Elapsed time: 77.9s

💾 Generated file:
  /home/usuario/cotacoes_extraidas/cotahist_extracted.parquet
```

______________________________________________________________________

## Explorando Dados Disponíveis

Antes de baixar ou extrair dados, você pode descobrir o que está disponível.

### Descobrir Documentos CVM

```python
from globaldatafinance import FundamentalStocksDataCVM

cvm = FundamentalStocksDataCVM()

# Listar todos os tipos de documentos disponíveis
docs = cvm.get_available_docs()
for code, description in docs.items():
    print(f"{code}: {description}")

# Verificar anos disponíveis
years = cvm.get_available_years()
print(f"\nDados disponíveis de {years.general_min_year} até {years.current_year}")
```

**Saída**:

```
DFP: Demonstração Financeira Padronizada
ITR: Informação Trimestral
FRE: Formulário de Referência
FCA: Formulário Cadastral
...

Dados disponíveis de 2010 até o ano atual
```

### Descobrir Classes de Ativos B3

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()

# Listar classes de ativos disponíveis
assets = b3.get_available_assets()
print("Classes de ativos disponíveis:")
for asset in assets:
    print(f"  • {asset}")

# Verificar intervalo de anos
years = b3.get_available_years()
print(f"\nDados disponíveis de {years['minimal_year']} até {years['current_year']}")
```

**Saída**:

```
Classes de ativos disponíveis:
  • ações
  • etf
  • opções
  • termo
  • exercicio_opcoes
  • forward
  • leilao

Dados disponíveis de 1986 até o ano atual
```

______________________________________________________________________

## Exemplo Completo: Pipeline de Dados

Aqui está um exemplo mais completo que combina download e extração:

```python
from globaldatafinance import FundamentalStocksDataCVM, HistoricalQuotesB3

# === PARTE 1: Download de Documentos CVM ===
print("=" * 60)
print("ETAPA 1: Download de Documentos CVM")
print("=" * 60)

cvm = FundamentalStocksDataCVM()
cvm.download(
    destination_path="/home/usuario/dados_financeiros/cvm",
    list_docs=["DFP", "ITR"],
    initial_year=2022,
    last_year=2023,
    automatic_extractor=True  # Extrai automaticamente para Parquet
)

# === PARTE 2: Extração de Cotações B3 ===
print("\n" + "=" * 60)
print("ETAPA 2: Extração de Cotações B3")
print("=" * 60)

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/home/usuario/dados_financeiros/cotahist",
    assets_list=["ações", "etf"],
    initial_year=2022,
    last_year=2023,
    destination_path="/home/usuario/dados_financeiros/cotacoes",
    output_filename="acoes_etf_2022_2023",
    processing_mode="fast"
)

# === PARTE 3: Análise dos Resultados ===
print("\n" + "=" * 60)
print("RESUMO FINAL")
print("=" * 60)

if result['success']:
    print(f"✓ Pipeline concluído com sucesso!")
    print(f"✓ Total de registros extraídos: {result['total_records']:,}")
    print(f"✓ Arquivo de cotações: {result['output_file']}")
else:
    print(f"✗ Houve erros durante a extração")
    if 'errors' in result and result['errors']:
        for file_name, message in result['errors'].items():
            print(f"  • {file_name}: {message}")
```

______________________________________________________________________

## Trabalhando com os Dados Extraídos

Após extrair os dados, você pode analisá-los com Pandas ou PyArrow. PyArrow é
o engine usado pela biblioteca para produzir os artefatos; Pandas permanece
compatível para consumo tabular.

### Com Pandas

```python
import pandas as pd

# Ler arquivo Parquet gerado
df = pd.read_parquet("/home/usuario/cotacoes_extraidas/cotahist_extracted.parquet")

# Visualizar primeiras linhas
print(df.head())

# Informações sobre o dataset
print(f"\nTotal de registros: {len(df):,}")
print(f"Colunas: {list(df.columns)}")
print(f"Período: {df['data_pregao'].min()} a {df['data_pregao'].max()}")
```

### Com PyArrow em batches

```python
import pyarrow.parquet as pq

# Ler o arquivo sem materializar todas as linhas de uma vez
parquet = pq.ParquetFile(
    "/home/usuario/cotacoes_extraidas/cotahist_extracted.parquet"
)

for batch in parquet.iter_batches(batch_size=100_000, columns=["ticker"]):
    print(batch.slice(0, min(5, batch.num_rows)))
```

Polars não é instalado como dependência da biblioteca. Caso seja o leitor
preferido da sua aplicação, instale-o explicitamente no ambiente consumidor.

______________________________________________________________________

## Dicas para Iniciantes

!!! tip "Comece Pequeno"

    Ao testar pela primeira vez, use intervalos de anos pequenos (ex: 1-2 anos) para entender o comportamento da biblioteca antes de fazer downloads grandes.

!!! tip "Use Modo Fast"

    Para extração de cotações B3, o modo `"fast"` é recomendado na maioria dos casos, oferecendo melhor performance.

!!! tip "Verifique Espaço em Disco"

    Documentos CVM e cotações históricas podem ocupar bastante espaço. Certifique-se de ter espaço suficiente antes de baixar muitos anos.

______________________________________________________________________

## Próximos Passos

Agora que você conhece o básico, explore:

- 📄 **[Documentos CVM](cvm-docs.md)** - Guia completo da API CVM
- 📈 **[Cotações B3](b3-docs.md)** - Guia completo da API B3
- 💻 **[Exemplos Práticos](examples.md)** - Casos de uso avançados
- ❓ **[FAQ](faq.md)** - Perguntas frequentes

______________________________________________________________________

!!! success "Parabéns!"

    Você completou o guia de início rápido! Agora você está pronto para explorar todo o potencial do Global-Data-Finance. 🚀
