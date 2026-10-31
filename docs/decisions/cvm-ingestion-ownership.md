# ADR: ownership da ingestão de arquivos CVM

## Status

Accepted

## Contexto

Outras famílias CVM precisam reutilizar download, conversão e publicação sem
depender do catálogo de companhias abertas. Esses mecanismos conhecem contratos
CSV, ZIP, Parquet e metadados da CVM; as fundações globais atendem várias fontes.

## Decisão

- `brazil/cvm/ingestion/` é responsável pelos mecanismos reutilizáveis. Um contrato
  de imports impede dependência de `fundamental_stocks_data/`.
- `fundamental_stocks_data/` é responsável pelo catálogo, URLs, anos e destinos
  de empresas. A facade compõe `ingestion.http.CvmDownloadAdapter`; a extração
  usa `ingestion.extract.CvmParquetExtractor`, e o resultado pertence a
  `ingestion.models.DownloadResultCVM`.
- Configuração, segurança e publicação transacional usam os proprietários
  existentes em `core/` e `macro_infra/`.
- O inventário associa saídas à origem por `cvm.source-archive`, sem inferência
  pelo nome. O [guia de inventário](../user-guide/migration-cvm-exact-text.md#inventario-das-saidas)
  define substituição, preservação e bloqueio dos arquivos existentes.

## Alternativas consideradas

- Promover todo o pipeline ao escopo global espalharia contratos específicos da
  CVM pelas demais fontes.
- Manter os mecanismos sob empresas ou copiá-los para cada família preservaria
  acoplamento ou duplicação.
- Compartilhar dentro da CVM separa essas responsabilidades e mantém os
  proprietários canônicos, sem impor parsing ou schemas comuns à B3.

## Consequências

Novas famílias compatíveis usam os mecanismos sem consultar o catálogo de
empresas. O contrato `exact-text-v1`, os nomes de saída e as assinaturas públicas
permanecem. A integração com arquivos oficiais de outra família exige validar
seu formato e suas regras.

A extração automática verifica o inventário antes e depois do colaborador; a
transação verifica a extração direta antes da publicação. São três varreduras
no caminho padrão, com custo proporcional aos arquivos no destino. Um extrator
fornecido responde por suas escritas e transação; a checagem posterior não desfaz
efeitos arbitrários.

O lock `.cvm-write-lock` e o lock do publisher mantêm seus ciclos e limites de
concorrência. A realocação não amplia essas garantias.

## Migração e rollback

Consumidores internos usam os módulos canônicos de `ingestion/`, sem aliases ou
módulos de encaminhamento. A inferência por nomes presente em `develop` foi
retirada antes de chegar às releases. Destinos com dados não identificados exigem
preparação explícita conforme o guia de inventário.

Um rollback restaura implementação, imports e verificadores juntos, mantendo um
único proprietário do estado de escrita.

## Quando revisar

Revisar quando outra fonte precisar das mesmas operações com as mesmas garantias,
ou uma família CVM exigir outro dialeto, schema ou ciclo de publicação.
