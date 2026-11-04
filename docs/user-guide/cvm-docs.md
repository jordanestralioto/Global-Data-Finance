# Documentos CVM

Use `FundamentalStocksDataCVM` para baixar documentos da CVM por tipo e ano.
O download requer internet; a conversão para Parquet é opcional.

## Escolher documentos e anos

| Código | Conteúdo | Primeiro ano |
| --- | --- | --- |
| `DFP` | Demonstrações financeiras anuais | 2010 |
| `ITR` | Informações trimestrais | 2011 |
| `FRE` | Formulário de referência | 2010 |
| `FCA` | Formulário cadastral | 2010 |
| `CGVN` | Informe de governança | 2018 |
| `VLMO` | Valores mobiliários negociados e detidos | 2018 |
| `IPE` | Documentos periódicos e eventuais | 2003 |

Os anos inicial e final são inclusivos. Em seleções mistas, cada documento
respeita seu primeiro ano. `get_available_docs()` retorna os códigos e suas
descrições; `get_available_years()` retorna os limites por grupo e o ano atual.

## Baixar e converter

```python
from globaldatafinance import FundamentalStocksDataCVM

result = FundamentalStocksDataCVM().download(
    destination_path="./data_cvm",
    list_docs=["DFP", "ITR"],
    initial_year=2023,
    last_year=2023,
    automatic_extractor=True,
)
if result.error_count_downloads > 0 or result.success_count_downloads == 0:
    raise RuntimeError(result.failed_downloads)
print(result.successful_downloads)
```

Escolha um intervalo pequeno na primeira execução. A pasta de destino pode ser
relativa ou absoluta e precisa permitir escrita.

| Opção | Comportamento |
| --- | --- |
| `list_docs` | Lista de códigos. `None` ou `[]` seleciona todos os tipos. |
| `initial_year` / `last_year` | Limites inclusivos. Sem limites explícitos, a seleção usa os mínimos disponíveis e o ano atual. |
| `automatic_extractor=False` | Padrão: salva os ZIPs. |
| `automatic_extractor=True` | Salva os ZIPs e converte seus CSVs para Parquet. |

A [referência CVM](../reference/cvm-api.md) contém a assinatura completa,
os limites de anos e as exceções.

## Entender os arquivos gerados

Os ZIPs originais são preservados, inclusive anexos que não são CSV. A extração
gera um Parquet por CSV, com o mesmo nome base. ZIPs e Parquets ficam em
`{destination_path}/{DOC}/{YEAR}/`, por exemplo:

```text
data_cvm/DFP/2023/
├── dfp_cia_aberta_2023.zip
└── dfp_cia_aberta_BPA_con_2023.parquet
```

O nome de cada Parquet depende dos CSVs presentes no ZIP.

No contrato `exact-text-v1`, **todas as colunas CVM são texto**. Zeros iniciais,
separadores decimais e tokens literais são preservados; campos vazios são
`""`. Converta datas e valores numéricos explicitamente na análise. Um CSV
com apenas cabeçalho produz um Parquet vazio com as colunas definidas.

O conteúdo é conferido antes da publicação. O lote de Parquets é recuperável
em caso de falha; leitores concorrentes não recebem uma troca instantânea de
todo o diretório. Os detalhes ficam na [referência CVM](../reference/cvm-api.md)
e no [protocolo de publicação](../reference/transactional-publication.md).

## Conferir sucesso e tratar falhas

O retorno é um `DownloadResultCVM`, não uma tabela de dados:

- `successful_downloads` lista os identificadores concluídos, como `DFP_2023`.
- `failed_downloads` associa falhas aos respectivos diagnósticos.
- `success_count_downloads` e `error_count_downloads` resumem o lote.

Falhas de arquivos individuais são registradas no resultado e podem coexistir
com downloads concluídos. Verifique esses campos antes de continuar a análise.
Erros de parâmetros ou caminhos podem levantar exceções imediatamente; consulte
as [exceções documentadas](../reference/cvm-api.md).

Em notebooks ou aplicações com event loop ativo, use
`await cvm.async_download(...)` com os mesmos argumentos e resultado, conforme
a [API assíncrona](../reference/cvm-api.md#async_download).

Para ajustar logs e tentativas, veja [logging](../dev-guide/logging-system.md)
e [retry](../dev-guide/retry-strategy.md). Se já consumia os Parquets com tipos
inferidos, siga a [migração para texto exato](migration-cvm-exact-text.md).

## Retomar downloads com checkpoint

Ajuste `base_path` para uma pasta onde a aplicação tenha permissão de escrita.

Registre `successful_downloads` em um checkpoint da aplicação. A pasta do ano pode existir após uma falha. Solicite cada ano pendente separadamente para respeitar lacunas no histórico:

```python
import json
from pathlib import Path

from globaldatafinance import FundamentalStocksDataCVM

cvm = FundamentalStocksDataCVM()
base_path = Path("/data/cvm")
checkpoint = base_path / "completed-downloads.json"
completed_downloads = set()
if checkpoint.is_file():
    completed_downloads.update(json.loads(checkpoint.read_text(encoding="utf-8")))
current_year = cvm.get_available_years().current_year
refresh_years = {current_year}
for year in range(2020, current_year + 1):
    identifier = f"DFP_{year}"
    if identifier in completed_downloads and year not in refresh_years:
        continue
    result = cvm.download(
        destination_path=str(base_path), list_docs=["DFP"],
        initial_year=year, last_year=year, automatic_extractor=True,
    )
    if identifier in result.successful_downloads:
        completed_downloads.add(identifier)
        pending = checkpoint.with_suffix(".tmp")
        pending.write_text(json.dumps(sorted(completed_downloads)), encoding="utf-8")
        pending.replace(checkpoint)
    if result.has_errors():
        print(result.failed_downloads)
```

O exemplo usa um checkpoint de um único processo e atualiza o ano corrente a cada execução. A CVM também pode revisar anos anteriores: inclua-os em `refresh_years` conforme a política da aplicação. O checkpoint registra sucessos anteriores; revalide os artefatos locais antes de reutilizá-los e remova os identificadores cujos arquivos estejam ausentes ou corrompidos.
