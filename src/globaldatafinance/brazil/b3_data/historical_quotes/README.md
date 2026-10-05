# Cotações históricas B3

Este diretório é o proprietário da descoberta, validação e transformação de
COTAHIST. A API pública fica na facade `HistoricalQuotesB3` em `application/`.

## Responsabilidades

| Módulo ou pacote                                                    | Responsabilidade                                                                       |
| ------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| `catalog.py`                                                        | Catálogo anual compartilhado, validação integral, equivalência ZIP/TXT e anos ausentes |
| `source_validation/`                                                | Ordem dos registros, controles, contagens e fatos imutáveis por fonte                  |
| `layout.py`                                                         | Campos, posições e conversões do schema v2                                             |
| `cotahist_parser/`                                                  | Conversão exata de todos os campos antes da seleção de mercados                        |
| `assets.py`                                                         | Aliases e códigos TPMERC; `todos` preserva códigos numéricos desconhecidos             |
| `zip_reader.py`, `member_resolver.py`                               | Leitura limitada de ZIP/TXT e resolução segura do membro anual                         |
| `extraction_service/`                                               | Agendamento, workers, repetição transitória, merge e publicação transacional           |
| `parquet_writer/`                                                   | Schema Arrow, escrita limitada e verificação integral do artefato privado              |
| `source_evidence.py`, `integrity_report.py`                         | Evidências comuns ao footer e ao resultado público                                     |
| `row_digest.py`                                                     | Digest ordenado dos valores lógicos e ocorrências selecionadas                         |
| `client.py`, `models.py`                                            | Casos de uso e configuração preparada                                                  |
| `filesystem.py`, `input_validation.py`, `years.py`, `processing.py` | Validação de parâmetros, caminhos, anos e modo de processamento                        |

A extração padrão seleciona todos os mercados. Cada documento deve conter um
header `00`, ao menos uma cotação `01` válida e um trailer `99` consistente.
ZIP tem preferência somente quando ZIP e TXT do mesmo ano forem integralmente
válidos e seus conteúdos descompactados forem idênticos. Entradas conflitantes
falham antes da criação do destino.

Entradas externas usam `COTAHIST_A{YEAR}.ZIP` ou `COTAHIST_A{YEAR}.TXT`.
`DocsToExtractorB3` é um objeto de dados e não executa validação na construção
direta. `CreateDocsToExtractUseCaseB3` valida os parâmetros e prepara a
configuração; `documents_to_download` contém caminhos absolutos resolvidos.
`ações`, `etf` e `opções` são classes de ativos, selecionadas pelos aliases.

Os modos `fast` e `slow` mantêm limites de lote e concorrência distintos e a mesma
validação de integridade. A leitura completa do Parquet privado verifica schema,
metadata, contagens, proveniência, bytes originais e digests antes da publicação.
Falhas retornam contadores de saída zerados e preservam o resultado anterior.

Todo worker usa a conversão canônica e confere a releitura da fonte e o digest
ordenado, inclusive quando a fábrica retorna uma subclasse do parser. O caminho
alternativo que aceitava apenas `parse_line()` foi removido. Extensões internas
devem implementar o contrato completo de `CotahistParserB3`.

`iter_lines()`, `read_lines_from_zip()` e `ParquetWriterB3` continuam disponíveis
para seus consumidores existentes. A leitura textual deriva dos bytes originais;
a escrita usa as mesmas sessões Arrow e o schema atual. Essas interfaces não
mantêm um parser ou um engine produtivo alternativo.

Os arquivos de entrada devem permanecer inalterados durante a execução. A
reconferência final e a publicação executam no mesmo trabalhador, com um ponto
de cancelamento antes da decisão de publicar. A reconferência não bloqueia
alterações por processos externos. Os detalhes estão na referência da API.

## Contratos e validação

- [API B3](../../../../../docs/reference/b3-api.md)
- [Schema v2](../../../../../docs/reference/b3-schema-v2.md)
- [Guia de migração](../../../../../docs/user-guide/migration-pyarrow-integrity.md)
- [Testes e campanhas reais](../../../../../docs/dev-guide/testing.md)

Os testes espelham este proprietário em
`tests/brazil/b3_data/historical_quotes/`. O oracle independente em
`scripts/cotahist_oracle/` define suas próprias posições, conversões e tipos;
a campanha nativa `scripts/real_validation.py` compara cada ocorrência original
com o Parquet e verifica a paridade exata entre os modos.
