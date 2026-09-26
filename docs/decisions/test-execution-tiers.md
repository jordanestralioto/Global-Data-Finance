# Níveis de execução de testes e validação local do COTAHIST

**Status:** Aceita
**Data:** 2026-08-30
**Escopo:** testes e quality gates do repositório

## Decisão

O conjunto de testes usa exatamente um tier primário por teste:

- `unit`: comportamento isolado, com funções puras, fakes, stubs ou
  colaboradores locais controlados;
- `integration`: fluxo que atravessa dois ou mais componentes reais de
  produção, incluindo filesystem, ZIP, CSV, Parquet e `tmp_path` determinísticos;
- `perf`: benchmark ou medição de tempo, memória ou recursos, sempre opt-in.

`unit` e `integration` são mutuamente exclusivos. O checker estrutural
`scripts/check_test_quality.py` rejeita teste sem tier ou com mais de um tier.
Ele é uma proteção estrutural e heurística: verifica a classificação e a
presença de uma observação aceita no corpo executável direto do teste, sem
descer em helpers, lambdas ou classes aninhadas. Não substitui a revisão de que
uma asserção protege uma regressão nem prova ausência de todas as tautologias
semânticas.

Os marcadores `slow`, `asyncio` e `real_data` são qualificadores ortogonais:

- `slow` identifica trabalho pesado ou sensível a tempo;
- `asyncio` identifica a necessidade do plugin assíncrono;
- `real_data` identifica uso de um COTAHIST pertencente ao chamador e só pode
  aparecer com o tier `integration`.

O gate determinístico padrão é:

```bash
uv run --locked --no-sync pytest -m "not slow and not real_data and not perf" \
  --cov --cov-report=xml --cov-report=term-missing
```

Integrações criadas pelo repositório permanecem nesse gate quando não são
`slow` nem `real_data`. A suíte de performance e a suíte que lê dados reais
ficam fora do gate padrão:

```bash
uv run --locked --no-sync pytest -m unit
uv run --locked --no-sync pytest -m "integration and not slow and not real_data and not perf"
uv run --locked --no-sync pytest tests/perf -m perf -o addopts=''
```

## COTAHIST local

O diretório configurado em `COTAHIST_PATH` é sempre caller-owned.
`cotahist_b3/` é ignorado pelo Git e não é baixado pela suíte. A fixture da
suíte `tests/brazil/b3_data/historical_quotes/integration/test_real_cotahist.py`
aplica estas regras:

1. Sem `COTAHIST_PATH`, somente a suíte explicitamente selecionada com
   `-m real_data` é pulada, com instrução acionável. O gate padrão não a
   seleciona.
2. Com `COTAHIST_PATH`, caminho inexistente, ilegível, vazio, sem um arquivo
   `COTAHIST_A{YYYY}.ZIP` ou `COTAHIST_A{YYYY}.TXT` válido, ou sem o ano
   solicitado, causa falha; não causa skip.
3. `COTAHIST_TEST_YEAR`, quando presente, deve ter exatamente quatro dígitos.
   Sem ele, a fixture infere o ano somente se o catálogo tiver um único ano;
   com vários anos, falha com instrução acionável e nunca escolhe o maior ano.
4. A extração recebe o ano resolvido explicitamente. Nunca usa o ano corrente
   do sistema nem baixa dados durante o teste.
5. O catálogo inspeciona todos os arquivos externos disponíveis, seus anos,
   central directories, limites ZIP e resolução do membro interno, sem
   processar integralmente todos os registros.
6. A paridade limitada cria uma amostra não vazia de até 20.000 registros
   reais `01` no `tmp_path` e compara `fast` e `slow` pelas 20 colunas, dtypes
   e ordenação determinística exatos. Como executa os dois modos, ela é
   marcada `slow`.
7. Uma prova anual em `fast` valida o schema Arrow, a contagem de registros e
   os limites de data. Outra prova anual `slow` compara contagens, schema e
   igualdade de tabela ou digest lógico entre `fast` e `slow`.

Para executar a verificação do catálogo e as provas de processamento:

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

## Gatilho para dados oficiais

Uma futura amostra anual oficial só se torna obrigatória no CI quando houver
uma decisão explícita de release que forneça um fixture versionado no
repositório ou um artefato de CI publicado sob licença compatível. Antes desse
gatilho, dados oficiais permanecem opt-in e caller-owned. A adoção obrigatória
deve atualizar simultaneamente a licença/proveniência, o schema esperado, o
fixture de CI, o job correspondente e esta decisão.

## Consequências e não objetivos

Esta decisão torna a seleção de testes previsível, mantém o CI determinístico
e permite validação de paridade sem incorporar dados financeiros externos ao
Git. Ela não altera a API pública, assinaturas de facades, semântica de
extração, nomes de saída ou schema persistido da biblioteca.
