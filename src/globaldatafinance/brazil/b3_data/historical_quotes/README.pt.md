# Módulo de Cotações Históricas (B3)

> [!NOTE] Este módulo faz parte da suíte `Global-Data-Finance` e é especializado
> na extração de alta performance de dados históricos da B3.

O módulo `historical_quotes` implementa uma solução robusta para processar
arquivos da série histórica (COTAHIST) da B3. Ele abstrai a complexidade do
layout posicional de arquivos legados, oferecendo uma interface moderna e tipada
para extração de dados financeiros. Internamente combina módulos focados por
responsabilidade com subpacotes especializados para orquestração do streaming e
escrita em Parquet, sem reproduzir camadas genéricas
`domain`/`application`/`infra`.

## 🎯 Objetivos e Valor

- **Abstração de Layout**: Remove a necessidade de conhecer o layout posicional
  (bytes/offsets) dos arquivos da B3.
- **Performance**: Utiliza estratégias de leitura otimizada e escrita em formato
  colunar (Parquet).
- **Integridade**: Validação estrita de parâmetros de entrada e tratamento de
  erros específico de domínio com diagnósticos contextuais de registros.
- **Filtragem por Classe de Ativo**: Capacidade de filtrar a extração por
  classes de ativos (ações, ETF, opções, etc.).

## 🏗️ Arquitetura

Módulos focados e subpacotes especializados:

```text
brazil/b3_data/historical_quotes/
├── models.py              # DocsToExtractorB3 (data object)
├── filesystem.py          # FileSystemServiceB3 (validação de caminhos e arquivos COTAHIST)
├── assets.py              # AvailableAssetsServiceB3 (classes de ativos e mapeamento TPMERC)
├── processing.py          # ExtractionConfigServiceB3, ProcessingModeEnumB3
├── years.py               # Lógica e validação de anos
├── client.py              # ExtractHistoricalQuotesUseCaseB3, CreateDocsToExtractUseCaseB3, etc.
├── cotahist_parser.py     # Parsing posicional COTAHIST (preservado — complexidade legítima)
├── integrity.py           # B3RecordContext (diagnósticos contextuais delimitados de registros)
├── member_resolver.py     # resolve_cotahist_member (resolução e compatibilidade de membro interno ZIP)
├── parquet_writer/        # Subpacote de escrita Parquet (writer, schema, session, disk, constants)
├── extraction_service/    # Subpacote de orquestração (service, zip_processor, resource_policy, retry, temp_parquet_merge, types)
├── catalog.py              # Catálogo estrito e precedência dos inputs COTAHIST
├── zip_reader.py          # Leitura streaming de ZIP ou TXT
└── errors.py              # InvalidFirstYear, InvalidLastYear, InvalidAssetsName, EmptyAssetListError, InvalidProcessingMode, etc.
```

`ExtractHistoricalQuotesUseCaseB3` permanece como classe (D3) porque mantém
estado: `zip_reader + parser + writer + processing_mode` são reutilizados entre
chamadas. Disponibiliza execução assíncrona com `execute()` e síncrona com
`execute_sync()`.

`catalog.py` pertence ao owner B3 e é usado por validações opt-in que precisam
auditar um diretório caller-owned antes de processar dados reais. Ele aceita
somente os nomes externos `COTAHIST_A{ANO}.ZIP` e `COTAHIST_A{ANO}.TXT`, valida
metadados/CRC e o membro interno root, rejeita conflitos no mesmo formato e
mantém precedência ZIP quando ZIP e TXT coexistem para o mesmo ano.

### Componentes Chave

| Módulo                | Componente                         | Tipo                  | Responsabilidade                                                                                                                                                                     |
| --------------------- | ---------------------------------- | --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `client.py`           | `ExtractHistoricalQuotesUseCaseB3` | Orquestrador (classe) | Conecta parser, leitor e escritor. Mantém estado entre chamadas. Oferece `execute()` e `execute_sync()`. Suporta limites de segurança e allowed UNC roots.                           |
| `client.py`           | `CreateDocsToExtractUseCaseB3`     | Use case              | Constrói `DocsToExtractorB3` validado a partir dos parâmetros públicos do facade, resolvendo os inputs para caminhos absolutos.                                                      |
| `models.py`           | `DocsToExtractorB3`                | Data object           | Representa a configuração de extração já preparada; não executa validação ao ser construído diretamente.                                                                             |
| `filesystem.py`       | `FileSystemServiceB3`              | Service               | Valida paths (`SecurityError`/`PathPermissionError` antes de I/O) e resolve regex de arquivos oficiais.                                                                              |
| `assets.py`           | `AvailableAssetsServiceB3`         | Service               | Fornece aliases de classes de ativos e valida os nomes dessas classes (não códigos de negociação individuais como PETR4).                                                            |
| `processing.py`       | `ExtractionConfigServiceB3`        | Service               | Valida modo de processamento (`fast`, `slow`) e sanitiza/formata `output_filename`.                                                                                                  |
| `years.py`            | `YearValidationServiceB3`          | Service               | Implementa validação e lógica de limite temporal para o `range_years`.                                                                                                               |
| `cotahist_parser.py`  | `CotahistParserB3`                 | Parser concreto       | Traduz linhas de texto posicional em dicionários Python estruturados.                                                                                                                |
| `integrity.py`        | `B3RecordContext`                  | Modelo diagnóstico    | Rastreia coordenadas (linha física, registro lógico, campo) para diagnóstico contextual seguro sem truncamento cego em falhas de parsing.                                            |
| `member_resolver.py`  | `resolve_cotahist_member`          | Função de resolução   | Resolve o membro raiz compatível nos metadados do ZIP (`COTAHIST_A{ANO}.TXT`, `COTAHIST.A{ANO}`, `COTAHIST_A{ANO}`) e valida correspondência com o ano externo.                      |
| `parquet_writer/`     | `ParquetWriterB3`                  | Writer concreto       | Escrita Parquet com schema Arrow explícito, compressão zstd, statistics e sessões persistentes limitadas. Subpacote (`writer`, `schema`, `session`, `disk`, `constants`).            |
| `extraction_service/` | `ExtractionServiceB3`              | Service concreto      | Scheduler limitado, workers síncronos, retry de I/O transitório e merge ordenado. Subpacote (`service`, `zip_processor`, `resource_policy`, `retry`, `temp_parquet_merge`, `types`). |

## 🚀 Guia de Uso

### Pré-requisitos

Certifique-se de ter os arquivos `COTAHIST_A{ANO}.ZIP` baixados, ou os
respectivos arquivos `COTAHIST_A{ANO}.TXT` descompactados, em um diretório
acessível. Se os dois formatos do mesmo ano estiverem presentes, o ZIP terá
precedência determinística. Em ZIPs, o membro interno pode ser o moderno
`COTAHIST_A{ANO}.TXT`, o histórico `COTAHIST.A{ANO}` ou o histórico sem extensão
`COTAHIST_A{ANO}`; deve haver exatamente um membro compatível com o ano externo.
Registros de cotação `01` têm largura exata de 245 caracteres, e ZIPs
estruturalmente inseguros são rejeitados antes do streaming.

### Exemplo Completo

```python
import asyncio
from globaldatafinance.brazil.b3_data.historical_quotes import (
    CreateDocsToExtractUseCaseB3,
    ExtractHistoricalQuotesUseCaseB3,
)


async def run_extraction():
    # 1. Validar a entrada e preparar a configuração
    # O use case valida os parâmetros e resolve os inputs para caminhos absolutos.
    config = CreateDocsToExtractUseCaseB3(
        path_of_docs='/dados/brutos/b3',  # Onde estão os inputs ZIP/TXT
        destination_path='/dados/processados',
        assets_list=['ações', 'etf'],
        initial_year=2023,
        last_year=2023,
    ).execute()

    # 2. Execução (assíncrona ou execute_sync)
    use_case = ExtractHistoricalQuotesUseCaseB3()

    try:
        result = await use_case.execute(
            docs_to_extract=config,
            processing_mode='fast',  # 'fast' (memória) ou 'slow' (iterativo)
            output_filename='b3_quotes_2023.parquet',
        )

        print(f'Sucesso! {result["total_records"]} registros processados.')
        print(f'Arquivo Parquet de saída: {result["output_file"]}')

    except Exception as e:
        print(f'Erro durante a extração: {e}')


if __name__ == '__main__':
    asyncio.run(run_extraction())
```

## ⚙️ Referência da API

### `DocsToExtractorB3` (Configuração preparada)

`DocsToExtractorB3` é um objeto de dados e não valida a construção direta. Use
`CreateDocsToExtractUseCaseB3` para validar os parâmetros públicos e preencher
`documents_to_download` com os caminhos absolutos encontrados no diretório.

| Campo                   | Tipo       | Descrição                                                                                                                                                                                       |
| ----------------------- | ---------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `path_of_docs`          | `str`      | Caminho absoluto para o diretório contendo arquivos COTAHIST ZIP ou TXT.                                                                                                                        |
| `destination_path`      | `str`      | Caminho absoluto onde o arquivo Parquet será salvo.                                                                                                                                             |
| `range_years`           | `range`    | Intervalo de anos para validação (ex: `range(2020, 2024)`).                                                                                                                                     |
| `set_assets`            | `set[str]` | Conjunto de tipos de ativos para filtrar (ex: `{"ações", "etf", "opções"}`). Valores válidos: `ações`, `etf`, `opções`, `termo`, `exercicio_opcoes`, `forward`, `leilao`.                       |
| `documents_to_download` | `set[str]` | Caminhos absolutos dos arquivos COTAHIST ZIP/TXT selecionados pelo `FileSystemServiceB3`; o `CreateDocsToExtractUseCaseB3` preenche este campo. Construção direta exige caminhos já resolvidos. |

### `ExtractHistoricalQuotesUseCaseB3` (Execução e Retorno)

Métodos:

- `execute(docs_to_extract, processing_mode='fast', output_filename='cotahist_extracted.parquet')`:
  Ponto de entrada assíncrono retornando o dicionário de resultados.
- `execute_sync(docs_to_extract, processing_mode='fast', output_filename='cotahist_extracted.parquet')`:
  Wrapper síncrono sobre `execute()`.

Esquema do dicionário de retorno:

| Chave           | Tipo             | Descrição                                                                     |
| --------------- | ---------------- | ----------------------------------------------------------------------------- |
| `total_files`   | `int`            | Total de arquivos COTAHIST inspecionados para extração.                       |
| `success_count` | `int`            | Contagem de arquivos processados com sucesso.                                 |
| `error_count`   | `int`            | Contagem de arquivos que falharam no processamento.                           |
| `total_records` | `int`            | Quantidade total de registros de cotação gravados no arquivo Parquet.         |
| `errors`        | `dict[str, str]` | Mapeamento de caminhos de arquivos com falha para suas respectivas mensagens. |
| `output_file`   | `str`            | Caminho absoluto resolvido para o arquivo Parquet gerado.                     |

### Tratamento de Erros

O módulo expõe exceções específicas em
`globaldatafinance.brazil.b3_data.historical_quotes.errors` (re-exportadas pelo
`__init__.py` da fonte):

- `InvalidFirstYear` / `InvalidLastYear`: erros de validação de intervalo
  temporal.
- `InvalidAssetsName`: alias de classe de ativo não é reconhecido.
- `EmptyAssetListError`: tentativa de processamento com lista de ativos
  inválida.
- `InvalidProcessingMode`: `processing_mode` fora de `{'fast', 'slow'}`.
- `InvalidOutputFilename`: tentativa de uso de nome de arquivo de saída inválido
  (vazio/somente espaços).
- `SecurityError` / `PathPermissionError` (de `macro_exceptions`): tentativa de
  escrita em path sensível (`/etc`, `/sys`, etc.) ou sem permissões suficientes
  — defesa em `FileSystemServiceB3` (`filesystem.py`).

## 🔧 Troubleshooting

> [!WARNING] **Erro: Arquivo não encontrado** Verifique se cada caminho absoluto
> em `documents_to_download` aponta para um arquivo COTAHIST existente; para
> obter essa configuração com segurança, use `CreateDocsToExtractUseCaseB3`.

> [!TIP] **Performance** Para grandes volumes de dados (todos os ativos de
> vários anos), prefira processar ano a ano ou utilizar máquinas com mais
> memória RAM se usar o modo `fast`.
