# Installation

Use Python `>=3.12,<4.0`. CI checks Python 3.12, 3.13, and 3.14. Required disk
space and memory depend on the files and years being processed.

## Install with pip

Create a virtual environment:

```bash
python -m venv .venv
```

Activate it using the command for your terminal:

| Terminal | Command |
| --- | --- |
| Linux/macOS | `source .venv/bin/activate` |
| Windows PowerShell | `.venv\Scripts\Activate.ps1` |
| Windows cmd | `.venv\Scripts\activate.bat` |

Install the library in the active environment:

```bash
python -m pip install globaldatafinance
```

## Install in a project with uv

```bash
uv add globaldatafinance
```

To change the library's source code, follow the locked environment setup in the
[contributing guide](../dev-guide/contributing.md).

## Verify the installation

In the same environment where you installed the library:

```python
from importlib.metadata import version
from globaldatafinance import FundamentalStocksDataCVM, HistoricalQuotesB3

print(version("globaldatafinance"))
print(FundamentalStocksDataCVM().get_available_docs())
print(HistoricalQuotesB3().get_available_assets())
```

These queries do not download data. The library already installs PyArrow.
Pandas and Polars are optional readers for Parquet analysis; install them
separately when needed.

## Resolve common problems

| Symptom | What to check |
| --- | --- |
| `No module named globaldatafinance` | Use the same Python for installation and execution; check `python -m pip show globaldatafinance`. |
| Unsupported Python | Create the virtual environment with a version in the supported range. |
| Dependency conflict | Install in a new virtual environment; project versions are in `pyproject.toml`. |
| Installation permission failure | Use a virtual environment in a directory where you have write access. |

Continue with the [quickstart](quickstart.md).
