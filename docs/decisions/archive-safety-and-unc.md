# Limites de ZIP e destinos UNC por allowlist

**Status:** Aceita
**Data:** 2026-08-31
**Escopo:** segurança compartilhada de arquivos e destinos fornecidos pelo
chamador

## Contexto

CVM e B3 consomem arquivos ZIP fornecidos por fontes externas. Streaming evita
`extractall()`, mas não limita por si só o custo de CPU, disco ou memória de um
arquivo com muitos membros, metadados enganosos ou expansão excessiva. As duas
fontes também recebem destinos fornecidos pelo chamador. Um bloqueio apenas de
alguns diretórios POSIX não protege raízes de drives Windows nem caminhos UNC.

## Decisão

`core/archive_safety.py` concentra a política reutilizável de ZIP. Antes de
CRC, parsing ou escrita, CVM e B3 validam tamanho compactado, quantidade de
membros, tamanhos descompactados individual e total, razão de compressão,
criptografia, nomes absolutos ou com `..`, links/tipos especiais, nomes de
saída duplicados após normalização case-insensitive e colisões em que um
arquivo é ancestral de outro membro. Cada componente também é validado contra
a semântica Win32: separadores ambíguos, ADS, caracteres inválidos, terminações
em ponto/espaço e dispositivos DOS reservados são rejeitados. Cada stream
descompactado é ainda contado durante a leitura; metadados falsos não podem
autorizar mais bytes que o limite.

Os limites pertencem à configuração global tipada:

| Variável | Padrão |
| --- | ---: |
| `DATAFINANCE_ARCHIVE_MAX_ARCHIVE_BYTES` | 2 GiB |
| `DATAFINANCE_ARCHIVE_MAX_MEMBERS` | 10.000 |
| `DATAFINANCE_ARCHIVE_MAX_MEMBER_UNCOMPRESSED_BYTES` | 2 GiB |
| `DATAFINANCE_ARCHIVE_MAX_TOTAL_UNCOMPRESSED_BYTES` | 8 GiB |
| `DATAFINANCE_ARCHIVE_MAX_COMPRESSION_RATIO` | 200,0 |

Os valores são positivos, têm tetos defensivos e são validados ao criar
`Settings`; o total permitido não pode ser menor que o limite de um membro.

`assert_path_not_sensitive()` continua sendo a única política compartilhada
de destino. Ela bloqueia `/`, raízes de todos os drives Windows, `Windows`,
`Program Files` e `Program Files (x86)` em qualquer drive, além de diretórios
POSIX sensíveis. UNC é negado por padrão. A única exceção é um caminho igual
ou descendente de uma raiz da lista JSON
`DATAFINANCE_PATH_SAFETY_ALLOWED_UNC_ROOTS`; shares administrativos terminados
em `$` permanecem proibidos mesmo nessa lista.

## Consequências

- As fontes preservam suas regras próprias de nome: CSV pertence à CVM e
  `COTAHIST` pertence à B3; somente os limites e a segurança genérica são
  compartilhados.
- Entradas rejeitadas falham antes de descompressão relevante ou de escrita.
- Os limites reduzem o risco de negação de serviço, mas um arquivo dentro dos
  tetos ainda pode consumir recursos até esses tetos.
- Esta é uma defesa de destinos fornecidos pelo chamador. Ela não afirma
  restringir um chamador que já possui os mesmos privilégios do processo.
- A biblioteca não carrega `.env` implicitamente. O chamador deve exportar as
  variáveis ou usar explicitamente `uv run --env-file ...` ao executar um
  processo local.
