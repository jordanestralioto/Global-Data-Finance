# Global-Data-Finance

Biblioteca Python para obter documentos regulatórios da CVM e converter
cotações históricas da B3 em Parquet. Requer Python `>=3.12,<4.0`.

| Fonte | Entrada | Resultado |
| --- | --- | --- |
| CVM | Download dos documentos selecionados | ZIP original e conversão opcional para Parquet |
| B3 | Arquivos anuais fornecidos pelo usuário | Parquet consolidado e relatório de integridade |

O extrator B3 aceita ZIP ou TXT locais: `COTAHIST_A{YYYY}.ZIP` e
`COTAHIST_A{YYYY}.TXT`. Os arquivos precisam existir antes da extração.

## Usar a biblioteca

```bash
python -m pip install globaldatafinance
```

Comece pelo [início rápido](user-guide/quickstart.md): um download CVM e uma
extração B3, com conferência do resultado.

| Preciso de… | Página |
| --- | --- |
| Preparar o ambiente | [Instalação](user-guide/installation.md) |
| Escolher documentos e anos | [Guia CVM](user-guide/cvm-docs.md) |
| Preparar COTAHIST e filtrar mercados | [Guia B3](user-guide/b3-docs.md) |
| Executar exemplos ou resolver uma dúvida | [Exemplos](user-guide/examples.md) · [FAQ](user-guide/faq.md) |

## Desenvolver no projeto

Siga [como contribuir](dev-guide/contributing.md) para preparar o ambiente e
validar uma mudança. A [arquitetura](dev-guide/architecture.md) mostra onde cada
responsabilidade fica; o [guia de testes](dev-guide/testing.md) explica os
comandos e a classificação dos testes.

## Consultar detalhes

Use a [referência da API](dev-guide/api-reference.md) para assinaturas,
resultados, schemas e exceções. Configuração, operação e migrações estão
agrupadas na referência; benchmarks, campanhas externas e decisões ficam na
área de manutenção do guia do desenvolvedor.
