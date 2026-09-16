# Cutover de ingestão PyArrow e integridade transacional

**Status:** Aceita
**Data:** 2026-09-10
**Escopo:** extração CVM e B3, publicação de Parquet e imports de runtime
**Decisões:** Q1, Q2, Q3, Q4

## Contexto

O pacote carregava engines de ingestão durante import globaldatafinance,
inclusive para consumidores que apenas consultavam a API. O caminho CVM inferia
tipos por chunk e podia receber um decimal depois de ter fixado uma coluna como
inteira. O caminho B3 retinha grandes buffers de dicionários, reescrevia
Parquet durante append e aceitava alguns campos financeiros inválidos com
defaults silenciosos.

O commit CVM existente reduz a chance de um lote parcialmente publicado, mas
não preserva um manifest durável nem recupera automaticamente uma interrupção
entre backups e substituições. Isso compromete integridade e recuperação de
artefatos financeiros.

## Decisão

### Q1 — Pipelines PyArrow por fonte

Os pipelines produtivos CVM e B3 permanecem independentes e usam PyArrow para
leitura, conversão e escrita de Parquet. CVM preserva seu dialeto CSV
QUOTE_NONE; B3 usa parser posicional estrito. As fontes não compartilham
inferência, parsing, schema financeiro nem regras de filtro.

Foi rejeitado manter apenas imports lazy sobre os pipelines atuais, pois isso
não corrige a inferência local CVM, os buffers B3 ou o parsing permissivo.
Também foi rejeitado um framework genérico único: as fontes têm formatos,
lifecycle e diagnósticos de ownership distinto.

### Q2 — Imports e dependências de runtime

Polars será removido de runtime, lockfile, testes e scripts. PyArrow será o
único engine produtivo e será importado somente no primeiro caminho operacional
que precisa dele. Pandas continua obrigatório apenas pelo contrato legado de
ReadFilesAdapter, com import local nos métodos leitores.

Fachadas e arquivos __init__.py públicos permanecem leves. Construir uma
fachada, consultar assets/years B3 ou baixar CVM sem extração não pode carregar
pandas, NumPy, PyArrow ou Polars. Os três exports raiz e as assinaturas públicas
permanecem inalterados.

### Q3 — Publicação recuperável e failure-atomic

A infraestrutura interna macro_infra/transactional_publication/ fornece
staging no mesmo filesystem, manifest JSON durável, lock de diretório, backup
por hardlink ou cópia, rollback e recuperação na próxima chamada. Ela conhece
somente artefatos e paths; não conhece campos, schemas, filtros ou formatos das
fontes.

O manifest registra OPEN, VALIDATED, BACKUPS_READY, PUBLISHING, COMMITTED,
CLEANUP_PENDING, ROLLING_BACK e ROLLED_BACK. Todo path do manifest deve ficar
abaixo do destino ou staging. Escrita concorrente no mesmo destino é rejeitada;
um lock de outro host ou processo vivo nunca é removido apenas por idade.

O contrato é commit em lote recuperável e failure-atomic. Não há visibilidade
instantaneamente atômica para leitores concorrentes de múltiplos Parquets CVM,
porque múltiplos nomes não podem ser substituídos em uma única operação.

### Q4 — Regras de integridade por fonte

CVM faz uma passagem global de validação/inferência em texto e uma segunda
passagem com schema explícito. Linhas curtas são completadas somente no final;
linhas excedentes, cabeçalhos ausentes e estruturas ambíguas falham sem
publicar. CSV apenas com cabeçalho produz Parquet vazio com campos null, ordem
do cabeçalho e sem metadata pandas.

B3 aceita somente registros vazios, 00, 99 e registros 01 de exatamente 245
caracteres. Registros selecionados por TPMERC devem ter datas, textos, inteiros
e decimais válidos; valores inválidos nunca viram zero, string vazia ou nulo.
Registros fora do filtro são contados, mas não persistidos. Fontes válidas
integralmente filtradas publicam Parquet vazio com schema B3 explícito.

## Decisões de remediação da revisão

As seguintes decisões fecham os contratos encontrados na revisão de
implementação:

- `Settings.archive` é o único namespace canônico para limites de ZIP;
  `Settings.archive_safety` não é alias compatível. `infos=None` significa que
  a validação deve consultar o diretório central; uma lista fornecida, inclusive
  `[]`, é uma seleção já validada e deve ser respeitada literalmente.
- O logger `globaldatafinance` permanece isolado da hierarquia da aplicação
  desde o import, com `NullHandler` e `propagate=False`. `setup_logging()` só
  instala handlers gerenciados depois de construir todos os candidatos; uma
  falha de preparação ou troca restaura nível, propagação e handlers anteriores
  sem tocar em handlers externos. `LoggingSettings` é estrito e não aceita o
  campo removido `structured` nem variáveis `DATAFIN_LOG_*` desconhecidas.
  Destinos de arquivo passam pela política de segurança de caminhos antes de
  qualquer criação; o formatter redige
  parâmetros e campos de contexto sensíveis conhecidos, mas consumidores
  continuam proibidos de enviar segredos ao logging.
- A inferência CVM mantém inteiros assinados anuláveis como `int64`; não usa
  `float64` apenas porque a coluna contém nulos. O dialeto `QUOTE_NONE` também
  preserva uma linha física vazia de CSV de uma coluna como nulo lógico.
- O corte B3 remove o writer da dependência de estado do service e deixa o
  fechamento apenas na session concreta. A session tem estados explícitos
  `NEW`, `OPEN` e `CLOSED`; uma falha de fechamento é terminal, e o marcador
  interno de nulo nunca é aceito como dado literal de entrada.
- `ResourceMonitor` continua singleton deliberado, enquanto o cache de
  imports Arrow permanece lazy e privado ao caminho operacional que precisa
  dele. Essas escolhas não são atalhos de compatibilidade nem caminhos
  alternativos de ingestão.

## Consequências

- A release é major: parser B3 estrito, remoção de Polars e remoção do caminho
  CSV interno legado podem exigir migração de consumidores.
- CVM pode reabrir uma fonte em múltiplas passagens e criar spool UTF-8
  transacional para CP1252 ou Latin-1.
- A publicação passa a exigir staging, manifest, backup, lock e fsync quando a
  plataforma oferecer suporte.
- Fast e slow B3 preservam equivalência lógica, embora usem limites diferentes
  de memória e concorrência.
- ZIPs e TXTs de entrada nunca são apagados em falha; somente derivados da
  transação podem ser limpos.

## Não objetivos

- Não alterar exports públicos raiz, assinaturas, defaults, nomes de saída,
  schemas lógicos ou o formato Parquet.
- Não adicionar serviço, fila, processo externo, framework web ou feature flag.
- Não suportar CSV RFC quoted/multiline junto com QUOTE_NONE neste cutover.
- Não manter um pipeline produtivo pandas/Polars de contingência.
- Não tornar o corpus anual COTAHIST obrigatório na CI sem fixture licenciada.
- Não prometer isolamento serializável para leitores concorrentes de lote CVM.
