# Testes

Guia completo sobre testes no Global-Data-Finance.

______________________________________________________________________

## Estrutura de Testes

A árvore de testes espelha cada fonte. Os subdiretórios dentro de cada feature são **organizacionais** (agrupam por tópico para legibilidade), não arquiteturais — qualquer teste importa diretamente dos módulos da fonte (`from globaldatafinance.brazil.<país>.<fonte>.<módulo> import ...`).

```
tests/
├── application/                       # tests do facade público
│   ├── cvm_docs/
│   └── b3_docs/
│       └── result_formatters/
├── brazil/
│   ├── b3_data/
│   │   └── historical_quotes/
│   │       ├── test_*.py              # tópicos de domínio e facade de uso
│   │       ├── extraction_service/    # serviço, parser em lote, recursos e merge
│   │       ├── parquet_writer/        # escrita e streaming Parquet
│   │       └── integration/            # COTAHIST local opt-in
│   └── cvm/
│       └── fundamental_stocks_data/
│           ├── application/use_cases/ # tests de orquestração (client.py)
│           ├── domain/                # tests de value objects e validators (core.py)
│           ├── infra/adapters/        # tests dos adapters concretos (http.py, extract.py)
│           ├── exceptions/            # tests das exceções (errors.py)
│           └── integration/           # fluxos CVM com filesystem/ZIP reais
├── core/
├── macro_infra/
└── macro_exceptions/
```

______________________________________________________________________

## Executando Testes

### Gate Determinístico Padrão

```bash
uv run --locked --no-sync pytest -m "not slow and not real_data and not perf" \
  --cov --cov-report=xml --cov-report=term-missing
```

Esse comando inclui testes unitários e integrações determinísticas criadas
pelos próprios testes. `perf`, dados reais e cenários `slow` não fazem parte do
gate padrão.

### Com Cobertura

A configuração de coverage, incluindo o limite `fail_under = 85`, fica em
`[tool.coverage.report]` no `pyproject.toml`. O `pytest.ini` mantém a
descoberta, os markers e as opções do pytest.

```bash
uv run --locked --no-sync pytest -m "not slow and not real_data and not perf" \
  --cov --cov-report=html
```

### Marcadores

Os markers registrados em `pytest.ini` têm contratos distintos. Cada teste
deve ter exatamente um tier primário:

- `unit`: comportamento isolado com fakes, stubs ou colaboradores puros;
- `integration`: vários componentes reais de produção e filesystem local
  determinístico;
- `perf`: benchmark ou medição de recursos, somente opt-in.

`slow`, `asyncio` e `real_data` são qualificadores ortogonais. `real_data`
exige `integration`, e `asyncio` não substitui o tier primário.

O gate `scripts/check_test_quality.py` é uma proteção estrutural e heurística:
ele verifica a classificação e a presença de uma observação aceita no corpo
executável direto do teste, sem descer em helpers, lambdas ou classes
aninhadas. Ele não prova que toda asserção protege uma regressão nem elimina a
necessidade de revisão contra tautologias semânticas.

```bash
# Apenas testes unitários
uv run --locked --no-sync pytest -m unit

# Integrações determinísticas, sem dados externos ou cenários lentos
uv run --locked --no-sync pytest -m "integration and not slow and not real_data and not perf"

# Benchmarks e medições (opt-in explícito)
uv run --locked --no-sync pytest tests/perf -m perf -o addopts=''
```

### COTAHIST local

Os testes `real_data` nunca baixam arquivos nem versionam dados financeiros.
O diretório é caller-owned e pode ser fornecido por `COTAHIST_PATH`; a
biblioteca não lê `.env` implicitamente. Para usar um arquivo dotenv local, o
chamador precisa selecionar isso explicitamente com `uv run --env-file .env`.
Sem `COTAHIST_PATH`, somente a suíte selecionada explicitamente é pulada; com
a variável definida, caminho inválido, vazio, ilegível ou sem o ano escolhido
falha.

A fixture inspeciona o catálogo de todos os arquivos locais antes de selecionar
um ano. Quando existe um único ano, ele pode ser inferido. Com vários anos,
`COTAHIST_TEST_YEAR` é obrigatório; ela nunca escolhe silenciosamente o maior
ano. O catálogo valida o central directory e a resolução do membro interno. A
paridade limitada cria uma amostra real não vazia de até 20.000 registros `01`
e compara fast/slow nas 20 colunas com tipos e ordenação exatos; como executa
os dois modos de processamento, ela é marcada `slow`. A prova anual, também
marcada `slow`, processa uma vez somente em modo `fast`.

```bash
COTAHIST_PATH=./cotahist_b3 COTAHIST_TEST_YEAR=2000 \
  uv run --locked --no-sync pytest -m "real_data and not slow"
COTAHIST_PATH=./cotahist_b3 COTAHIST_TEST_YEAR=2000 \
  uv run --locked --no-sync pytest -m "real_data and slow"
COTAHIST_PATH=./cotahist_b3 COTAHIST_TEST_YEAR=2024 \
  uv run --locked --no-sync pytest -m "real_data and not slow"
COTAHIST_PATH=./cotahist_b3 COTAHIST_TEST_YEAR=2024 \
  uv run --locked --no-sync pytest -m "real_data and slow"
```

`COTAHIST_TEST_YEAR` deve ter quatro dígitos. O ZIP tem precedência sobre o
TXT do mesmo ano. ZIPs modernos usam o membro `COTAHIST_A{YYYY}.TXT`; ZIPs
históricos podem usar `COTAHIST.A{YYYY}` ou `COTAHIST_A{YYYY}` sem extensão.
O diretório `cotahist_b3/` é ignorado pelo Git. A adoção de um dataset oficial anual no CI
só pode ocorrer após fixture versionado ou artefato de CI publicado com licença
compatível; até lá, a validação permanece opt-in.

### Campanha real auditável

Para auditar a matriz completa sem depender da configuração implícita do
ambiente, use o executor opt-in com todos os caminhos explícitos. O relatório e
os artefatos temporários devem ficar fora do repositório:

```bash
uv run --locked --no-sync python scripts/real_validation.py \
  --source all \
  --cotahist-path /caminho/externo/COTAHIST \
  --cvm-output /tmp/globaldatafinance-cvm-output \
  --report /tmp/globaldatafinance-real-validation/run-2026-09-01 \
  --timeout 3600
```

`all` cria os 25 anos COTAHIST de 2000 a 2024 e as sete janelas CVM
documentadas, totalizando 102 combinações CVM. Para cada ano COTAHIST, o
executor roda `fast` e uma paridade integral `fast`/`slow`; o arquivo local é
validado e selecionado com precedência ZIP antes do processamento. COTAHIST
nunca é baixado pelo executor. A matriz CVM acessa somente os URLs oficiais
explicitamente definidos pelo código e classifica HTTP 404/410 como
`not_published`, indisponibilidade de rede como `external_failure` e conteúdo
inválido ou falha de processamento como `failed`.

Cada caso roda em um processo isolado. O diretório indicado por `--report`
contém `manifest.json`, um `results.jsonl` com apenas o resultado atual de cada
caso, `summary.json`, logs individuais e evidências de artefatos. Use
`--resume --report <mesmo-diretório>` para reexecutar somente casos
`external_failure` ou ainda não classificados; resultados funcionais e
`not_published` são preservados. Os resultados persistidos são evidência do
chamador, não uma atestação assinada: use `--resume` somente em um diretório
de relatório confiável quando a conclusão aprovada/reprovada precisar ter
valor probatório. Antes da retomada, cada arquivo COTAHIST é
comparado ao `inputSizeBytes` e ao `inputSha256` do manifesto. O hash é
calculado uma vez por caminho compartilhado; qualquer drift gera
`ReportFormatError`, não reexecuta nem sobrescreve resultados antigos e exige
uma nova campanha. O `caseId`, ano, modo e input COTAHIST também precisam
corresponder ao catálogo atual. Casos CVM primeiro validam o
`campaign.cvmOutput` persistido com a política de destinos externos e depois
são reconstruídos da matriz oficial de documento/ano: os campos persistidos,
inclusive `inputPath`, `url` e `outputRoot`, precisam ser idênticos ao caso
reconstruído e ao destino da campanha antes de um worker ser iniciado. Um
`outputRoot` adulterado falha antes de `mkdir`, `mkdtemp`, worker ou cliente
HTTP. A sonda CVM usa somente HTTPS no endpoint canônico, não segue
redirecionamentos e não persiste um corpo de preflight. O limite de bytes do
arquivo comprimido é aplicado tanto ao `Content-Length` quanto ao streaming da
fachada pública; o hash registrado é calculado no ZIP imediatamente antes da
extração pela própria fachada. `--report` e `--cvm-output` passam pela política
de destinos sensíveis antes de qualquer criação de diretório; raízes do
sistema, diretórios protegidos, drives Windows relativos e UNC não confiáveis
são rejeitados, enquanto `/tmp` e uma UNC explicitamente permitida podem ser
usados conforme a política compartilhada. O código de saída é `0` somente
quando toda a matriz foi executada sem falhas funcionais, falhas externas,
combinações não executadas ou processos órfãos; `1` indica falha funcional e
`2` indica dependência externa, timeout, execução incompleta ou processo órfão.

______________________________________________________________________

## Escrevendo Testes

### Teste Unitário

```python
import pytest
from globaldatafinance.brazil.cvm.fundamental_stocks_data.core import (
    validate_docs_name,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.errors import (
    InvalidDocumentName,
)


@pytest.mark.unit
class TestValidateDocsName:
    def test_validate_valid_doc(self):
        """Verifica validação de documento válido."""
        validate_docs_name('DFP')  # Passa sem exceção

    def test_validate_invalid_doc(self):
        """Verifica se InvalidDocumentName é lançada para documento inválido."""
        with pytest.raises(InvalidDocumentName):
            validate_docs_name('INVALID')
```

> Tipos e exceções de cada fonte vivem nos módulos da própria fonte: para CVM em `brazil.cvm.fundamental_stocks_data.core` e `brazil.cvm.fundamental_stocks_data.errors`; para B3 a divisão é mais granular — entidades em `models.py`, value objects em `years.py`/`processing.py`, validators de filesystem em `filesystem.py`, asset services em `assets.py`, exceções em `errors.py`.

### Estratégias de Mocking

Para desacoplar chamadas de I/O de rede ou sistema de arquivos, os testes substituem as dependências via stubs com duck typing ou `monkeypatch.setattr`:

```python
from globaldatafinance.brazil.cvm.fundamental_stocks_data.client import (
    DownloadDocumentsUseCaseCVM,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.core import (
    DownloadResultCVM,
)
from globaldatafinance.brazil.cvm.fundamental_stocks_data.http import (
    DownloadTaskCVM,
)


class MockRepository:
    def download_docs(
        self,
        tasks: list[DownloadTaskCVM],
        *,
        automatic_extractor: bool | None = None,
    ) -> DownloadResultCVM:
        return DownloadResultCVM(
            successful_downloads=['DFP_2023', 'ITR_2023'],
            failed_downloads={},
            elapsed_time=0.5,
        )


use_case = DownloadDocumentsUseCaseCVM(MockRepository())
result = use_case.execute(destination_path='/tmp/cvm')
assert result.success_count_downloads == 2
```

### Engines obrigatórios e provas reais

PyArrow é o engine obrigatório de leitura/escrita produtiva. Pandas não é
instalado pela biblioteca e, quando necessário para análise downstream, deve
ser uma dependência explícita do consumidor. Polars também não faz parte do
runtime. Testes unitários podem usar fakes para
colaboradores do próprio projeto, como monitor de recursos, parser ou a seam de
filesystem. Eles não substituem testes de um componente que lê ou grava
Parquet: esse componente também precisa de integrações com PyArrow real,
leitura do artefato e verificação de schema, tipos e limpeza de temporários.

### Teste de Integração

```python
import pytest
from globaldatafinance import FundamentalStocksDataCVM


@pytest.mark.integration
class TestFundamentalStocksDataIntegration:
    def test_get_available_docs(self):
        """Testa obtenção de documentos disponíveis."""
        cvm = FundamentalStocksDataCVM()
        docs = cvm.get_available_docs()

        assert isinstance(docs, dict)
        assert len(docs) > 0
        assert 'DFP' in docs
```

______________________________________________________________________

## Fixtures

```python
import pytest
from pathlib import Path


@pytest.fixture
def temp_dir(tmp_path):
    """Cria diretório temporário para testes."""
    return tmp_path


@pytest.fixture
def sample_zip_file(tmp_path):
    """Cria arquivo ZIP de exemplo."""
    zip_path = tmp_path / 'test.zip'
    # Criar ZIP...
    return zip_path
```

______________________________________________________________________

## Cobertura

Objetivo: **>= 85% de cobertura agregada** (enforced via `fail_under = 85` em
`[tool.coverage.report]` no `pyproject.toml`). Esse é também o piso para
módulos novos.

```bash
# Gerar relatório
uv run --locked --no-sync pytest -m "not slow and not real_data and not perf" \
  --cov --cov-report=term-missing

# Relatório HTML
uv run --locked --no-sync pytest --cov --cov-report=html
open htmlcov/index.html
```

### Cobertura do executor de validação real

Os scripts `real_validation*.py` são código operacional de desenvolvimento e
possuem um gate separado do produto. O hook `real-validation-coverage`, no
estágio `pre-push`, executa os testes determinísticos do executor e exige
`>= 85%` de cobertura agregada, incluindo branches:

```bash
uv run --locked --no-sync pytest -q \
  tests/tooling/test_real_validation.py \
  tests/tooling/test_real_validation_b3.py \
  tests/tooling/test_real_validation_cases.py \
  tests/tooling/test_real_validation_cvm.py \
  tests/tooling/test_real_validation_matrix.py \
  tests/tooling/test_real_validation_report.py \
  tests/tooling/test_real_validation_resume.py \
  tests/tooling/test_real_validation_runner.py \
  tests/tooling/test_real_validation_types.py \
  tests/tooling/test_real_validation_utils.py \
  --cov=scripts.real_validation \
  --cov=scripts.real_validation_b3 \
  --cov=scripts.real_validation_cases \
  --cov=scripts.real_validation_cvm \
  --cov=scripts.real_validation_matrix \
  --cov=scripts.real_validation_report \
  --cov=scripts.real_validation_resume \
  --cov=scripts.real_validation_runner \
  --cov=scripts.real_validation_types \
  --cov=scripts.real_validation_utils \
  --cov-report=term-missing --cov-fail-under=85
```

Esse gate não altera o piso de 85% da cobertura de `src`; ele impede que
timeout, limpeza, relatórios, classificações CVM, paridade B3 ou retomada
percam cobertura sem um sinal separado. A mesma verificação é executada como
passo próprio na pipeline de qualidade.

______________________________________________________________________

## CI/CD

Testes são executados automaticamente em:

- Push para `main` ou `develop`
- Pull Requests
- Releases

______________________________________________________________________

## Próximos Passos

- [Como Contribuir](contributing.md)
- [Arquitetura](architecture.md)
