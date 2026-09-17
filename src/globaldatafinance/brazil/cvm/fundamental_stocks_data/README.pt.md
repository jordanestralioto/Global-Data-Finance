# Módulo de Dados Fundamentais (CVM)

> [!NOTE]
> Este módulo integra a suíte `Global-Data-Finance` e fornece uma interface robusta para automação de downloads de documentos regulatórios da CVM (Comissão de Valores Mobiliários).

O módulo `fundamental_stocks_data` foi projetado para simplificar a aquisição de dados públicos de companhias abertas brasileiras. Ele gerencia a complexidade de URLs dinâmicas, estrutura de diretórios e resiliência de rede, tudo encapsulado em uma arquitetura limpa e extensível.

## 🎯 Objetivos e Valor

- **Automação Confiável**: Elimina o trabalho manual de buscar arquivos no site da CVM.
- **Gestão de Falhas**: Sistema robusto de retentativas e relatório detalhado de erros.
- **Organização Automática**: Estrutura os arquivos baixados por tipo e ano, facilitando o consumo posterior.
- **Extensibilidade**: adapter HTTP concreto (`AsyncDownloadAdapterCVM`) construído diretamente. Quando uma segunda implementação aparecer (ex.: `WgetDownloadAdapter`), extrair um `Protocol` é trivial.

## 🏗️ Arquitetura

Módulos focados e subpacote de conversão:

```text
brazil/cvm/fundamental_stocks_data/
├── core.py                   # AvailableDocsCVM, AvailableYearsCVM, DictZipsToDownloadCVM, DownloadResultCVM, UrlDocsCVM
├── client.py                 # consultas públicas, orquestração e validação de paths
├── http.py                   # AsyncDownloadAdapterCVM (httpx async + retry/back-off + integrity check)
├── extract.py                # ParquetExtractorAdapterCVM (limite de extração)
├── transaction.py            # staging, backup e commit recuperável em lote
├── csv_pipeline/             # subpacote de ingestão streaming de CSV e conversão Parquet via PyArrow
├── errors.py                 # InvalidDocumentName, InvalidFirstYear, InvalidLastYear, MissingDownloadUrlError, etc.
├── download_paths.py         # validação de basenames derivados de URLs
├── download_validation.py    # Validação de ZIPs e Parquets gerados (integridade estrutural e de dados)
└── download_extraction.py    # Delegação de extração e rastreamento de artefatos para rollback
```

`DownloadDocumentsUseCaseCVM` orquestra a geração de URLs, a validação de
paths (`VerifyPathsUseCasesCVM` — `SecurityError` para destinos sensíveis) e o
download via `AsyncDownloadAdapterCVM` injetado.

### Componentes Chave

| Módulo                   | Componente                    | Tipo                  | Responsabilidade                                                                                             |
| ------------------------ | ----------------------------- | --------------------- | ------------------------------------------------------------------------------------------------------------ |
| `client.py`              | `DownloadDocumentsUseCaseCVM` | Orquestrador (classe) | Coordena geração de URLs, validação de paths e execução de download (`execute` e `execute_async`). Stateful. |
| `client.py`              | `generate_urls`               | Função de aplicação   | Constrói URLs de download a partir de `DictZipsToDownloadCVM`.                                               |
| `client.py`              | `VerifyPathsUseCasesCVM`      | Use case              | Cria estrutura de diretórios de destino. Raise `SecurityError` em paths sensíveis.                           |
| `core.py`                | `DownloadResultCVM`           | Result object         | Resultado agregado contendo sucessos, falhas e contadores (`elapsed_time` incluso).                          |
| `core.py`                | `DictZipsToDownloadCVM`       | Value object          | Mapeamento documento → URLs por ano.                                                                         |
| `http.py`                | `AsyncDownloadAdapterCVM`     | Adapter concreto      | Downloads assíncronos com retry/back‑off e delegação de extração.                                            |
| `extract.py`             | `ParquetExtractorAdapterCVM`  | Adapter concreto      | Abre o ZIP e delega o commit recuperável da conversão.                                                       |
| `transaction.py`         | `CvmFailureAtomicBatchCommit` | Detalhe de extração   | Faz staging, validação, backup e restauração determinística por lote.                                        |
| `csv_pipeline/`          | `CsvToParquetPipelineCVM`     | Subpacote conversão   | Ingestão streaming de CSV e escrita tipada Parquet em chunks limitados em memória (`chunk_size`).            |
| `download_extraction.py` | `extract_downloaded_file`     | Helper / Use case     | Rastreia os artefatos publicados e valida o resultado do download.                                           |
| `download_validation.py` | `validate_downloaded_file`    | Helper                | Valida integridade e completude de ZIPs e arquivos Parquet extraídos.                                        |

## 🚀 Guia de Uso

### Exemplo Completo

```python
from globaldatafinance.brazil.cvm.fundamental_stocks_data import (
    AsyncDownloadAdapterCVM,
    DownloadDocumentsUseCaseCVM,
    ParquetExtractorAdapterCVM,
)


def baixar_dados_cvm():
    # 1. Adapter HTTP concreto (httpx async + retry + integrity check)
    repository = AsyncDownloadAdapterCVM(
        file_extractor_repository=ParquetExtractorAdapterCVM()
    )

    # 2. Orquestrador
    downloader = DownloadDocumentsUseCaseCVM(repository=repository)

    print('Iniciando downloads...')

    # 3. Execução (síncrona ou assíncrona via execute_async)
    try:
        resultado = downloader.execute(
            destination_path='./dados_cvm',  # Diretório raiz para salvar
            list_docs=['DFP', 'ITR', 'FRE'],  # Tipos de documentos
            initial_year=2022,  # Ano inicial
            last_year=2023,  # Ano final
            automatic_extractor=True,  # Extrair automaticamente CSVs para Parquet
        )

        # 4. Análise dos Resultados
        print('\nResumo da Operação:')
        print(f'⏱️ Tempo decorrido: {resultado.elapsed_time:.2f}s')
        print(f'✅ Sucessos: {resultado.success_count_downloads}')
        print(f'❌ Falhas: {resultado.error_count_downloads}')

        if resultado.failed_downloads:
            print('\nDetalhes das falhas:')
            for doc, erro in resultado.failed_downloads.items():
                print(f' - {doc}: {erro}')

    except Exception as e:
        print(f'Erro crítico na execução: {e}')


if __name__ == '__main__':
    baixar_dados_cvm()
```

## ⚙️ Referência da API

### `DownloadDocumentsUseCaseCVM.execute`

Também disponível como `execute_async(...)` para execução dentro de loops assíncronos existentes.

| Parâmetro             | Tipo        | Obrigatório | Descrição                                                                                                                             |
| --------------------- | ----------- | ----------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `destination_path`    | `str`       | Sim         | Caminho base onde as pastas por documento serão criadas.                                                                              |
| `list_docs`           | `list[str]` | Não         | Lista de códigos de documentos que serão baixados. Valores válidos: `DFP`, `ITR`, `FRE`, `FCA`, `CGVN`, `IPE`, `VLMO`. Padrão: todos. |
| `initial_year`        | `int`       | Não         | Ano de início da coleta.                                                                                                              |
| `last_year`           | `int`       | Não         | Ano final da coleta.                                                                                                                  |
| `automatic_extractor` | `bool`      | Não         | Extrai e converte automaticamente CSVs em arquivos Parquet via batch commit. Padrão: `False`.                                         |

#### Tipos de Documentos Disponíveis

| Código | Nome                                   | Descrição                      |
| ------ | -------------------------------------- | ------------------------------ |
| `DFP`  | Demonstrações Financeiras Padronizadas | Balanço, DRE, DFC, DVA (anual) |
| `ITR`  | Informações Trimestrais                | Demonstrações trimestrais      |
| `FRE`  | Formulário de Referência               | Informações corporativas       |
| `FCA`  | Formulário Cadastral                   | Dados cadastrais               |
| `CGVN` | Código de Governança                   | Governança corporativa         |
| `IPE`  | Informações Eventuais                  | Atas, fatos relevantes         |
| `VLMO` | Valores Mobiliários                    | Títulos negociados             |

### `DownloadResultCVM` (Retorno)

Objeto retornado pelos métodos `execute` e `execute_async`, contendo:

- `successful_downloads` (`list[str]`): Lista de identificadores lógicos concluídos no formato `{DOC}_{YEAR}` (ex.: `DFP_2023`), não caminhos de arquivo.
- `failed_downloads` (`dict[str, str]`): Dicionário que mapeia identificadores `{DOC}_{YEAR}` para mensagens de erro.
- `elapsed_time` (`float`): Tempo total de execução da coleta em segundos.
- `success_count_downloads` (`int` property): Contagem total de sucessos.
- `error_count_downloads` (`int` property): Contagem total de erros.
- `has_errors()` (`bool` method): Retorna `True` caso algum download tenha falhado (`error_count_downloads > 0`).

### Tratamento de Erros

Exceções definidas em `globaldatafinance.brazil.cvm.fundamental_stocks_data.errors` (re-exportadas pelo `__init__.py` da fonte):

- `MissingDownloadUrlError`: não foi possível gerar uma URL para o documento/ano solicitado.
- `InvalidDocumentName`: tipo de documento não reconhecido.
- `InvalidFirstYear` / `InvalidLastYear`: ano inválido ou fora do range suportado.
- `SecurityError` (de `macro_exceptions`): tentativa de escrita em path sensível ou nome de arquivo derivado de URL que não é portátil — defesa em `VerifyPathsUseCasesCVM` e `download_paths.py`.

> Nota: A integridade da tipagem dos adaptadores é checada estaticamente via ferramentas como `mypy` e verificação de contratos de métodos (duck typing), promovendo a adoção direta e limpa do adapter concreto (`AsyncDownloadAdapterCVM`).

## 🔧 Troubleshooting

> [!CAUTION]
> **Bloqueio de IP**
> O site da CVM pode bloquear IPs que realizam muitas requisições em curto período. O adaptador de infraestrutura deve implementar "backoff" ou pausas entre requisições.

> [!TIP]
> **Estrutura de Pastas**
> O sistema cria automaticamente subpastas para cada tipo de documento dentro de `destination_path`. Não é necessário criá-las manualmente.

## 🔎 Como funciona a extração dos arquivos da CVM

A extração é orquestrada por **`download_extraction.py`**, iniciada pelo
**`ParquetExtractorAdapterCVM`** em `extract.py`, suportada pelo subpacote
**`csv_pipeline/`** e concretizada por `transaction.py` quando
`automatic_extractor=True`. O fluxo completo é:

1. **Validação do ZIP e dos membros CSV** antes de qualquer escrita: limites,
   integridade, nomes e colisões de basename são rejeitados.
2. **Conversão em staging no mesmo filesystem**: cada CSV vira Parquet em um
   diretório oculto; nenhum destino final muda nesta fase.
3. **Validação dos Parquets staged**: todos precisam ter conteúdo e footer
   válido antes do commit.
4. **Backup e substituição determinística**: alvos existentes são preservados
   e os Parquets staged são publicados em ordem estável.
5. **Restauração recuperável em caso de falha**: os alvos já modificados são
   restaurados em ordem reversa. Se a restauração também falhar, o diretório de
   recovery é mantido e informado para intervenção manual.
6. **Rastreamento e validação pós-extração** em `download_extraction.py`:
   apenas os artefatos publicados entram no resultado do download.

### Por que essa abordagem?

- **Commit recuperável por lote**: protege os alvos existentes contra uma
  falha parcial; não promete visibilidade instantaneamente atômica para todos
  os leitores concorrentes.
- **Escalabilidade**: o processamento em chunks (`chunk_size`) permite lidar com arquivos CSV de grande porte sem esgotar a memória.
- **Resiliência**: back‑off e retries são implementados no adaptador de download; na extração, falhas são capturadas e revertidas de forma controlada.

> **Nota**: Caso deseje desabilitar a extração automática (por exemplo, para apenas baixar os ZIPs), basta configurar `automatic_extractor=False` no método `downloader.execute(...)` ou no facade `FundamentalStocksDataCVM`.
