# Exemplos de Uso - GlobalDataFinance

Esta pasta contém exemplos práticos executáveis para iniciar rapidamente a extração e o processamento de dados financeiros brasileiros usando a biblioteca `globaldatafinance`.

______________________________________________________________________

## 📌 Diferença Entre as Fontes

- **CVM (`FundamentalStocksDataCVM`)**: Realiza o **download automático** (via HTTP assíncrono) das Demonstrações Financeiras diretamente dos servidores da CVM e converte em arquivos Parquet.
- **B3 (`HistoricalQuotesB3`)**: Faz a **leitura, filtragem e conversão** de arquivos oficiais de cotações históricas (`COTAHIST_AYYYY.ZIP` ou `.TXT`) armazenados em uma pasta local (`path_of_docs`) e consolida em Parquet. A API aceita os formatos locais ZIP e TXT; o download oficial da B3 continua sendo distribuído em ZIP. *(Nota: A biblioteca não baixa os arquivos COTAHIST da B3, ela processa os arquivos locais existentes).*

______________________________________________________________________

## 🚀 Como Executar os Exemplos

Todos os exemplos utilizam a ferramenta `uv` para gerenciar dependências e o ambiente virtual de forma rápida e reprodutível.

### 1. Início Rápido com CVM (`01_quickstart_cvm.py`)

Baixa as Demonstrações Financeiras Padronizadas (**DFP**) da CVM do ano de 2023 diretamente da internet e converte automaticamente em arquivos Parquet.

```bash
uv run python examples/01_quickstart_cvm.py
```

______________________________________________________________________

### 2. Extração Rápida de Ações da B3 (`02_quickstart_b3.py`)

Lê os arquivos de cotações históricas da B3 (**COTAHIST**) presentes na pasta local `./cotahist_b3`, filtra apenas os negócios com **Ações** e gera um arquivo Parquet consolidado.

```bash
uv run python examples/02_quickstart_b3.py
```

______________________________________________________________________

### 3. Extração Avançada da B3 (`03_advanced_options_b3.py`)

Demonstra a extração de múltiplos ativos simultâneos (**Ações, ETFs e Opções**) a partir dos arquivos COTAHIST locais de 2022 e 2023, utilizando o **modo de alto desempenho (`processing_mode="fast"`)**.

```bash
uv run python examples/03_advanced_options_b3.py
```

______________________________________________________________________

## 📁 Estrutura dos Arquivos de Saída

Por padrão, os exemplos salvam os dados em formato **Parquet** e usam
**PyArrow** como leitor nativo. Pandas e Polars são opções downstream; instale
explicitamente a biblioteca escolhida no ambiente consumidor antes de usá-la:

```bash
python -m pip install pandas  # opcional, para DataFrames
python -m pip install polars  # opcional, para consultas Polars
```

- `./dados_cvm/`: Contém os arquivos `.parquet` por tipo de relatório da CVM.
- `./dados_b3/`: Contém os arquivos Parquet consolidados com o nome especificado em `output_filename`.

______________________________________________________________________

## 📚 Mais Documentação

Para acessar a documentação completa da biblioteca e parâmetros avançados:

- [Guia do Usuário CVM](../docs/user-guide/cvm-docs.md)
- [Guia do Usuário B3](../docs/user-guide/b3-docs.md)
- [Exemplos Detalhados na Doc](../docs/user-guide/examples.md)
