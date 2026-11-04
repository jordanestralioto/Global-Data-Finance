# Instalação

Use Python `>=3.12,<4.0`. A CI verifica Python 3.12, 3.13 e 3.14. O espaço em
disco e a memória necessários dependem dos arquivos e anos processados.

## Instalar com pip

Crie um ambiente virtual:

```bash
python -m venv .venv
```

Ative-o com o comando do seu terminal:

| Terminal | Comando |
| --- | --- |
| Linux/macOS | `source .venv/bin/activate` |
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| Windows cmd | `.venv\Scripts\activate.bat` |

Instale a biblioteca no ambiente ativo:

```bash
python -m pip install globaldatafinance
```

## Instalar em um projeto com uv

```bash
uv add globaldatafinance
```

Para alterar o código da biblioteca, siga o ambiente com lockfile do
[guia de contribuição](../dev-guide/contributing.md).

## Conferir a instalação

No mesmo ambiente em que instalou a biblioteca:

```python
from importlib.metadata import version
from globaldatafinance import FundamentalStocksDataCVM, HistoricalQuotesB3

print(version("globaldatafinance"))
print(FundamentalStocksDataCVM().get_available_docs())
print(HistoricalQuotesB3().get_available_assets())
```

Essas consultas não baixam dados. PyArrow já é instalado pela biblioteca.
Pandas e Polars são leitores opcionais para análise dos Parquets e devem ser
instalados separadamente quando necessários.

## Resolver problemas comuns

| Sintoma | O que verificar |
| --- | --- |
| `No module named globaldatafinance` | Use o mesmo Python na instalação e na execução; confira `python -m pip show globaldatafinance`. |
| Python incompatível | Crie o ambiente virtual com uma versão no intervalo suportado. |
| Conflito de dependências | Instale em um ambiente virtual novo; as versões do projeto ficam em `pyproject.toml`. |
| Falha de permissão ao instalar | Use um ambiente virtual em uma pasta onde você tenha permissão de escrita. |

Continue pelo [início rápido](quickstart.md).
