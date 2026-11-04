# Exemplos de uso

Para usar um exemplo, **abra o arquivo, mude os valores no bloco `SETTINGS`,
salve e execute o comando indicado abaixo**. Você pode fazer isso no editor de
texto que já usa. As opções que precisam ser alteradas estão juntas, perto do
início de cada arquivo.

| Arquivo                                                | O que faz                           | O que precisa                 |
| ------------------------------------------------------ | ----------------------------------- | ----------------------------- |
| [01_quickstart_cvm.py](01_quickstart_cvm.py)           | Baixa documentos financeiros da CVM | Internet                      |
| [02_quickstart_b3.py](02_quickstart_b3.py)             | Lê cotações dos mercados de ações   | Amostras incluídas no projeto |
| [03_advanced_options_b3.py](03_advanced_options_b3.py) | Lê também os mercados de opções     | Amostras incluídas no projeto |
| [04_yearly_b3.py](04_yearly_b3.py)                     | Salva cotações em uma pasta por ano | Amostras incluídas no projeto |

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

Você também pode executar como módulo, usando `-m` e pontos entre os nomes:

```bash
uv run --locked --no-sync python -m examples.01_quickstart_cvm
uv run --locked --no-sync python -m examples.02_quickstart_b3
uv run --locked --no-sync python -m examples.03_advanced_options_b3
uv run --locked --no-sync python -m examples.04_yearly_b3
```

Execute apenas o exemplo desejado. Com `-m`, use `examples.nome_do_exemplo`,
sem `/` e sem a extensão `.py`. Para usar o caminho `examples/arquivo.py`,
execute sem `-m`, como nos comandos abaixo.

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
| `ASSETS`              | Grupos de mercados B3                                       | `['ações']`, `['ações', 'opções']` ou `['todos']`                                                                    |
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

A biblioteca lê arquivos locais. O repositório inclui duas amostras sintéticas
pequenas, prontas para executar os exemplos após preparar o ambiente:

```text
cotahist_b3/
├── COTAHIST_A2022.ZIP
└── COTAHIST_A2023.ZIP
```

Cada amostra contém **21 cotações fictícias**: sete combinações de instrumento
e mercado em três datas. São usados 17, 18 e 19 de janeiro em 2022 e 16, 17 e
18 de janeiro em 2023. Todos os tickers, nomes, ISINs e preços das amostras são
demonstrativos; não representam negociações oficiais.

| Ticker    | Nome        | Instrumento / mercado                  |
| --------- | ----------- | -------------------------------------- |
| `ALFA4`   | ALFA        | Ação preferencial à vista (010)        |
| `BETA3`   | BETA        | Ação ordinária à vista (010)           |
| `INDX11`  | INDICE DEMO | ETF à vista (010)                      |
| `ALFA4F`  | ALFA        | Ação preferencial no fracionário (020) |
| `ALFAA30` | ALFA        | Opção de compra (070)                  |
| `ALFAM30` | ALFA        | Opção de venda (080)                   |
| `ALFA4`   | ALFA        | Ação no mercado a termo (030)          |

Os preços variam entre instrumentos, datas e anos. Cada cotação representa
quatro negócios com quantidades iguais; o volume corresponde ao preço médio
vezes a quantidade total. As opções têm preço de exercício e vencimento;
as ações e o ETF à vista não têm vencimento. Os ISINs distinguem os
instrumentos, enquanto `ALFA4`, `ALFA4F` e o termo de `ALFA4` compartilham o
identificador da mesma ação. As opções de anos diferentes têm ISINs diferentes.

Esses arquivos são gerados por
[`scripts/generate_example_cotahist.py`](../scripts/generate_example_cotahist.py);
edite o gerador e regenere os ZIPs para mudar as amostras.

Para usar bases reais, siga o [guia B3](../docs/user-guide/b3-docs.md), guarde
os arquivos em `cotahist_b3_local/` e ajuste `PATH_OF_DOCS` e os anos do
exemplo. Essa pasta é ignorada pelo Git. Também funciona com TXT descompactado;
preserve o nome oficial `COTAHIST_AYYYY.ZIP` ou `.TXT` e forneça cada ano pedido.

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
Com a amostra incluída e os valores padrão, são geradas **12 cotações**:
quatro instrumentos em três datas.

`ASSETS = ['ações']` seleciona os mercados à vista (010) e fracionário (020).
ETFs desses mercados também podem aparecer. Essa opção escolhe **mercados**;
ela não escolhe empresas por códigos como PETR4.

### Exemplo 03: mais mercados da B3

Use este arquivo para incluir opções. Ele funciona da mesma forma que o exemplo
02; a seleção inicial é `ASSETS = ['ações', 'opções']`. O alias `ações` inclui
os mercados 010 e 020, que também incluem ETFs. Adicionar o alias `etf`
selecionaria esses mesmos mercados.

O arquivo está configurado para **2022 a 2023**, com entradas locais em
`./cotahist_b3`. A pasta precisa conter os arquivos dos dois anos. Para
experimentar só 2023, mude os dois anos para `2023`. Se precisar mudar a pasta,
edite `PATH_OF_DOCS` como no exemplo 02.

Execute:

```bash
uv run --locked --no-sync python examples/03_advanced_options_b3.py
```

Com a configuração atual, o resultado é
`dados_b3/carteira_completa_2022_2023.parquet`. Com os dois anos em 2023, será
`dados_b3/carteira_completa_2023.parquet`. Para incluir todos os mercados em
qualquer exemplo B3, mude `ASSETS` para `['todos']`.
As amostras incluídas produzem **36 cotações** com a configuração padrão do
exemplo 03: seis instrumentos em três datas de cada ano. O mercado a termo
(030) das amostras é excluído por essa seleção. Com `ASSETS = ['todos']`, são
geradas **42 cotações**, incluindo o termo.

### Exemplo 04: salvar a B3 ano a ano

Este exemplo lê os COTAHIST locais e executa uma extração independente por ano,
salvando todas as cotações selecionadas daquele ano em um único Parquet dentro
da pasta correspondente. A configuração padrão usa as amostras de 2022 e 2023:

```bash
uv run --locked --no-sync python examples/04_yearly_b3.py
```

```text
dados_b3/cotacoes_acoes_por_ano/
├── 2022/
│   └── cotacoes_acoes_2022.parquet
└── 2023/
    └── cotacoes_acoes_2023.parquet
```

Cada amostra produz **12 cotações** com `ASSETS = ['ações']`, que seleciona os
mercados 010 e 020, incluindo ETFs desses mercados. O exemplo usa a API pública
para preservar o schema e gerar os metadados de integridade de cada ano.

Para gerar sua base de **2000 a 2026**, ajuste `INITIAL_YEAR = 2000`,
`LAST_YEAR = 2026`, `PATH_OF_DOCS` para a pasta dos COTAHIST originais e
`DESTINATION_PATH` para a pasta que conterá as subpastas anuais. A entrada são
os arquivos `COTAHIST_AYYYY.ZIP` ou `.TXT`; o Parquet consolidado não é necessário.

Para atualizar apenas **2026**, coloque a versão atualizada de
`COTAHIST_A2026.ZIP` ou `.TXT` na pasta de entrada e use:

```python
INITIAL_YEAR = 2026
LAST_YEAR = 2026
```

Mantenha a mesma pasta de destino, o nome inicial e a seleção de mercados.
A execução refaz e substitui `2026/cotacoes_acoes_2026.parquet`; os arquivos
dos outros anos não são alterados. Anos já existentes também são processados
quando incluídos no intervalo; o exemplo não ignora um ano apenas porque sua
pasta existe. A pasta de entrada precisa conter somente os anos solicitados.

Se um ano falhar, o exemplo para com um diagnóstico. As extrações anuais
anteriores que já terminaram permanecem disponíveis; ajuste o intervalo para
retomar a partir do ano que falhou.

## 3. Conferir o resultado

Ao terminar, cada exemplo mostra a pasta ou o arquivo gerado e a quantidade de
arquivos processados. Os exemplos B3 também mostram o número de cotações e
uma prévia das seis primeiras linhas, com data, ticker, mercado, nome, preço
de fechamento e ISIN. A prévia lê somente um pequeno lote do Parquet.
Se houver falha ou nenhum dado for produzido, o script exibe um diagnóstico
e encerra com erro.

O mesmo ticker pode aparecer em datas ou mercados diferentes. Compare
`data_pregao`, `ticker` e `tipo_mercado` em conjunto para entender essas linhas.
Nas amostras, essa combinação não se repete. O nome ALFA também aparece nas
opções porque elas se referem à mesma emissora; seus ISINs são diferentes dos
da ação.

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
exemplos. Para usar ou personalizar os exemplos, edite os quatro arquivos
numerados.

## Validação dos exemplos

Na pasta principal do projeto:

```bash
uv run --locked --no-sync pytest tests/examples
```

Para regenerar as duas amostras versionadas, ou conferir que correspondem ao
gerador sem alterá-las:

```bash
uv run --locked --no-sync python scripts/generate_example_cotahist.py
uv run --locked --no-sync python scripts/generate_example_cotahist.py --check
```

O gerador substitui somente os ZIPs de 2022 e 2023 em `cotahist_b3/`. Os ZIPs
têm timestamps fixos para evitar mudanças causadas pela data de geração.
Os testes também executam os scripts com as amostras incluídas, sem editar
suas configurações e sem depender de bases anuais locais.

Os testes usam ZIP, TXT, CSV e Parquet locais criados para a validação. O HTTP
da CVM é substituído por respostas locais, sem baixar dados reais.

Consulte os guias [CVM](../docs/user-guide/cvm-docs.md) e
[B3](../docs/user-guide/b3-docs.md) para os contratos completos.
