# API CVM - Referência Técnica

Documentação técnica detalhada da API CVM.

______________________________________________________________________

## FundamentalStocksDataCVM

### Classe Principal

```python
class FundamentalStocksDataCVM:
    """Interface de alto nível para documentos CVM."""
```

### Métodos

#### `download()`

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

**Descrição**: Baixa documentos CVM para o diretório especificado.

**Parâmetros**:

| Nome                  | Tipo                | Obrigatório | Padrão  | Descrição                              |
| --------------------- | ------------------- | ----------- | ------- | -------------------------------------- |
| `destination_path`    | `str`               | Sim         | -       | Diretório de destino                   |
| `list_docs`           | `list[str] \| None` | Não         | `None`  | Tipos de documentos (None = todos)     |
| `initial_year`        | `int \| None`       | Não         | `None`  | Ano inicial (None = mínimo disponível) |
| `last_year`           | `int \| None`       | Não         | `None`  | Ano final (None = ano atual)           |
| `automatic_extractor` | `bool`              | Não         | `False` | Extrair para Parquet com PyArrow       |

Com `automatic_extractor=True`, o CSV CVM mantém o dialeto `QUOTE_NONE`: aspas
são literais, linhas curtas recebem apenas nulos ao final e linhas excedentes
falham. Um CSV somente com cabeçalho gera Parquet vazio com campos Arrow
`null`, sem metadata `b'pandas'`. Os Parquets do mesmo ZIP usam publicação em
lote recuperável, não visibilidade instantaneamente atômica para leitores
concorrentes.

O nome do arquivo local é o último componente do caminho da URL, após uma
decodificação percent-encoded. A biblioteca rejeita, com `SecurityError`,
separadores, caracteres inválidos do Win32, controles, pontos ou espaços no
final e dispositivos DOS reservados, como `CON`, `AUX`, `COM1` e `LPT1`, antes
de iniciar o download ou criar staging.

**Retorno**:

Retorna um objeto `DownloadResultCVM` contendo os resultados consolidados:

- `success_count_downloads: int` — Quantidade de downloads bem-sucedidos.
- `error_count_downloads: int` — Quantidade de downloads que falharam.
- `successful_downloads: list[str]` — Lista de identificadores concluídos no formato `{DOC}_{YEAR}` (ex.: `"DFP_2023"`).
- `failed_downloads: dict[str, str]` — Dicionário mapeando arquivos com falha para mensagens de erro.
- `elapsed_time: float` — Tempo decorrido em segundos.
- `has_errors() -> bool` — Indica se houve pelo menos uma falha.

**Exceções Síncronas**:

- `InvalidDocumentName`: Tipo de documento inválido.
- `InvalidFirstYear`: Ano inicial inválido.
- `InvalidLastYear`: Ano final inválido.
- `InvalidDestinationPathError`: Caminho de destino inválido ou não seguro.
- `SecurityError`: Nome derivado da URL ou destino local não é seguro.

Falhas de rede ou indisponibilidade transitória de arquivos específicos durante
o download assíncrono são tratadas pelo mecanismo interno de retry. Quando as
tentativas se esgotam, cada falha é consolidada em `failed_downloads` do
`DownloadResultCVM`, sem interromper os demais downloads.

**Exemplo**:

```python
cvm = FundamentalStocksDataCVM()
result = cvm.download(
    destination_path="/data/cvm",
    list_docs=["DFP", "ITR"],
    initial_year=2022,
    last_year=2023,
    automatic_extractor=True
)
```

#### `get_available_docs()`

```python
def get_available_docs(self) -> dict[str, str]:
    ...
```

**Descrição**: Retorna mapeamento de códigos para descrições de documentos.

**Retorno**: Dicionário `{código: descrição}`

**Exemplo**:

```python
docs = cvm.get_available_docs()
# {'DFP': 'Demonstração Financeira Padronizada', ...}
```

#### `get_available_years()`

```python
def get_available_years(self) -> AvailableYearsInfoCVM:
    ...
```

**Descrição**: Retorna informações estruturadas sobre anos mínimos suportados e ano corrente da CVM.

**Retorno (`AvailableYearsInfoCVM`)**: `NamedTuple` com os atributos:

- `general_min_year` (`int`): Ano mínimo para documentos gerais (`DFP`, `FRE`, `FCA`, `IPE`) — `2010`.
- `itr_min_year` (`int`): Ano mínimo para `ITR` — `2011`.
- `cgvn_vlmo_min_year` (`int`): Ano mínimo para `CGVN` e `VLMO` — `2018`.
- `current_year` (`int`): Ano corrente do sistema.

**Exemplo**:

```python
years = cvm.get_available_years()
print(f"Docs gerais a partir de: {years.general_min_year}")
print(f"ITR a partir de: {years.itr_min_year}")
print(f"Ano atual: {years.current_year}")
```

______________________________________________________________________

## Tipos de Documentos

| Código | Nome Completo                       | Desde |
| ------ | ----------------------------------- | ----- |
| DFP    | Demonstração Financeira Padronizada | 2010  |
| ITR    | Informação Trimestral               | 2011  |
| FRE    | Formulário de Referência            | 2010  |
| FCA    | Formulário Cadastral                | 2010  |
| CGVN   | Código de Governança                | 2018  |
| VLMO   | Valores Mobiliários                 | 2018  |
| IPE    | Informações Periódicas e Eventuais  | 2010  |

______________________________________________________________________

## Documentação Relacionada

- [Guia de Uso CVM](../user-guide/cvm-docs.md)
- [Exceções](exceptions.md)
