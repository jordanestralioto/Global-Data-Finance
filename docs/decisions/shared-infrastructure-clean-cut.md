# ADR: corte limpo da infraestrutura compartilhada

## Status

Accepted

## Contexto

- O repositório mantinha adapters genéricos de ZIP/CSV que já não eram donos
  de um contrato ativo, duplicava preparação de destinos em CVM e B3 e
  duplicava a reserva de arquivos temporários.
- Pandas permanecia como dependência de runtime somente para o caminho legado
  de leitura CSV, embora os pipelines produtivos CVM/B3 já fossem PyArrow.
- CVM e B3 possuem formatos, floors de ano, mensagens e ownership diferentes.
- A mudança é um breaking release deliberado. As fachadas raiz, schemas
  Parquet, nomes de saída e publicação transacional precisam permanecer.
- Atributos dominantes: correção de dados, segurança de paths, facilidade de
  mudança, rastreabilidade de falhas e baixo custo operacional.

## Decisão

Escolhemos extrair somente invariantes reais: normalização/preparação de
destinos em `core.utils.destination_paths` e reserva de temporários no mesmo
diretório em `macro_infra.temporary_files`. CVM e B3 continuam donos de sua
orquestração, validação de anos, formatos e mensagens.

`ExtractorAdapter`, `ReadFilesAdapter`, seus módulos e a dependência direta de
Pandas são removidos sem alias, warning, shim ou fallback. `DownloadTimeoutError`
substitui a classe customizada antiga. `B3Error` é uma base somente do domínio
B3; não será criada uma `GlobalDataFinanceError` ou outra base catch-all. Falhas
de filesystem na escrita staged CVM tornam-se `ParquetWriteError`, exceto
`ENOSPC`, que continua sendo `DiskFullError`.

Não há change OpenSpec: esta é uma decisão de release e de limpeza de contratos
já aceitos, sem um novo lifecycle de especificação compartilhada.

## Alternativas consideradas

- **Manter helpers locais e adapters legados:** rejeitada porque preserva
  divergência, uma dependência runtime desnecessária e uma superfície sem owner
  ativo.
- **Forçar CVM e B3 em um extrator/validador comum:** rejeitada porque mistura
  regras de fonte, floors de ano, diagnósticos e responsabilidades diferentes.
- **Extrair somente primitivas invariantes e fazer hard cut dos adapters:**
  escolhida porque reduz duplicação sem criar uma abstração de domínio e mantém
  a publicação no mesmo filesystem.

## Consequências

### Positivas

- Um único contrato interno para normalizar e preparar destinos com checagem de
  segurança antes de `mkdir` e revalidação após criação.
- Um único mecanismo de reserva temporária, com cleanup limitado ao arquivo
  criado pela própria chamada e sufixos preservados (`.part` e
  `.parquet.tmp`).
- Menos dependências e nenhuma instalação automática de Pandas.
- Captura B3 explícita sem contaminar a hierarquia global; erros de escrita CVM
  distinguem infraestrutura de conteúdo.

### Negativas e mitigação

- Consumidores dos adapters e do timeout antigo quebram imediatamente; o guia
  de migração fornece imports antes/depois e as alternativas source-owned.
- Consumidores que usam DataFrames precisam instalar Pandas; PyArrow é o leitor
  padrão documentado e os testes exercitam schemas/valores reais.
- Os helpers compartilhados tornam-se contratos internos entre owners; testes
  unitários diretos cobrem races, causas encadeadas, temporários e permissões.

## Nota de migração/rollback

A migração é uma troca única para a próxima versão major: substituir o timeout,
remover imports dos adapters e declarar Pandas no projeto consumidor quando
necessário. Não existe compatibilidade incremental por design. Desfazer a
decisão exige restaurar os módulos, testes, dependência e lockfile em conjunto;
não é permitido recuperar apenas um alias, porque isso recriaria um contrato
parcial e ambíguo.

## Revisit trigger

Revisar quando uma terceira fonte precisar de preparação de destino independente
de fonte ou de reserva de temporários irmãos com semântica diferente. Nesse
caso, avaliar um novo boundary source-owned; não ampliar os helpers atuais com
regras específicas de CVM ou B3.
