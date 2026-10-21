# Testes

Use o ambiente preparado no [guia de contribuição](contributing.md). O gate
padrão combina testes unitários e integrações determinísticas; cada teste cria
suas próprias entradas locais.

## Executar o gate padrão

```bash
uv run --locked --no-sync pytest -m "not slow and not real_data and not perf" \
  --cov --cov-report=xml --cov-report=term-missing
```

Para uma mudança localizada, comece pelo módulo afetado, por exemplo:

```bash
uv run --locked --no-sync pytest tests/application/b3_docs
```

`pytest.ini` define descoberta e marcadores; `pyproject.toml` define cobertura.
Para o relatório HTML, acrescente `--cov-report=html` ao comando com cobertura.

## Classificar cada teste

Todo teste tem **exatamente um tier primário**:

| Tier | Contrato |
| --- | --- |
| `unit` | Comportamento isolado, com colaboradores puros, fakes ou stubs. |
| `integration` | Vários componentes reais e filesystem local determinístico. |
| `perf` | Benchmark ou medição de recursos; sempre opt-in. |

Use `slow` para cenários pesados e `asyncio` para execução assíncrona.
`real_data` exige `integration`, usa COTAHIST fornecido pelo chamador e é
opt-in. Esses qualificadores não substituem o tier.

```bash
uv run --locked --no-sync pytest -m unit
uv run --locked --no-sync pytest -m "integration and not slow and not real_data"
uv run --locked --no-sync pytest tests/perf -m perf -o addopts=''
```

O comando com `-m` substitui a seleção padrão; use qualificadores explícitos
para manter cenários externos e lentos fora da execução desejada.

## Escrever testes úteis

- Espelhe a fronteira afetada: `tests/application/`, a fonte em `tests/brazil/`
  ou as fundações compartilhadas. Subdiretórios organizam assuntos.
- Prove comportamento, limites, transições e regressões com resultados
  observáveis; contagem de linhas cobertas não substitui uma asserção útil.
- Use `tmp_path` e entradas ZIP, CSV ou Parquet criadas pelo teste. Substitua
  rede com `httpx.MockTransport` ou colaboradores locais.
- Leitura e escrita Parquet precisam também de provas com PyArrow real,
  schema, tipos, conteúdo e limpeza de temporários. Pandas e Polars não são
  dependências de runtime da biblioteca.
- Documente exclusões e consolidações em `.test-integrity-policy.json`.

O gate estrutural abaixo verifica tiers e observações no corpo do teste;
ele é heurístico e não comprova a qualidade semântica das asserções:

```bash
uv run --locked --no-sync python scripts/check_test_quality.py
```

## Usar COTAHIST local

Dados oficiais ficam em um diretório do chamador, como `cotahist_b3_local/`,
ignorado pelo Git. Os testes não baixam esses arquivos nem leem `.env`
implicitamente. Defina os caminhos e o ano explicitamente:

```bash
COTAHIST_PATH=./cotahist_b3_local COTAHIST_TEST_YEAR=2023 \
  uv run --locked --no-sync pytest -m "real_data and not slow"
COTAHIST_PATH=./cotahist_b3_local COTAHIST_TEST_YEAR=2023 \
  uv run --locked --no-sync pytest -m "real_data and slow"
```

A primeira seleção não gera Parquet, mas a fixture atual faz preflight completo
de todos os anos do catálogo, incluindo hashes e validação de cada registro.
Mesmo com `not slow`, esse preparo pode ler integralmente arquivos grandes.
As provas de extração, incluindo amostra, validação anual e paridade
`fast`/`slow`, são `slow`. A auditoria completa usa um decoder independente.

A fixture inspeciona todo o catálogo antes de selecionar o ano. Sem
`COTAHIST_PATH`, a suíte selecionada é pulada. Com a variável definida, entrada
inválida, vazia, ilegível ou sem o ano pedido falha. Um ano único pode ser
inferido; com vários, `COTAHIST_TEST_YEAR` é obrigatório e tem quatro dígitos.
ZIP tem precedência sobre TXT. Os membros internos aceitam o nome moderno
`COTAHIST_A{YYYY}.TXT` e os históricos `COTAHIST.A{YYYY}` e
`COTAHIST_A{YYYY}`, sempre com o ano correspondente.

`cotahist_b3/` contém apenas as amostras sintéticas versionadas dos exemplos,
geradas por `scripts/generate_example_cotahist.py`. Elas são testadas em
`tests/examples` sem `real_data`. Um dataset anual oficial só poderá se tornar
obrigatório na CI após existir uma fixture versionada ou artefato publicado
com licença compatível.

## Cobertura e CI

O produto exige **85% de cobertura agregada de `src/`, incluindo branches**.
O executor de validação real tem um piso separado de 85%, também com branches.
Para executar seu gate sem copiar a lista de módulos e opções:

```bash
uv run --locked --no-sync pre-commit run real-validation-coverage \
  --hook-stage pre-push --all-files
```

A matriz de qualidade roda em Python 3.12, 3.13 e 3.14. As configurações
canônicas são `pyproject.toml`, `pytest.ini`, `.pre-commit-config.yaml` e
`.github/workflows/pipeline.yml`. O [aceite de release](release-readiness.md)
acrescenta evidências nativas em Windows/macOS, falhas de publicação e pacotes.

## Auditar dados externos

A campanha completa de CVM/COTAHIST é opt-in e pode levar horas. Use o
[guia de validação com dados externos](real-data-validation.md) para executá-la,
interpretar relatórios e retomar uma campanha. Ela não faz parte do gate
local determinístico.
