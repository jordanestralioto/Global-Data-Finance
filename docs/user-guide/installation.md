# Instalação

Este guia fornece instruções detalhadas para instalar e configurar a biblioteca **Global-Data-Finance** em diferentes ambientes.

______________________________________________________________________

## Requisitos do Sistema

Antes de instalar o Global-Data-Finance, certifique-se de que seu sistema atende aos seguintes requisitos:

### Requisitos Obrigatórios

- **Python**: `>=3.12,<4.0`
- **Sistema Operacional**: Linux, macOS ou Windows
- **Espaço em Disco**: Mínimo de 2 GB para conseguir baixar todos os dados
- **Memória RAM**: Mínimo de 3 GB (recomendado 6 GB ou mais para grandes volumes)

### Verificar Versão do Python

```bash
python --version
# ou
python3 --version
```

!!! warning "Versão do Python"

    O Global-Data-Finance requer uma versão do Python no intervalo `>=3.12,<4.0`. O workflow atual de CI exercita Python 3.12, 3.13 e 3.14; outras versões dentro do intervalo suportado não são implicitamente testadas pelo CI.

______________________________________________________________________

## Instalação via pip (Recomendado)

A forma mais simples de instalar o Global-Data-Finance é através do PyPI usando o `pip`:

```bash
pip install globaldatafinance
```

### Instalação em Ambiente Virtual (Recomendado)

É altamente recomendado instalar o Global-Data-Finance em um ambiente virtual para evitar conflitos de dependências:

```bash
# Criar ambiente virtual
python -m venv venv

# Ativar ambiente virtual
# No Linux/macOS:
source venv/bin/activate

# No Windows:
venv\Scripts\activate

# Instalar Global-Data-Finance
pip install globaldatafinance
```

### Atualizar para Última Versão

```bash
pip install --upgrade globaldatafinance
```

______________________________________________________________________

## Instalação via uv (alternativa ao pip)

`uv` é um gerenciador de pacotes Python rápido e é o gestor canônico deste projeto em desenvolvimento. Para consumir a biblioteca em outro projeto que usa `uv`:

```bash
# Adicionar ao projeto
uv add globaldatafinance

# Como dependência de desenvolvimento
uv add --dev globaldatafinance
```

______________________________________________________________________

## Instalação para Desenvolvimento

Se você deseja contribuir com o projeto ou modificar o código-fonte:

### 1. Clonar o Repositório

```bash
git clone https://github.com/jordanestralioto/Global-Data-Finance.git
cd Global-Data-Finance
```

### 2. Instalar com uv (Recomendado)

`uv.lock` é commitado no repositório, então `uv sync --locked` reproduz
exatamente o ambiente de desenvolvimento usado pelo CI.

```bash
# Sincronizar dependências (cria .venv automaticamente)
uv sync --locked --all-extras --dev

# Rodar comandos no ambiente do projeto
uv run --locked --no-sync pytest
uv run --locked --no-sync pre-commit run --all-files --show-diff-on-failure
```

______________________________________________________________________

## Dependências

O Global-Data-Finance possui as seguintes dependências principais:

### Dependências Obrigatórias

| Biblioteca          | Versão  | Descrição                                  |
| ------------------- | ------- | ------------------------------------------ |
| `httpx`             | ≥0.28.1 | Cliente HTTP assíncrono com suporte HTTP/2 |
| `pandas`            | ≥2.3.3  | Compatibilidade do adaptador CSV legado    |
| `pyarrow`           | ≥23.0.1,<24.0.0 | Engine produtivo de CSV e Apache Parquet   |
| `pydantic-settings` | ≥2.11.0 | Configuração e validação de dados          |
| `psutil`            | ≥5.9.0  | Utilitários de sistema e processos         |

### Dependências de Desenvolvimento (Opcionais)

Instaladas automaticamente apenas em modo desenvolvimento:

| Biblioteca        | Descrição                      |
| ----------------- | ------------------------------ |
| `pytest`          | Framework de testes            |
| `pytest-cov`      | Cobertura de testes            |
| `pytest-asyncio`  | Suporte a testes assíncronos   |
| `mypy`            | Verificação de tipos estáticos |
| `pre-commit`      | Hooks de pré-commit            |
| `mkdocs`          | Gerador de documentação        |
| `mkdocs-material` | Tema Material para MkDocs      |
| `hypothesis`       | Testes de propriedades         |

`polars` não é uma dependência de runtime do Global-Data-Finance. Consumidores
que queiram usar Polars para analisar os Parquets podem instalá-lo separadamente;
o pacote produz arquivos Apache Parquet independentes do leitor escolhido.

______________________________________________________________________

## Verificação da Instalação

Após a instalação, verifique se tudo está funcionando corretamente:

### 1. Verificar Importação

```pycon
>>> from globaldatafinance import FundamentalStocksDataCVM, HistoricalQuotesB3
>>> print("✓ Global-Data-Finance instalado com sucesso!")
✓ Global-Data-Finance instalado com sucesso!
```

### 2. Consultar a Versão Instalada

```pycon
>>> from importlib.metadata import version
>>> print(version("globaldatafinance"))
```

A saída reflete a metadata da distribuição efetivamente instalada.

### 3. Teste Básico

```python
from globaldatafinance import FundamentalStocksDataCVM

# Criar instância
cvm = FundamentalStocksDataCVM()

# Verificar documentos disponíveis
docs = cvm.get_available_docs()
print(f"✓ Encontrados {len(docs)} tipos de documentos disponíveis")

# Verificar anos disponíveis
years = cvm.get_available_years()
print(f"✓ Dados disponíveis de {years.general_min_year} até {years.current_year}")
```

Se todos os comandos acima executarem sem erros, a instalação foi bem-sucedida! ✅

______________________________________________________________________

## Solução de Problemas

### Erro: "No module named 'globaldatafinance'"

**Causa**: A biblioteca não foi instalada corretamente ou o ambiente virtual não está ativado.

**Solução**:

```bash
# Verificar se está no ambiente virtual correto
which python  # Linux/macOS
where python  # Windows

# Reinstalar a biblioteca
pip install --force-reinstall globaldatafinance
```

### Erro: "Python version outside supported range"

**Causa**: A versão do interpretador está fora do intervalo `>=3.12,<4.0`.

**Solução**:

1. Instale uma versão suportada do Python no [site oficial](https://www.python.org/downloads/)
2. Crie um novo ambiente virtual com a versão correta:

```bash
python3.12 -m venv venv
source venv/bin/activate
pip install globaldatafinance
```

### Erro de Dependências

**Causa**: Conflito com outras bibliotecas instaladas.

**Solução**:

```bash
# Criar ambiente virtual limpo
python -m venv venv_clean
source venv_clean/bin/activate
pip install globaldatafinance
```

### Erro de Permissão (Linux/macOS)

**Causa**: Tentativa de instalação sem permissões adequadas.

**Solução**:

```bash
# NÃO use sudo pip install!
# Em vez disso, use ambiente virtual:
python -m venv venv
source venv/bin/activate
pip install globaldatafinance
```

### Problemas com Proxy Corporativo

Se você está atrás de um proxy corporativo:

```bash
# Configurar proxy
export HTTP_PROXY="http://proxy.empresa.com:8080"
export HTTPS_PROXY="http://proxy.empresa.com:8080"

# Instalar com pip
pip install globaldatafinance
```

______________________________________________________________________

## Desinstalação

Para remover o Global-Data-Finance do seu sistema:

```bash
pip uninstall globaldatafinance
```

______________________________________________________________________

## Próximos Passos

Agora que você instalou o Global-Data-Finance com sucesso, explore:

- 🚀 **[Início Rápido](quickstart.md)** - Primeiros passos e exemplos básicos
- 📄 **[Documentos CVM](cvm-docs.md)** - Guia completo da API CVM
- 📈 **[Cotações B3](b3-docs.md)** - Guia completo da API B3
- 💻 **[Exemplos Práticos](examples.md)** - Casos de uso reais

______________________________________________________________________

!!! tip "Dica para Desenvolvedores"

    Se você planeja contribuir com o projeto, consulte o [Guia de Contribuição](../dev-guide/contributing.md) para configurar seu ambiente de desenvolvimento completo.
