# Portable Triage Contract

## Executar por fronteira de banco

O helper usa apenas a biblioteca padrão do Python. Não importa o harness, ORM
ou código do consumidor, não instala dependências e não abre conexão com banco.
Use o Python disponível compatível com o harness. Caminhos relativos são do
diretório atual do consumidor, independentemente de onde o helper foi instalado.

```bash
python .agents/skills/database-design/scripts/check_schema.py "db/schema.sql"
python .agents/skills/database-design/scripts/check_schema.py prisma/schema
python .agents/skills/database-design/scripts/check_schema.py db/schema db/indexes --output summary
python .agents/skills/database-design/scripts/check_schema.py . --include 'custom-ddl/*.sql' --exclude 'generated/*'
```

Informe arquivos diretamente para convenções incomuns. `--include` adiciona
candidatos às convenções padrão; `--exclude` remove caminhos. Globs são relativos
a cada diretório de entrada; em um arquivo explícito, o exclude usa seu basename.
Entradas repetidas são deduplicadas. Dependências/builds conhecidos e projeções
de ferramentas (`.agents`, `.claude`, `.codex`, `.opencode`) são podados na
descoberta de diretórios; diretórios ligados por symlink não são percorridos.

O padrão inspeciona até 500 arquivos e 2.000.000 bytes por arquivo. Ajuste
`--max-files` e `--max-bytes` explicitamente se necessário; limites atingidos
mantêm a cobertura incompleta, sem truncar SQL e fingir análise integral.

## O que é interpretado

- SQL: tabelas explícitas, colunas na mesma linha ou em várias linhas, tipos com
  parênteses, PK/UNIQUE/FK inline e de tabela, índices simples e alguns comandos
  ALTER/DROP/rename/obrigatoriedade. Modificadores `IF NOT EXISTS` e
  `CREATE INDEX CONCURRENTLY` são reconhecidos. Comentários, identificadores
  citados, strings e dollar quotes são separados de comandos reais.
- Em `ALTER TABLE`, `DROP PRIMARY KEY`, `DROP FOREIGN KEY`, `DROP CHECK` e
  `DROP CONSTRAINT` geram advisory de integridade; `DROP INDEX`/`DROP KEY`, de
  índice. Remoção de coluna continua HIGH. A severidade expressa o tipo da
  operação observada, não sua segurança no banco aplicado.
- Prisma: models, `@id`, `@@id`, `@unique`, `@@unique`, `@@index` e campos reais
  de `@relation(fields: [...])`, inclusive atributos em várias linhas. Um nome
  terminado em `id` não cria uma relação por inferência.
- Código de outras linguagens: inventário por convenções de schemas, models e
  migrations, ou por caminhos/globs explícitos. A análise semântica fica
  pendente para a ferramenta nativa ou para revisão contextual do agente.

Expressões de índice, tabelas derivadas/particionadas, rotinas, views e sintaxe
fora do subconjunto geram indicação de análise não verificada. Metadata Prisma
não substitui composição/validação nativa. O helper não valida todo SQL ou toda
regra do provider, mesmo quando interpreta a declaração.

Índices SQL em arquivos selecionados podem fornecer evidência para uma tabela
com nome explícito correspondente. Definições repetidas da mesma tabela tornam
essa combinação ambígua: a execução fica incompleta e pede separar fronteiras
ou consultar o estado aplicado. Não use uma árvore inteira de vários bancos
como se fosse um catálogo único. A ordem/história aplicada das migrations não
é reconstruída; índices implícitos e search paths não são inferidos.

PK/UNIQUE e índices simples só fornecem evidência de FK quando o prefixo atende
suas colunas. Índice parcial não é tratado como cobertura universal da relação.
A ausência dessa evidência é advisory dependente do workload, não uma exigência
automática de criar índice. Nomes de campos geram apenas avisos MEDIUM.

## Resultado e códigos de saída

O padrão é um único JSON em stdout, com `schema_version: 1`. `--output summary`
gera texto legível com limites e itens não verificados. Os principais campos:

| Campo                                               | Significado                                                                                    |
| --------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `files_found` / `files_inspected` / `files_omitted` | Descobertos, incluídos na inspeção e omitidos pelo limite                                      |
| `units_checked`                                     | Declarações de entidade, índice ou operação reconhecidas; não é quantidade de arquivos         |
| `coverage`                                          | Contagem por `complete`, `partial`, `unsupported` ou `error`                                   |
| `files`                                             | Caminho, formato, cobertura, unidades, statements, achados, pendências e erros por arquivo     |
| `findings_by_severity`                              | Contagem de achados; HIGH corresponde a operação destrutiva observada, não a substring de nome |
| `limitations`                                       | Garantias fora da triagem, preservadas mesmo em execução completa                              |
| `passed`                                            | Verdadeiro somente para código 0; não é aprovação do banco ou rollout                          |

| Exit | `status`           | Interpretação                                                                                        |
| ---- | ------------------ | ---------------------------------------------------------------------------------------------------- |
| 0    | `complete`         | Unidades suportadas interpretadas, sem HIGH; pode conter advisories MEDIUM                           |
| 1    | `findings`         | Cobertura completa da triagem e operação de risco HIGH observada                                     |
| 2    | `inspection-error` | Alvo ausente, leitura/encoding ou descoberta falhou; argumentos inválidos também usam 2 via argparse |
| 3    | `incomplete`       | Zero unidades, formato/sintaxe não cobertos, limite ou fronteira ambígua                             |

Erros de inspeção têm prioridade, depois cobertura incompleta, depois HIGH.
Achados já observados permanecem no JSON mesmo quando o status final é
incompleto. Não converta códigos 2/3 em sucesso nem descarte os achados de uma
execução parcial.

## Evidência complementar

O resultado não prova histórico aplicado, validação nativa, autorização/RLS,
corretude concorrente, performance, duração de locks ou segurança de rollout.
Complete a análise com os acessos, ferramentas e testes relevantes da tarefa.
Um helper que inventaria modelos Java/C# e retorna 3 está expondo um limite;
isso não impede o agente de continuar a revisão contextual desses modelos.
