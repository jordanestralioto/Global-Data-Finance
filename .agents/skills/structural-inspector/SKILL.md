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

Quando inspecionar arquivos grandes de dados de forma investigativa, **não use abstrações da linguagem (ex: pandas, json)** para leitura inicial. Abstrações de parser assumem dados bem formados e explodem a memória.

### Tática: Byte-Sniffing (Linux CLI)

```bash
# 1. Identificar tipo real (independente de extensão)
file -i dataset.csv

# 2. Descobrir codificação (Encoding) ou presença de BOM
uchardet dataset.csv || file -I dataset.csv

# 3. Detectar quebras de linha misturadas (CRLF vs LF)
head -n 1000 dataset.csv | grep -U $'\r$' | wc -l

# 4. Amostrar dados ignorando tamanho (Stream)
head -n 50 dataset.csv > sample_dataset.csv
```

______________________________________________________________________

## Inspeção de Dados Estruturados

### CSV / TSV

- **Verificação Rápida de Colunas:**
  ```bash
  head -n 1 dataset.csv | awk -F',' '{print NF}'
  # Ver se linhas subsequentes quebram o padrão
  head -n 100 dataset.csv | awk -F',' '{print NF}' | sort | uniq -c
  ```
- **Separadores Anômalos:** Vírgulas dentro de campos ou quebras de linha mal escapadas em strings quebram parsers.

### JSONL (JSON Lines)

- Em JSONL, cada linha é um JSON válido.
- **Validador Rápido de Quebras (sem falhar por 1 erro):**
  ```bash
  head -n 1000 data.jsonl | jq -c . > /dev/null
  ```
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
2. **Tipos Amplos Incorretos:** Detectar `float64` onde poderia ser `float32` ou int. Extraia uma coluna e confira o valor máximo.
3. **Strings Escapadas Duplamente:** Anomalias em APIs REST antigas (ex: JSON serializado como string dentro de JSON).
   ```bash
   # Procurar por escapamento excessivo
   grep -o '\\\\"' data.jsonl | head -n 1
   ```

______________________________________________________________________

## Checklist de Decisão de Reconhecimento

- [ ] A codificação exata foi verificada (UTF-8, Latin-1, com ou sem BOM)?
- [ ] O separador de quebra de linha está consistente (`\n` vs `\r\n`)?
- [ ] Em CSV, a contagem de colunas por linha é absolutamente idêntica na amostra?
- [ ] Foram encontradas strings duplamente escapadas ou JSON aninhado em strings?
- [ ] Em datasets >1GB, a inspeção inicial usou stream (`head`, `awk`) em vez de carregar tudo?

## Procedimento

1. Comece com amostragem barata: bytes iniciais, cabeçalho, delimitador, BOM, encoding e consistência básica de linhas.
2. Só escolha parser ou engine depois de inferir o formato provável; o objetivo é evitar carregar um arquivo errado do jeito errado.
3. Em datasets grandes, mantenha a inspeção em modo streaming até saber que uma leitura completa é segura e necessária.
4. Registre o formato detectado, ambiguidades restantes e a próxima ferramenta recomendada para processamento real.

## Scripts

- `scripts/inspector.py`: faz inspeção estrutural streaming/byte-level de arquivos.

## Exemplos

### Caso positivo

**Entrada:** Usuário entrega arquivo/dataset desconhecido, grande ou suspeito de encoding/formato.
**Saída esperada:** Fazer byte-sniffing, amostragem streaming e identificar schema/otimização sem carregar tudo em memória.

### Caso negativo

**Entrada:** Usuário pede interpretar regra de negócio no código.
**Por quê não:** Não é inspeção estrutural de arquivo/dados.

## Evals de trigger

Deve acionar:

- "identifica encoding e schema desse CSV enorme"
- "inspeciona parquet sem carregar tudo"
- "esse JSONL tem BOM ou quebra de linha CRLF?"
- "por que o parser falhou ao ler esse arquivo binário?"
- "descobre o delimitador e encoding desse arquivo"

Não deve acionar:

- "interpreta regra de negócio"
- "redesenha UI"
- "otimiza query lenta no Postgres"
- "escreve teste unitário para o parser"
