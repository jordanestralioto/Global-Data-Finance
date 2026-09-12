# FAQ - Perguntas Frequentes

Respostas para as perguntas mais comuns sobre o Global-Data-Finance.

______________________________________________________________________

## Instalação e Configuração

### Como instalar o Global-Data-Finance?

```bash
pip install globaldatafinance
```

Veja o [guia completo de instalação](installation.md) para mais detalhes.

### Qual versão do Python é necessária?

Global-Data-Finance requer Python **>=3.12,<4.0**. O workflow atual de CI
exercita Python 3.12, 3.13 e 3.14; outras versões dentro do intervalo suportado
não são implicitamente testadas pelo CI.

### Posso usar em ambiente virtual?

Sim, e é altamente recomendado! Use `venv` ou `conda`:

```bash
python -m venv venv
source venv/bin/activate  # Linux/macOS
pip install globaldatafinance
```

______________________________________________________________________

## Uso Geral

### Onde os arquivos são salvos?

Os arquivos baixados e extraídos são salvos no diretório especificado em `destination_path`, estruturados em subpastas por tipo de documento e ano (formato `{destination_path}/{DOC}/{YEAR}/`). Por exemplo:

```python
from globaldatafinance import FundamentalStocksDataCVM

cvm = FundamentalStocksDataCVM()
cvm.download(
    destination_path="/home/usuario/dados",
    list_docs=["DFP"],
    initial_year=2023,
    last_year=2023,
)
# Arquivos salvos em: /home/usuario/dados/DFP/2023/dfp_cia_aberta_2023.zip
```

### Como verificar quais documentos estão disponíveis?

Use os métodos `get_available_*` das classes principais:

```python
from globaldatafinance import (
    FundamentalStocksDataCVM,
    HistoricalQuotesB3,
)

# Para CVM
cvm = FundamentalStocksDataCVM()
docs = cvm.get_available_docs()
years = cvm.get_available_years()

# Para B3
b3 = HistoricalQuotesB3()
assets = b3.get_available_assets()
years = b3.get_available_years()
```

______________________________________________________________________

## Documentos CVM

### Quais tipos de documentos posso baixar?

- **DFP**: Demonstrações Financeiras Padronizadas
- **ITR**: Informações Trimestrais
- **FRE**: Formulário de Referência
- **FCA**: Formulário Cadastral
- **CGVN**: Código de Governança
- **VLMO**: Valores Mobiliários
- **IPE**: Informações Periódicas e Eventuais

Veja [Documentos CVM](cvm-docs.md) para detalhes.

### Como baixar apenas um tipo de documento?

```python
cvm.download(
    destination_path="/data",
    list_docs=["DFP"],  # Apenas DFP
    initial_year=2022
)
```

### O que é extração automática?

Com `automatic_extractor=True`, os arquivos ZIP são automaticamente extraídos e convertidos para formato Parquet:

```python
from globaldatafinance import FundamentalStocksDataCVM

cvm = FundamentalStocksDataCVM()
result = cvm.download(
    destination_path="/data",
    list_docs=["DFP"],
    automatic_extractor=True,  # Converte para Parquet
)
```

### Como lidar com downloads interrompidos?

A biblioteca possui retry automático. Para maior robustez, implemente sua própria lógica de retry (veja [estratégia de retry](../dev-guide/retry-strategy.md#exemplo-de-uso)).

______________________________________________________________________

## Cotações B3

### Onde obter arquivos COTAHIST?

Baixe do site oficial da B3:
🔗 [https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/](https://www.b3.com.br/pt_br/market-data-e-indices/servicos-de-dados/market-data/historico/mercado-a-vista/cotacoes-historicas/)

A API aceita `COTAHIST_A{YYYY}.ZIP` e o TXT descompactado
`COTAHIST_A{YYYY}.TXT`; para o mesmo ano, o ZIP tem precedência. `path_of_docs`
é um diretório de entrada local já existente; a biblioteca não baixa nem o
preenche com arquivos B3. BDRs e Futures são **Planned**, não categorias aceitas
atualmente.

### Qual a diferença entre modo fast e slow?

| Modo     | Performance | CPU   | Pico de RAM (Faixa Operacional) | Quando usar                         |
| -------- | ----------- | ----- | ------------------------------- | ----------------------------------- |
| **fast** | Alta        | Alto  | ~2 GB a 4.2 GB (padrão)         | Máquinas com bons recursos (padrão) |
| **slow** | Moderada    | Baixo | ~500 MB a 1.5 GB                | Recursos limitados                  |

> Os valores de benchmark medidos em dataset anual completo (~4.260 MB em modo `fast` e ~1.571 MB em modo `slow`) representam cenários de carga máxima. Em execuções operacionais típicas ou anos individuais, o pico varia dentro das faixas indicadas.

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()

# Modo fast (padrão)
result_fast = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    processing_mode="fast",
)

# Modo slow (menor consumo de recursos)
result_slow = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    processing_mode="slow",
)
```

### Como extrair registros da classe de ações?

O alias `"ações"` seleciona os códigos TPMERC 010 (mercado à vista) e 020
(mercado fracionário):

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],  # Seleciona os códigos TPMERC 010 e 020
    initial_year=2023,
)
```

### Posso extrair múltiplas classes de ativos?

Sim! Passe uma lista com as classes desejadas:

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações", "etf", "opções"],
    initial_year=2023,
)
```

### Como personalizar o nome do arquivo de saída?

Use o parâmetro `output_filename`:

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    output_filename="acoes_2023",  # Gera: acoes_2023.parquet
)
```

______________________________________________________________________

## Performance

### Como acelerar downloads?

O Global-Data-Finance já usa download paralelo por padrão (`AsyncDownloadAdapterCVM`), que é 3-5x mais rápido que download sequencial.

### Como acelerar extração de cotações?

Use o modo `"fast"` (padrão):

```python
from globaldatafinance import HistoricalQuotesB3

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    processing_mode="fast",
)
```

### Posso processar em paralelo?

Sim! Você pode executar múltiplas extrações em paralelo usando `multiprocessing` ou `concurrent.futures`:

```python
from concurrent.futures import ProcessPoolExecutor
from globaldatafinance import HistoricalQuotesB3


def extract_year(year: int) -> dict:
    b3 = HistoricalQuotesB3()
    return b3.extract(
        path_of_docs="/data/cotahist",
        assets_list=["ações"],
        initial_year=year,
        last_year=year,
        output_filename=f"acoes_{year}",
    )


if __name__ == "__main__":
    with ProcessPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(extract_year, range(2020, 2024)))
```

______________________________________________________________________

## Análise de Dados

### Como ler os arquivos Parquet gerados?

Use Pandas ou PyArrow:

```python
# Com Pandas
import pandas as pd
df = pd.read_parquet("cotahist_extracted.parquet")

# Com PyArrow em batches
import pyarrow.parquet as pq
for batch in pq.ParquetFile("cotahist_extracted.parquet").iter_batches():
    print(batch)
```

### Qual biblioteca é usada pela extração?

- **PyArrow**: engine produtivo de leitura/escrita e opção de batches para
  volumes grandes.
- **Pandas**: compatível com os Parquets gerados e mantido pelo adaptador CSV
  legado.

Polars não é instalado pelo pacote, mas pode ser adicionado pelo consumidor como
um leitor downstream opcional.

### Como filtrar dados de um ativo específico?

```python
import pandas as pd
df = pd.read_parquet("cotahist_extracted.parquet")
petr4 = df[df['ticker'] == 'PETR4']
```

______________________________________________________________________

## Erros Comuns

### "No module named 'globaldatafinance'"

**Causa**: Biblioteca não instalada ou ambiente virtual não ativado.

**Solução**:

```bash
pip install globaldatafinance
```

### "Python version not supported"

**Causa**: O script está executando fora do intervalo `>=3.12,<4.0`.

**Solução**: Instale uma versão suportada do Python e recrie o ambiente.

### "InvalidDocumentName"

**Causa**: Tipo de documento inválido.

**Solução**: Verifique tipos disponíveis:

```python
docs = cvm.get_available_docs()
print(list(docs.keys()))
```

### "EmptyDirectoryError"

**Causa**: `EmptyDirectoryError` ocorre somente quando o diretório de entrada
está fisicamente vazio. Se o diretório não está vazio, mas não contém COTAHIST
correspondente ao ano solicitado, a API retorna um resultado vazio com
`success=True`, `total_files=0`, `total_records=0`, `output_file=""` e
`errors={}`.

**Solução**: Quando o diretório estiver vazio, coloque nele arquivos
`COTAHIST_A{YYYY}.ZIP` ou `.TXT`. Para diretórios não vazios, inspecione
`total_files` e `total_records` para confirmar se os anos solicitados possuem
dados.

### Falhas de Download ou Timeout

**Causa**: Instabilidade de conexão ou indisponibilidade temporária dos servidores regulatórios da CVM.

**Solução**:

1. A biblioteca realiza retries automáticos com backoff exponencial durante o download assíncrono.
2. Inspecione `result.failed_downloads` após a chamada para verificar se algum arquivo falhou.
3. Se necessário, configure `DATAFINANCE_NETWORK_TIMEOUT` e `DATAFINANCE_NETWORK_MAX_RETRIES` via variáveis de ambiente.

______________________________________________________________________

## Produção e Deploy

### Posso usar em produção?

O pacote está classificado como **Beta**. Os fluxos CVM e B3 atualmente
implementados são considerados **Production** dentro dos contratos
documentados e são exercitados pelos quality gates do repositório. BDRs,
Futures e outras capacidades planejadas não são suportados. Recomendações:

- Use logging apropriado
- Implemente tratamento de erros robusto
- Configure retry logic para downloads
- Monitore uso de disco e memória

### Como agendar downloads automáticos?

Use `cron` (Linux/macOS) ou Task Scheduler (Windows):

```bash
# Crontab: executar todo dia às 2h da manhã
0 2 * * * /path/to/venv/bin/python /path/to/script.py
```

### Como integrar com pipelines de dados?

Global-Data-Finance funciona bem com:

- **Apache Airflow**: Crie DAGs para orquestração
- **Prefect**: Use como tasks em flows
- **Luigi**: Integre como tasks
- **Dagster**: Use como ops/assets

Exemplo com Airflow:

```python
from datetime import datetime
from airflow import DAG
from airflow.operators.python import PythonOperator
from globaldatafinance import FundamentalStocksDataCVM


def download_cvm():
    cvm = FundamentalStocksDataCVM()
    cvm.download(
        destination_path="/data/cvm",
        list_docs=["DFP"],
        initial_year=2023,
    )


with DAG(
    dag_id="cvm_download",
    start_date=datetime(2024, 1, 1),
    schedule="@daily",
    catchup=False,
) as dag:
    task = PythonOperator(
        task_id="download",
        python_callable=download_cvm,
    )
```

______________________________________________________________________

## Contribuição

### Como contribuir com o projeto?

Veja o [guia de contribuição](../dev-guide/contributing.md) para detalhes completos.

### Como reportar bugs?

Abra uma issue no GitHub:
🔗 [https://github.com/jordanestralioto/Global-Data-Finance/issues](https://github.com/jordanestralioto/Global-Data-Finance/issues)

### Como sugerir novas funcionalidades?

Abra uma issue com a tag `enhancement` no GitHub.

______________________________________________________________________

## Licença e Uso

### Qual a licença do Global-Data-Finance?

Apache License 2.0.

### Posso usar em projetos comerciais?

Sim! A licença Apache 2.0 permite uso comercial.

### Os dados baixados têm restrições de uso?

Os dados são públicos e fornecidos pela CVM e B3. Consulte os termos de uso de cada instituição:

- **CVM**: [http://www.cvm.gov.br/](http://www.cvm.gov.br/)
- **B3**: [https://www.b3.com.br/](https://www.b3.com.br/)

______________________________________________________________________

## Suporte

### Onde obter ajuda?

1. **Documentação**: Leia a [documentação completa](../index.md)
2. **GitHub Issues**: [Abra uma issue](https://github.com/jordanestralioto/Global-Data-Finance/issues)
3. **Email**: estraliotojordan@gmail.com

### Como reportar problemas de segurança?

Envie um email para: estraliotojordan@gmail.com

______________________________________________________________________

!!! tip "Não encontrou sua pergunta?"

    Abra uma issue no GitHub ou consulte a [documentação completa](../index.md).
