# Exemplos de uso

Para usar um exemplo, **abra o arquivo, mude os valores no bloco `SETTINGS`,
salve e execute o comando indicado abaixo**. Você pode fazer isso no editor de
texto que já usa. As opções que precisam ser alteradas estão juntas, perto do
início de cada arquivo.

| Arquivo                                                | O que faz                           | O que precisa                   |
| ------------------------------------------------------ | ----------------------------------- | ------------------------------- |
| [01_quickstart_cvm.py](01_quickstart_cvm.py)           | Baixa documentos financeiros da CVM | Internet                        |
| [02_quickstart_b3.py](02_quickstart_b3.py)             | Lê cotações dos mercados de ações   | Arquivos COTAHIST no computador |
| [03_advanced_options_b3.py](03_advanced_options_b3.py) | Lê também os mercados de opções     | Arquivos COTAHIST no computador |

## 1. Preparar o ambiente uma vez

Você precisa de Python `>=3.12,<4.0` e `uv`. Se ainda não os instalou, siga o
[guia de instalação](../docs/user-guide/installation.md).

Abra o terminal na **pasta principal deste projeto**, onde está o arquivo
`pyproject.toml`, e execute:

```bash
uv sync --locked --all-extras --dev
```

Use essa mesma pasta para executar os exemplos. Um caminho como `./dados_b3`
significa a pasta `dados_b3` dentro dela. A biblioteca cria a pasta de saída
quando necessário.

## 2. Escolher o que processar

As variáveis têm nomes em inglês, iguais aos usados nos arquivos. Use a tabela
para saber qual valor mudar:

| Variável              | Significado                                                 | Como preencher                                                                                                       |
| --------------------- | ----------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `INITIAL_YEAR`        | Primeiro ano                                                | Número sem aspas, como `2023`                                                                                        |
| `LAST_YEAR`           | Último ano, incluído no processamento                       | Use o mesmo ano inicial para processar só um ano                                                                     |
| `DESTINATION_PATH`    | Pasta onde o resultado será salvo                           | Caminho entre aspas, como `'./meus_dados'`                                                                           |
| `DOCUMENTS`           | Tipos de documentos CVM, no exemplo 01                      | `['DFP']` para demonstrações anuais; `['DFP', 'ITR']` para incluir trimestrais; `[]` para todos os tipos disponíveis |
| `AUTOMATIC_EXTRACTOR` | Converter documentos CVM em Parquet                         | `True` converte; `False` apenas baixa os ZIPs                                                                        |
| `PATH_OF_DOCS`        | Pasta que contém os arquivos B3                             | Caminho da pasta entre aspas, sem o nome do ZIP ou TXT                                                               |
| `ASSETS`              | Grupos de mercados B3                                       | `['ações']`, `['ações', 'etf', 'opções']` ou `['todos']`                                                             |
| `OUTPUT_NAME`         | Nome inicial do arquivo B3                                  | Texto sem pasta, extensão ou ano, como `'minhas_cotacoes'`                                                           |
| `PROCESSING_MODE`     | Modo de processamento B3                                    | `'fast'` para maior velocidade; `'slow'` para usar menos memória                                                     |
| `VERBOSE`             | Mostrar também os mercados, o modo e o tempo da extração B3 | `True` mostra; `False` mantém o resumo básico                                                                        |

Os exemplos B3 mostram barras de progresso por arquivo durante a validação e
o processamento, com `VERBOSE = True` ou `False`. Essa variável controla
somente os detalhes adicionais do resumo ao final. Após a barra de
processamento, a biblioteca ainda consolida e verifica o Parquet antes de
informar que a extração terminou.

Mude somente o valor **à direita do sinal `=`**. Mantenha as aspas nos textos,
os colchetes nas listas e as vírgulas entre os itens. `True` e `False` são
escritos sem aspas, com a primeira letra maiúscula. Depois de editar, **salve o
arquivo** antes de executá-lo.

### Exemplo 01: documentos da CVM

Para começar apenas com as demonstrações anuais de 2023, deixe o bloco assim:

```python
INITIAL_YEAR = 2023
LAST_YEAR = 2023
DESTINATION_PATH = './dados_cvm'
DOCUMENTS = ['DFP']
AUTOMATIC_EXTRACTOR = True
```

Execute:

```bash
uv run --locked --no-sync python examples/01_quickstart_cvm.py
```

Os arquivos serão salvos em `dados_cvm`. Parquet é o formato de dados gerado
pela conversão; os ZIPs originais também são preservados. Os documentos reúnem
várias empresas, e o download pode levar alguns minutos.

O arquivo está configurado para **2010 a 2026**, com `DOCUMENTS = []`
para todos os tipos. Para uma primeira execução menor, use o bloco acima.

### Exemplo 02: cotações da B3

A biblioteca lê arquivos que já estão no seu computador. Para obter a entrada,
siga o [guia B3](../docs/user-guide/b3-docs.md). Para processar 2023, organize
a pasta assim:

```text
cotahist_b3/
└── COTAHIST_A2023.ZIP
```

Também funciona com `COTAHIST_A2023.TXT`. Preserve o nome oficial; cada ano
solicitado precisa ter seu arquivo na pasta. Os exemplos não incluem esses
arquivos nem fazem o download deles.

O exemplo 02 já está configurado para 2023. Se a entrada estiver em outra
pasta, substitua a linha `PATH_OF_DOCS` por algo como:

```text
PATH_OF_DOCS = '/home/usuario/Minha pasta/COTAHIST'
```

As aspas também permitem caminhos com espaços. Execute:

```bash
uv run --locked --no-sync python examples/02_quickstart_b3.py
```

O resultado padrão é `dados_b3/cotacoes_acoes_2023.parquet`. Para processar
2022 e 2023, mude `INITIAL_YEAR` para `2022` e `LAST_YEAR` para `2023`. O nome
passa automaticamente a ser `cotacoes_acoes_2022_2023.parquet`.

`ASSETS = ['ações']` seleciona os mercados à vista (010) e fracionário (020).
ETFs desses mercados também podem aparecer. Essa opção escolhe **mercados**;
ela não escolhe empresas por códigos como PETR4.

### Exemplo 03: mais mercados da B3

Use este arquivo para incluir opções. Ele funciona da mesma forma que o exemplo
02; a seleção inicial é `ASSETS = ['ações', 'etf', 'opções']`.

O arquivo está configurado para **2010 a 2026** e o caminho local já
configurado em `PATH_OF_DOCS`. Para experimentar só 2023, mude os dois anos
para `2023`. Se precisar mudar a pasta, substitua todo o trecho de
`PATH_OF_DOCS = (` até o `)` por uma única linha como a mostrada no exemplo 02.

Execute:

```bash
uv run --locked --no-sync python examples/03_advanced_options_b3.py
```

Com a configuração atual, o resultado é
`dados_b3/carteira_completa_2010_2026.parquet`. Com os dois anos em 2023, será
`dados_b3/carteira_completa_2023.parquet`. Para incluir todos os mercados em
qualquer exemplo B3, mude `ASSETS` para `['todos']`.

## 3. Conferir o resultado

Ao terminar, cada exemplo mostra a pasta ou o arquivo gerado e a quantidade de
arquivos processados. Os exemplos B3 também mostram o número de cotações.
Se houver falha ou nenhum dado for produzido, o script exibe um diagnóstico
e encerra com erro.

Para ver cinco cotações do exemplo 02, abra o Python pelo terminal:

```bash
uv run --locked --no-sync python
```

Cole o código abaixo. PyArrow já está instalado com a biblioteca:

```python
import pyarrow.parquet as pq

parquet = pq.ParquetFile('./dados_b3/cotacoes_acoes_2023.parquet')
print(f'Records: {parquet.metadata.num_rows}')
for batch in parquet.iter_batches(
    batch_size=5,
    columns=['data_pregao', 'ticker', 'preco_fechamento'],
):
    print(batch.to_pydict())
    break
```

Se você mudou a pasta, o nome ou os anos, ajuste o caminho entre aspas para
corresponder ao arquivo gerado. Esse código lê uma pequena amostra, sem
carregar todas as cotações na memória.

## Se aparecer um erro

- **Biblioteca não encontrada:** execute a preparação e use `uv run` como nos
  comandos acima.
- **COTAHIST não encontrado ou ano indisponível:** confira `PATH_OF_DOCS`, os
  nomes `COTAHIST_AYYYY.ZIP` ou `.TXT` e se há um arquivo para cada ano.
- **Nenhuma cotação selecionada:** confira `ASSETS` e se os mercados escolhidos
  existem na entrada.
- **Falha no download CVM:** confira a conexão e leia quais documentos falharam
  no diagnóstico antes de tentar novamente.
- **Erro após editar:** confira aspas, colchetes, vírgulas e se o ano final é
  maior ou igual ao inicial.
- **Mensagem pedindo para editar `SETTINGS`:** retire as opções extras do
  comando, altere os valores no arquivo, salve e execute novamente.

O arquivo `support.py` reúne a conferência dos resultados e as mensagens dos
exemplos. Para usar ou personalizar os exemplos, edite os três arquivos
numerados.

## Validação dos exemplos

Na pasta principal do projeto:

```bash
uv run --locked --no-sync pytest tests/examples
```

Os testes usam ZIP, TXT, CSV e Parquet locais criados para a validação. O HTTP
da CVM é substituído por respostas locais, sem baixar dados reais.

Consulte os guias [CVM](../docs/user-guide/cvm-docs.md) e
[B3](../docs/user-guide/b3-docs.md) para os contratos completos.
