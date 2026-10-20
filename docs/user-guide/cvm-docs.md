# Documentos CVM

Guia completo para usar a API `FundamentalStocksDataCVM` e baixar documentos fundamentalistas da Comissão de Valores Mobiliários (CVM).

______________________________________________________________________

## Visão Geral

A classe `FundamentalStocksDataCVM` fornece uma interface simples e poderosa para baixar documentos oficiais da CVM, incluindo demonstrações financeiras, formulários de referência e outros documentos regulatórios de empresas brasileiras de capital aberto.

### Características

- ✅ Download automático de múltiplos tipos de documentos
- ✅ Suporte a intervalos de anos flexíveis
- ✅ Extração automática para formato Parquet (opcional)
- ✅ Download assíncrono concorrente
- ✅ Tratamento robusto de erros e retry automático
- ✅ Logging detalhado do progresso

______________________________________________________________________

## Tipos de Documentos Disponíveis

A CVM disponibiliza os seguintes tipos de documentos:

| Código   | Nome Completo                       | Descrição                              | Disponível desde |
| -------- | ----------------------------------- | -------------------------------------- | ---------------- |
| **DFP**  | Demonstração Financeira Padronizada | Balanços anuais completos              | 2010             |
| **ITR**  | Informação Trimestral               | Demonstrações financeiras trimestrais  | 2011             |
| **FRE**  | Formulário de Referência            | Informações detalhadas sobre a empresa | 2010             |
| **FCA**  | Formulário Cadastral                | Dados cadastrais da empresa            | 2010             |
| **CGVN** | Código de Governança                | Práticas de governança corporativa     | 2018             |
| **VLMO** | Valores Mobiliários                 | Informações sobre valores mobiliários  | 2018             |
| **IPE**  | Informações Periódicas e Eventuais  | Documentos periódicos e eventuais      | 2003             |

!!! info "Dados Históricos"

    IPE está disponível desde 2003; DFP/FRE/FCA desde 2010, ITR desde 2011 e CGVN/VLMO desde 2018.

______________________________________________________________________

## Uso Básico

### Importação

```python
from globaldatafinance import FundamentalStocksDataCVM
```

### Criar Instância

```python
cvm = FundamentalStocksDataCVM()
```

### Download Simples

```python
# Baixar DFP dos últimos 3 anos
cvm.download(
    destination_path="/home/usuario/dados_cvm",
    list_docs=["DFP"],
    initial_year=2021,
    last_year=2023
)
```

______________________________________________________________________

## Métodos Principais

### `download()`

Baixa documentos CVM para um diretório especificado.

#### Assinatura

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

#### Parâmetros

| Parâmetro             | Tipo                | Obrigatório | Descrição                                                     |
| --------------------- | ------------------- | ----------- | ------------------------------------------------------------- |
| `destination_path`    | `str`               | ✅ Sim      | Diretório onde os arquivos serão salvos                       |
| `list_docs`           | `list[str] \| None` | ❌ Não      | Lista de tipos de documentos. Se `None`, baixa todos          |
| `initial_year`        | `int \| None`       | ❌ Não      | Ano inicial (inclusive). Se `None`, usa ano mínimo disponível |
| `last_year`           | `int \| None`       | ❌ Não      | Ano final (inclusive). Se `None`, usa ano atual               |
| `automatic_extractor` | `bool`              | ❌ Não      | Se `True`, extrai ZIPs para Parquet automaticamente           |

#### Retorno

Retorna um objeto `DownloadResultCVM` com os seguintes atributos e métodos:

- `success_count_downloads: int` — Total de arquivos baixados com sucesso.
- `error_count_downloads: int` — Total de falhas durante o download.
- `successful_downloads: list[str]` — Identificadores de documentos concluídos no formato `{DOC}_{YEAR}` (ex.: `"DFP_2023"`).
- `failed_downloads: dict[str, str]` — Dicionário mapeando arquivos com falha para a mensagem de erro.
- `elapsed_time: float` — Tempo total de execução em segundos.
- `has_errors() -> bool` — Retorna `True` se houver pelo menos uma falha.

#### Exemplos

**Exemplo 1: Download básico de DFP**

```python
cvm = FundamentalStocksDataCVM()
cvm.download(
    destination_path="/data/cvm",
    list_docs=["DFP"],
    initial_year=2020,
    last_year=2023
)
```

**Exemplo 2: Download de múltiplos documentos**

```python
cvm.download(
    destination_path="/data/cvm",
    list_docs=["DFP", "ITR", "FRE"],
    initial_year=2022
)
```

**Exemplo 3: Download com extração automática**

```python
cvm.download(
    destination_path="/data/cvm",
    list_docs=["DFP"],
    initial_year=2022,
    automatic_extractor=True  # Extrai para Parquet
)
```

**Exemplo 4: Download de todos os documentos**

```python
# list_docs=None baixa TODOS os tipos disponíveis
cvm.download(
    destination_path="/data/cvm_completo",
    initial_year=2023
)
```

### Segurança dos nomes derivados da URL
Consulte a [referência da API CVM](../reference/cvm-api.md) para as regras de `SecurityError` aplicadas antes do download.

______________________________________________________________________

### `get_available_docs()`

Retorna todos os tipos de documentos disponíveis com suas descrições.

#### Assinatura

```python
def get_available_docs(self) -> dict[str, str]:
    ...
```

#### Retorno

Dicionário mapeando códigos de documentos para descrições completas.

#### Exemplo

```python
cvm = FundamentalStocksDataCVM()
docs = cvm.get_available_docs()

for code, description in docs.items():
    print(f"{code}: {description}")
```

**Saída**:

```
DFP: Demonstração Financeira Padronizada
ITR: Informação Trimestral
FRE: Formulário de Referência
FCA: Formulário Cadastral
CGVN: Código de Governança
VLMO: Valores Mobiliários
IPE: Informações Periódicas e Eventuais
```

______________________________________________________________________

#### `get_available_years()`

Retorna informações sobre os anos disponíveis para cada tipo de documento.

#### Assinatura

```python
def get_available_years(self) -> AvailableYearsInfoCVM:
    ...
```

#### Retorno (`AvailableYearsInfoCVM`)

Objeto `NamedTuple` com informações estruturadas de anos disponíveis:

| Atributo             | Tipo  | Descrição                                |
| -------------------- | ----- | ---------------------------------------- |
| `general_min_year`   | `int` | Ano mínimo para documentos gerais (2010) |
| `itr_min_year`       | `int` | Ano mínimo para ITR (2011)               |
| `cgvn_vlmo_min_year` | `int` | Ano mínimo para CGVN/VLMO (2018)         |
| `ipe_min_year` | `int` | IPE: 2003 (propriedade) |
| `current_year`       | `int` | Ano corrente do sistema                  |

#### Exemplo

```python
cvm = FundamentalStocksDataCVM()
years = cvm.get_available_years()

print(f"Documentos gerais disponíveis desde: {years.general_min_year}")
print(f"ITR disponível desde: {years.itr_min_year}")
print(f"Ano atual: {years.current_year}")
```

______________________________________________________________________

## Exemplos Avançados

### Download Incremental

Registre `successful_downloads` em um checkpoint da aplicação. A pasta do ano pode existir após uma falha. Solicite cada ano pendente separadamente para respeitar lacunas no histórico:

```python
import json
from pathlib import Path

from globaldatafinance import FundamentalStocksDataCVM

cvm = FundamentalStocksDataCVM()
base_path = Path("/data/cvm")
checkpoint = base_path / "completed-downloads.json"
completed_downloads = set()
if checkpoint.is_file():
    completed_downloads.update(json.loads(checkpoint.read_text(encoding="utf-8")))
current_year = cvm.get_available_years().current_year
refresh_years = {current_year}
for year in range(2020, current_year + 1):
    identifier = f"DFP_{year}"
    if identifier in completed_downloads and year not in refresh_years:
        continue
    result = cvm.download(
        destination_path=str(base_path), list_docs=["DFP"],
        initial_year=year, last_year=year, automatic_extractor=True,
    )
    if identifier in result.successful_downloads:
        completed_downloads.add(identifier)
        pending = checkpoint.with_suffix(".tmp")
        pending.write_text(json.dumps(sorted(completed_downloads)), encoding="utf-8")
        pending.replace(checkpoint)
    if result.has_errors():
        print(result.failed_downloads)
```

O exemplo usa um checkpoint de um único processo e atualiza o ano corrente a cada execução. A CVM também pode revisar anos anteriores: inclua-os em `refresh_years` conforme a política da aplicação. O checkpoint registra sucessos anteriores; revalide os artefatos locais antes de reutilizá-los e remova os identificadores cujos arquivos estejam ausentes ou corrompidos.

### Validação Prévia

Validar parâmetros antes de iniciar downloads pesados:

```python
from globaldatafinance import FundamentalStocksDataCVM

cvm = FundamentalStocksDataCVM()

# Validar tipos de documentos
requested_docs = ["DFP", "ITR", "FRE"]
available_docs = cvm.get_available_docs()

valid_docs = [doc for doc in requested_docs if doc in available_docs]
invalid_docs = [doc for doc in requested_docs if doc not in available_docs]

if invalid_docs:
    print(f"⚠️  Documentos inválidos: {invalid_docs}")
    print(f"✓ Documentos válidos: {valid_docs}")

# Guarda de segurança: lista vazia acionaria o download de todos os documentos
if not valid_docs:
    raise ValueError("Nenhum documento válido foi informado.")

# Validar anos
years_info = cvm.get_available_years()
requested_year = 2015

if requested_year < years_info.general_min_year:
    print(f"⚠️  Ano {requested_year} não disponível (mínimo: {years_info.general_min_year})")
else:
    # Prosseguir com download
    cvm.download(
        destination_path="/data/cvm",
        list_docs=valid_docs,
        initial_year=requested_year
    )
```

______________________________________________________________________

## Tratamento de Erros

### Exceções Síncronas

A API valida parâmetros na fronteira pública e pode lançar:

| Exceção                       | Quando ocorre                           | Como tratar                                |
| ----------------------------- | --------------------------------------- | ------------------------------------------ |
| `InvalidDocumentName`         | Tipo de documento inválido              | Verificar lista com `get_available_docs()` |
| `InvalidFirstYear`            | Ano inicial fora do intervalo           | Verificar anos com `get_available_years()` |
| `InvalidLastYear`             | Ano final inválido ou menor que inicial | Validar intervalo de anos                  |
| `InvalidDestinationPathError` | Caminho de destino inválido             | Verificar permissões e caminho             |

> Falhas transitórias de conexão durante o download assíncrono passam pela [política de retry e HTTP](../dev-guide/retry-strategy.md). Erros persistentes são consolidados no atributo `failed_downloads` do `DownloadResultCVM` retornado.

______________________________________________________________________

## Estrutura dos Arquivos Baixados

### Organização de Diretórios

Após o download, os arquivos são organizados da seguinte forma:

```
destination_path/
    DFP/
        2020/
            dfp_cia_aberta_2020.zip
        2021/
            dfp_cia_aberta_2021.zip
        ...
    ITR/
        2020/
            itr_cia_aberta_2020.zip
        ...
    FRE/
        2020/
            fre_cia_aberta_2020.zip
        ...
```

### Conteúdo dos Arquivos ZIP

Cada arquivo ZIP contém múltiplos arquivos CSV com dados estruturados:

```

dfp_cia_aberta_2023.zip
├── dfp_cia_aberta_2023.csv # Dados principais
├── dfp_cia_aberta_BPA_con_2023.csv # Balanço Patrimonial Ativo Consolidado
├── dfp_cia_aberta_BPP_con_2023.csv # Balanço Patrimonial Passivo Consolidado
├── dfp_cia_aberta_DRE_con_2023.csv # Demonstração do Resultado
├── dfp_cia_aberta_DFC_MD_con_2023.csv # Fluxo de Caixa (Método Direto)
├── dfp_cia_aberta_DFC_MI_con_2023.csv # Fluxo de Caixa (Método Indireto)
├── dfp_cia_aberta_DVA_con_2023.csv # Demonstração do Valor Adicionado
└── ...

```

### Extração Automática para Parquet

Quando `automatic_extractor=True`, os arquivos são convertidos para Parquet:

```
destination_path/
├── DFP/
    2023/
    │ ├── dfp_cia_aberta_2023.parquet
    │ ├── dfp_cia_aberta_BPA_con_2023.parquet
    │ ├── dfp_cia_aberta_BPP_con_2023.parquet
    │ └── ...
└── ...

```

### Integridade e recuperação da extração

Cada ZIP é validado antes do consumo. Todas as colunas são Arrow `string`
no contrato `exact-text-v1`, preservando decimais, zeros iniciais, caixa,
textos como `N/A` e campos vazios como `""`. CSV só com cabeçalho gera zero
linhas com colunas `string`. `QUOTE_NONE` mantém aspas literais; linhas curtas
recebem campos vazios finais e campos excedentes abortam.

O SHA-256 de todos os registros é conferido contra o Parquet reaberto antes
da publicação. Checksums, `fsync` e associação do Parquet ao ZIP consumido
impedem confirmar conteúdo incompleto ou divergente. O ZIP original permanece
no destino, incluindo anexos não CSV. Os Parquets têm commit recuperável por
lote; a visibilidade conjunta para leitores concorrentes não é instantânea.

Escritores concorrentes para o mesmo destino são rejeitados antes da promoção
do ZIP. Um `.cvm-write-lock` deixado por terminação abrupta exige inspeção
explícita antes da recuperação. Para limites, encoding e migração do
consumidor, consulte a [migração CVM exata](migration-cvm-exact-text.md).

## Boas Práticas

### 1. Use Intervalos de Anos Razoáveis

```python
# ❌ Evite baixar muitos anos de uma vez
cvm.download(
    destination_path="/data",
    list_docs=["DFP"],
    initial_year=2003,  # Includes the full IPE history
    last_year=2023
)

# ✅ Prefira intervalos menores
cvm.download(
    destination_path="/data",
    list_docs=["DFP"],
    initial_year=2020,  # 3-4 anos
    last_year=2023
)
```

### 2. Verifique Espaço em Disco

```python
import shutil

# Verificar espaço disponível
stats = shutil.disk_usage("/data")
free_gb = stats.free / (1024**3)

if free_gb < 10:
    print(f"⚠️  Pouco espaço disponível: {free_gb:.2f} GB")
else:
    cvm.download(
        destination_path="/data/cvm",
        list_docs=["DFP"],
        initial_year=2023
    )
```

### 3. Use Extração Automática para Análise

```python
# Se você vai analisar os dados, use Parquet
cvm.download(
    destination_path="/data/cvm",
    list_docs=["DFP"],
    initial_year=2022,
    automatic_extractor=True  # Muito mais rápido para ler
)
```

## Performance

### Modo de Download

O `FundamentalStocksDataCVM` usa `AsyncDownloadAdapterCVM` por padrão, que oferece:

- ⚡ Até **10 downloads concorrentes** por padrão
- 🔄 **Retry automático** em caso de falhas
- 📊 **Progress tracking** detalhado

### Benchmarks

**Linha de base v2 — fluxo completo: download + extração CSV→Parquet
(2010–2026, revisão `703d9ab`):**

Esta medição histórica usa o contrato anterior ao `exact-text-v1`.

| Docs                | Período   | ZIPs | Parquets |      Linhas |     Saída |     Tempo | Pico RSS | Erros |
| ------------------- | --------- | ---: | -------: | ----------: | --------: | --------: | -------: | ----: |
| DFP, ITR, FRE, etc. | 2010–2026 |  102 |    1.569 | 70.821.466 | 382,27 MB | 906,85 s | 333,91 MB |     0 |

O tempo inclui conexão, downloads, validação, extração CSV e geração dos
Parquets para os 102 ZIPs. Ele varia com a rede e os servidores da CVM e não
representa uma comparação isolada com download sequencial. Consulte os
[detalhes e limitações do benchmark](../dev-guide/benchmarks.md).

## Próximos Passos

- 📈 **[Cotações B3](b3-docs.md)** - Aprenda a extrair cotações históricas
- 💻 **[Exemplos Práticos](examples.md)** - Veja casos de uso completos
- 🔧 **[API Reference](../reference/cvm-api.md)** - Documentação técnica detalhada
- ❓ **[FAQ](faq.md)** - Perguntas frequentes

______________________________________________________________________

!!! tip "Dica de Performance"

    Para análises de dados, sempre use `automatic_extractor=True`. O formato Parquet é muito mais eficiente que CSV para leitura e processamento.
