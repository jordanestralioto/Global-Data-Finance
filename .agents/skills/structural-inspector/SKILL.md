---
name: structural-inspector
description: >-
  Use para inspecionar arquivos, datasets ou formatos desconhecidos sem carregar
  tudo na memória. Ative com "que arquivo é esse?", "qual encoding?", "qual
  delimitador?", "descobre o schema", "CSV/JSONL/Parquet estranho?", "tem BOM?",
  "CRLF ou LF?" ou "por que esse parser falha?", ou quando a estrutura ainda não
  for confiável. Cobre byte sniffing, amostragem, schema e identificação de
  formato. Não use para otimizar queries Polars conhecidas, modelar bancos de
  dados ou validar regras de negócio.
---

# Structural Inspector

## O Princípio do Zero Memory Overhead

Na leitura inicial de um arquivo grande ou suspeito, **não o carregue com um leitor de alto nível (pandas, `json.load`)**: ele assume dados bem formados e põe tudo na memória. Comece pelos bytes. Use um parser só em streaming, sobre poucos registros, depois de conhecer encoding e delimitador.

### Tática: Byte-Sniffing (Linux CLI)

```bash
# 1. Identificar tipo real (independente de extensão)
file --mime dataset.csv

# 2. Descobrir codificação (Encoding) ou presença de BOM ("ef bb bf" = BOM UTF-8)
uchardet dataset.csv || file --mime-encoding dataset.csv
head -c 3 dataset.csv | od -An -tx1

# 3. Detectar quebras de linha misturadas (CRLF vs LF)
head -n 1000 dataset.csv | grep -U $'\r$' | wc -l

# 4. Amostrar dados ignorando tamanho (Stream). Em CSV com quebra de linha
#    entre aspas, cortar por linha pode partir um registro ao meio.
head -n 50 dataset.csv > sample_dataset.csv
```

______________________________________________________________________

## Inspeção de Dados Estruturados

### CSV / TSV

- **Campos por registro:** conte com um parser CSV em streaming, não com
  `awk -F','`, `cut` ou `wc -l`. Vírgula e quebra de linha dentro de aspas são
  CSV válido, e uma contagem por linha as trata como separadores: um arquivo
  correto parece quebrado.
  ```bash
  python3 - dataset.csv <<'EOF'
  import collections, csv, itertools, sys
  with open(sys.argv[1], newline='', encoding='utf-8', errors='replace') as f:
      rows = itertools.islice(csv.reader(f, delimiter=','), 1000)
      print(collections.Counter(len(row) for row in rows))
  EOF
  ```
  Ajuste `encoding` e `delimiter` ao que o byte sniffing mostrou. Uma única
  contagem indica estrutura consistente; mais de uma aponta os registros a
  conferir antes de declarar o arquivo corrompido.
- **Separadores anômalos:** o que quebra um parser é aspas desbalanceadas, o
  delimitador dentro de um campo sem aspas ou a mistura de delimitadores, não
  vírgulas entre aspas.

### JSONL (JSON Lines)

- Em JSONL, cada linha é um JSON válido.
- **Validador de linhas** (lista todas as inválidas, sem parar na primeira):
  ```bash
  head -n 1000 data.jsonl | python3 -c 'import json, sys
  for number, line in enumerate(sys.stdin.buffer, 1):
      try:
          json.loads(line)
      except ValueError as error:
          print(number, error)'
  ```
  Saída vazia significa que todas as linhas amostradas são JSON válido.
- **Inspeção de Schema Inferida:**
  Pegue as chaves da primeira linha:
  ```bash
  head -n 1 data.jsonl | jq 'keys'
  ```

### Parquet

- Parquet contém os próprios metadados e schema armazenados no final do arquivo.
- **Extrair Schema Rápido (Python PyArrow):**
  ```python
  import pyarrow.parquet as pq

  schema = pq.read_schema('data.parquet')
  print(schema)
  ```

______________________________________________________________________

## Detecção de Oportunidades de Otimização (Recon)

1. **Campos muito longos ou repetitivos em JSON:** Podem ser melhor compactados mudando o schema para array posicional ou usar Parquet Dictionary Encoding se armazenados em banco colunar.
2. **Tipos mais largos que o necessário:** antes de sugerir inteiro para uma coluna `float64`, confirme na coluna inteira, não só na amostra, que não há casas decimais e que mínimo e máximo cabem no tipo. O máximo sozinho não basta: preços como `38.27` cabem em `Int16` e perderiam os centavos. `float32` guarda cerca de 7 dígitos significativos; não o sugira para valores monetários.
3. **Strings Escapadas Duplamente:** Anomalias em APIs REST antigas (ex: JSON serializado como string dentro de JSON).
   ```bash
   # Procurar por escapamento excessivo
   grep -o '\\\\"' data.jsonl | head -n 1
   ```

______________________________________________________________________

## Checklist de Decisão de Reconhecimento

- [ ] A codificação exata foi verificada (UTF-8, Latin-1, com ou sem BOM)?
- [ ] O separador de quebra de linha está consistente (`\n` vs `\r\n`)?
- [ ] Em CSV, a contagem de campos por registro, feita por um parser CSV, é idêntica na amostra?
- [ ] Foram encontradas strings duplamente escapadas ou JSON aninhado em strings?
- [ ] Em datasets >1GB, a inspeção inicial usou leitura em streaming (`head`, parser sobre poucos registros) em vez de carregar tudo?

## Procedimento

1. Comece com amostragem barata: bytes iniciais, cabeçalho, delimitador, BOM, encoding e consistência básica de linhas.
2. Só escolha parser ou engine depois de inferir o formato provável; o objetivo é evitar carregar um arquivo errado do jeito errado.
3. Em datasets grandes, mantenha a inspeção em modo streaming até saber que uma leitura completa é segura e necessária.
4. Registre o formato detectado, ambiguidades restantes e a próxima ferramenta recomendada para processamento real.

## Scripts

- `scripts/inspector.py --path <arquivo>`: relatório JSON de schema de CSV,
  Parquet ou Excel. Requer `polars` no ambiente; sem ele, sai com código 2 e
  diz o que instalar. Nesse caso, use os comandos acima. As estatísticas vêm de
  uma amostra (o arquivo inteiro até 2.000 linhas; acima disso, as 1.000
  primeiras e as 1.000 últimas), indicada em `sample_rows` e
  `source_is_sample`. Sugestões `CHECK` valem só para a amostra: confirme na
  coluna inteira antes de converter tipos. Sai com código 1 quando o relatório
  traz `error`.

## Exemplos

### Caso positivo

**Entrada:** Usuário entrega arquivo/dataset desconhecido, grande ou suspeito de encoding/formato.
**Saída esperada:** Fazer byte-sniffing, amostragem streaming e identificar schema/otimização sem carregar tudo em memória.

### Caso negativo

**Entrada:** Usuário pede interpretar regra de negócio no código.
**Por quê não:** Não é inspeção estrutural de arquivo/dados.
