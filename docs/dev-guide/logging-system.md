# Sistema de Logging

Documentação completa do sistema de logging avançado do Global-Data-Finance.

______________________________________________________________________

## Visão Geral

O Global-Data-Finance possui um sistema de logging centralizado e profissional que oferece:

- ✅ **Lazy initialization** - Logging desabilitado por padrão (biblioteca-friendly)
- ✅ **Console e arquivo** - Handlers configuráveis
- ✅ **Níveis customizáveis** - DEBUG, INFO, WARNING, ERROR, CRITICAL
- ✅ **Performance timing** - Context managers para medir tempo de execução
- ✅ **Structured logging** - Logs com dados contextuais
- ✅ **Variáveis de ambiente** - Configuração via environment variables

______________________________________________________________________

## Estado Inicial e Isolamento

Importar a biblioteca não configura o root logger da aplicação nem instala
saídas visíveis. O logger `globaldatafinance` começa com um `NullHandler` e
`propagate=False`, portanto eventos permanecem silenciosos até que o consumidor
chame `setup_logging()` explicitamente. A configuração afeta somente essa
hierarquia de loggers.

`LoggingSettings` aceita apenas os campos documentados: `level`, `format`,
`log_file` e `detailed_format`. Campos extras, como o removido
`structured`, falham com `ValidationError`.

As variáveis de ambiente suportadas são `DATAFIN_LOG_LEVEL`,
`DATAFIN_LOG_FORMAT`, `DATAFIN_LOG_FILE` e `DATAFIN_LOG_DETAILED_FORMAT`.
`DATAFIN_LOG_LOG_FILE` também é aceito como compatibilidade com o nome
derivado do campo. Qualquer outra variável `DATAFIN_LOG_*`, incluindo
`DATAFIN_LOG_STRUCTURED`, falha com `ValidationError` quando
`LoggingSettings()` é criado.

O formatter faz uma redação de melhor esforço para parâmetros comuns de URL e
campos de contexto sensíveis, como `token`, `password`, `authorization` e
`cookie`. Isso não substitui a responsabilidade do consumidor: segredos não
devem ser enviados em mensagens, exceções ou contexto de logging.

`log_file` deve apontar para um caminho de aplicação aprovado pelo consumidor.
Antes de criar diretórios ou o arquivo, `setup_logging()` rejeita raízes do
sistema, diretórios protegidos e destinos UNC não confiáveis, usando a mesma
política de segurança de caminhos das fachadas de dados. Use um diretório da
aplicação ou, para diagnóstico local, `/tmp`.

## Reconfiguração e Rollback

`setup_logging()` constrói e configura todos os handlers candidatos antes de
alterar o logger do pacote. Em uma reconfiguração bem-sucedida, somente
handlers gerenciados pela biblioteca são substituídos; handlers externos são
preservados. Se a criação do arquivo ou a troca falhar, os candidatos são
fechados e o nível, a propagação e os handlers anteriores são restaurados.

Isso permite que aplicações reconfigurem o logging sem perder a configuração
que já estava ativa:

```python
from globaldatafinance.core.logging_config import LoggingSettings, setup_logging

setup_logging(LoggingSettings(level="INFO"))
setup_logging(LoggingSettings(level="DEBUG", log_file="app-debug.log"))
```

## Arquitetura

### Componentes Principais

```
src/globaldatafinance/core/logging_config.py
├── setup_logging()           # Inicialização do logging
├── get_logger()              # Obter logger por módulo
├── log_execution_time()      # Context manager para timing
├── log_with_context()        # Logging estruturado
├── LoggingSettings           # Configurações
├── StructuredFormatter       # Formatter customizado
└── ContextFilter             # Filtro de contexto
```

______________________________________________________________________

## Uso Básico

### 1. Habilitar Logging

Por padrão, o logging está **desabilitado**. Para habilitar:

```python
from globaldatafinance.core.logging_config import LoggingSettings, setup_logging

# Habilitar logging com nível INFO
setup_logging(LoggingSettings(level="INFO"))
```

### 2. Obter Logger em um Módulo

```python
from globaldatafinance.core.logging_config import get_logger

logger = get_logger(__name__)
logger.info("Processamento iniciado")
logger.debug("Detalhes de debug")
logger.warning("Aviso importante")
logger.error("Erro ocorreu")
```

### 3. Logging Estruturado

```python
logger.info(
    "Arquivo processado",
    extra={
        "file_target": "data.csv",
        "records": 1000,
        "elapsed_ms": 250
    }
)
```

**Saída**:

```
2025-11-25 17:30:00 | INFO     | meu_modulo | Arquivo processado | file_target=data.csv | records=1000 | elapsed_ms=250
```

______________________________________________________________________

## Configuração

### Níveis de Log

| Nível        | Uso                                   | Exemplo                                            |
| ------------ | ------------------------------------- | -------------------------------------------------- |
| **DEBUG**    | Informações detalhadas para debugging | Valores de variáveis, fluxo de execução            |
| **INFO**     | Confirmação de funcionamento normal   | "Download iniciado", "Arquivo salvo"               |
| **WARNING**  | Alerta de situação inesperada         | "Arquivo já existe", "Timeout, tentando novamente" |
| **ERROR**    | Erro que não impede execução          | "Falha ao baixar arquivo X"                        |
| **CRITICAL** | Erro grave que pode parar aplicação   | "Disco cheio", "Sem memória"                       |

### Configuração via Código

```python
from globaldatafinance.core.logging_config import LoggingSettings, setup_logging

# Configuração básica
setup_logging(LoggingSettings(level="INFO"))

# Com arquivo de log
setup_logging(
    LoggingSettings(
        level="DEBUG",
        log_file="/tmp/datafin.log",
    )
)

# Formato detalhado (com linhas e funções)
setup_logging(
    LoggingSettings(
        level="DEBUG",
        detailed_format=True,
    )
)
```

### Configuração via Variáveis de Ambiente

```bash
# Nível de log
export DATAFIN_LOG_LEVEL=DEBUG

# Arquivo de log
export DATAFIN_LOG_FILE=/tmp/datafin.log

# Formato detalhado
export DATAFIN_LOG_DETAILED_FORMAT=true
```

Variáveis `DATAFIN_LOG_*` desconhecidas são rejeitadas; isso evita que uma
opção removida ou digitada incorretamente pareça ter sido aplicada.

```python
from globaldatafinance.core.logging_config import setup_logging

# Usa configurações das variáveis de ambiente (snapshot LoggingSettings padrão)
setup_logging()
```

______________________________________________________________________

## Recursos Avançados

### Performance Timing

Use o context manager `log_execution_time()` para medir tempo de operações:

```python
from globaldatafinance.core.logging_config import log_execution_time, get_logger

logger = get_logger(__name__)

with log_execution_time(logger, "Parse ZIP file", file_target="data.zip"):
    parse_file("data.zip")
```

**Saída**:

```
Starting: Parse ZIP file | operation=Parse ZIP file | file_target=data.zip
Completed: Parse ZIP file | operation=Parse ZIP file | elapsed_seconds=2.45 | file_target=data.zip
```

Se ocorrer erro:

```
Failed: Parse ZIP file | operation=Parse ZIP file | elapsed_seconds=1.23 | error=File not found | file_target=data.zip
```

### Logging com Contexto

```python
from globaldatafinance.core.logging_config import log_with_context, get_logger

logger = get_logger(__name__)

log_with_context(
    logger,
    "info",
    "Download concluído",
    url="https://example.com/file.zip",
    file_target="file.zip",
    size_mb=125.5,
    duration_seconds=45
)
```

### Verificar se Logging está Configurado

```python
from globaldatafinance.core.logging_config import (
    LoggingSettings,
    is_logging_configured,
    setup_logging,
)

if not is_logging_configured():
    setup_logging(LoggingSettings(level="INFO"))
```

### Snapshot de Configuração

`setup_logging()` retorna o snapshot `LoggingSettings` imutável aplicado à biblioteca:

```python
from globaldatafinance.core.logging_config import LoggingSettings, setup_logging

settings = setup_logging(LoggingSettings(level="INFO"))
print(f"Nível atual: {settings.level}")
print(f"Arquivo de log: {settings.log_file}")
print(f"Formato detalhado: {settings.detailed_format}")
```

______________________________________________________________________

## Exemplos Práticos

### Exemplo 1: Logging em Aplicação

```python
from globaldatafinance import FundamentalStocksDataCVM
from globaldatafinance.core.logging_config import (
    LoggingSettings,
    get_logger,
    setup_logging,
)

# Habilitar logging
setup_logging(LoggingSettings(level="INFO", log_file="app.log"))

logger = get_logger(__name__)
logger.info("Aplicação iniciada")

# Usar a biblioteca
cvm = FundamentalStocksDataCVM()
cvm.download(
    destination_path="/data/cvm",
    list_docs=["DFP"],
    initial_year=2023
)

logger.info("Aplicação finalizada")
```

### Exemplo 2: Debug de Problemas

```python
from globaldatafinance import HistoricalQuotesB3
from globaldatafinance.core.logging_config import LoggingSettings, setup_logging

# Nível DEBUG para troubleshooting
setup_logging(
    LoggingSettings(
        level="DEBUG",
        log_file="/tmp/debug.log",
        detailed_format=True,  # Inclui linhas e funções
    )
)

b3 = HistoricalQuotesB3()
result = b3.extract(
    path_of_docs="/data/cotahist",
    assets_list=["ações"],
    initial_year=2023
)
```

### Exemplo 3: Logging Customizado em Módulo Próprio

```python
# meu_script.py
from globaldatafinance import FundamentalStocksDataCVM
from globaldatafinance.core.logging_config import (
    LoggingSettings,
    get_logger,
    log_execution_time,
    setup_logging,
)

# Configurar logging
setup_logging(LoggingSettings(level="INFO"))

# Criar logger para este módulo
logger = get_logger(__name__)

def processar_dados():
    logger.info("Iniciando processamento")

    with log_execution_time(logger, "Download CVM"):
        cvm = FundamentalStocksDataCVM()
        cvm.download(
            destination_path="/data/cvm",
            list_docs=["DFP"],
            initial_year=2023
        )

    logger.info("Processamento concluído")

if __name__ == "__main__":
    processar_dados()
```

______________________________________________________________________

## Formatos de Log

### Formato Padrão

```
2025-11-25 17:30:00 | INFO     | módulo.nome | Mensagem de log
```

### Formato Detalhado

Inclui número de linha e nome da função:

```
2025-11-25 17:30:00 | INFO     | módulo.nome:123 | função_nome | Mensagem de log
```

### Formato com Dados Contextuais

```
2025-11-25 17:30:00 | INFO     | módulo | Mensagem | campo1=valor1 | campo2=valor2
```

______________________________________________________________________

## Boas Práticas

### 1. Sempre use `get_logger(__name__)`

```python
# ✅ Correto - hierarquia de nomes
logger = get_logger(__name__)

# ❌ Evite - nome hardcoded
logger = get_logger("meu_logger")
```

### 2. Use Níveis Apropriados

```python
# ✅ Correto
logger.debug("Valor da variável x: %s", x)
logger.info("Download iniciado")
logger.warning("Arquivo já existe, pulando")
logger.error("Falha ao processar arquivo", exc_info=True)

# ❌ Evite - nível errado
logger.info("Valor de debug: %s", x)  # Use DEBUG
logger.error("Arquivo processado")     # Use INFO
```

### 3. Use Structured Logging

```python
# ✅ Correto - dados estruturados
logger.info(
    "Arquivo processado",
    extra={"file_target": "data.csv", "size_mb": 10.5}
)

# ❌ Evite - string interpolation
logger.info(f"Arquivo data.csv processado, tamanho: 10.5 MB")
```

### 4. Use Context Manager para Timing

```python
# ✅ Correto - medição automática
with log_execution_time(logger, "Download"):
    time.sleep(1)

# ❌ Evite - medição manual
start = time.time()
time.sleep(1)
logger.info(f"Levou {time.time() - start}s")
```

______________________________________________________________________

## Troubleshooting

### Não vejo nenhum log

```python
# Certifique-se de chamar setup_logging()
from globaldatafinance.core.logging_config import LoggingSettings, setup_logging
setup_logging(LoggingSettings(level="INFO"))
```

### Logs duplicados

```python
# Se precisar reconfigurar, é seguro chamar novamente: apenas handlers gerenciados pela biblioteca são substituídos
setup_logging(LoggingSettings(level="DEBUG"))
```

### Logging em arquivo não funciona

```python
# Use um diretório da aplicação ou /tmp; raízes e diretórios protegidos são
# rejeitados antes de qualquer criação ou escrita.
setup_logging(LoggingSettings(level="INFO", log_file="/tmp/app.log"))
```

______________________________________________________________________

## Referências

- [Documentação Oficial Python Logging](https://docs.python.org/3/library/logging.html)
- [Logging Best Practices](https://docs.python.org/3/howto/logging.html)
- [Structured Logging](https://www.structlog.org/)

______________________________________________________________________

Veja também:

- [Configuração](advanced-usage.md#configuracao-global) - Configurações globais
- [Advanced Usage](advanced-usage.md) - Uso avançado do sistema
