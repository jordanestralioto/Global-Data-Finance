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

Com `automatic_extractor=True`, todas as colunas CVM são Arrow `string`
no contrato `exact-text-v1`. Cada campo mantém o texto original: decimais,
zeros iniciais, sinais, caixa e tokens como `N/A`, `NULL` ou `None`; campos
vazios são `""`. CSV só com cabeçalho gera zero linhas com colunas `string`.
O dialeto permanece `QUOTE_NONE`, com aspas literais. Linhas curtas recebem
campos vazios finais; campos excedentes, cabeçalhos vazios ou duplicados,
mais de 4.096 colunas e registros físicos acima de 8 MiB UTF-8 falham.

Todos os registros decodificados são comparados por SHA-256 com o Parquet
reaberto antes da publicação. Os arquivos incluem checksums de página,
identidade do ZIP e do membro CSV nos metadados e sincronização com `fsync`.
A confirmação exige todos os Parquets esperados e sua associação ao ZIP.
Row groups respeitam um orçamento estimado de 16 MiB, até 50.000 linhas.
As leituras permanecem no mesmo ZIP aberto e a origem é conferida novamente
antes da publicação. CSVs removidos ou renomeados exigem regeneração em um
destino limpo quando restarem Parquets obsoletos do mesmo arquivo.

O ZIP original é retido após sucesso e falha, incluindo membros não CSV.
Chamadas concorrentes para o mesmo destino são rejeitadas antes da promoção
do ZIP. Após terminação abrupta, `.cvm-write-lock` requer inspeção explícita
antes da recuperação. A publicação de vários Parquets é recuperável por
lote; sua visibilidade para leitores concorrentes não é instantaneamente
atômica. Encoding sem declaração pode ser ambíguo, e consistência contábil
não é inferida pelo pipeline.

A alteração de schema exige [migração do consumidor](../user-guide/migration-cvm-exact-text.md).

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

Se o diretório de saída desaparecer, virar um arquivo ou apresentar uma falha
de I/O ao criar o lock após o download, a finalização registra a falha em
`failed_downloads` e continua os outros destinos. A substituição por outro
diretório ou por um link simbólico é rejeitada com `SecurityError`.

Em sistemas com operações relativas a descritores de diretório, o lock, a
promoção do ZIP e a limpeza permanecem vinculados ao diretório aberto. A
extração automática reutiliza essa ownership para ler o ZIP, escrever o staging
e publicar os Parquet. Os leitores e escritores usam caminhos vinculados ao
descritor por `/proc/self/fd` ou `/dev/fd`; se ambos estiverem indisponíveis,
a extração falha com `SecurityError`, antes de escrever os dados por um caminho
mutável. Os manifestos persistem os nomes relativos originais. A limpeza
preserva o staging e registra um diagnóstico quando não consegue confirmar a
identidade do diretório originalmente validado.

Nos sistemas sem esse suporte, a biblioteca confere a identidade antes das
operações por caminho. Nesses sistemas, alterações simultâneas por processos
que não seguem o protocolo de ownership não têm a mesma garantia atômica.

A seleção de URLs respeita o primeiro ano de cada documento: IPE em 2003;
DFP, FCA e FRE em 2010; ITR em 2011; CGVN e VLMO em 2018. Um intervalo misto
não gera URLs para anos anteriores ao início do documento.

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

- `general_min_year` (`int`): Ano mínimo para documentos gerais (`DFP`, `FRE`, `FCA`) — `2010`.
- `itr_min_year` (`int`): Ano mínimo para `ITR` — `2011`.
- `cgvn_vlmo_min_year` (`int`): Ano mínimo para `CGVN` e `VLMO` — `2018`.
- `current_year` (`int`): Ano corrente do sistema.
- `ipe_min_year` (`int`, propriedade): Ano mínimo de IPE — `2003`; acessível como propriedade da tupla.

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
| IPE    | Informações Periódicas e Eventuais  | 2003  |

______________________________________________________________________

## Documentação Relacionada

- [Guia de Uso CVM](../user-guide/cvm-docs.md)
- [Exceções](exceptions.md)
