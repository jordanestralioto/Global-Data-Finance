# Como Contribuir

Guia para contribuir com o projeto Global-Data-Finance.

______________________________________________________________________

## Configurando Ambiente de Desenvolvimento

### 1. Fork e Clone

```bash
# Fork no GitHub, depois:
git clone https://github.com/jordanestralioto/Global-Data-Finance.git
cd Global-Data-Finance
```

### 2. Instalar Dependências

`uv` é o gestor canônico do projeto (`uv.lock` é commitado). O desenvolvimento
usa **Python >=3.12,<4.0**. O workflow atual de CI exercita Python 3.12, 3.13 e
3.14.

```bash
# Sincronizar exatamente o ambiente aprovado pelo lockfile (cria .venv)
uv sync --locked --all-extras --dev

# Para rodar comandos sem sincronização implícita:
uv run --locked --no-sync pytest
uv run --locked --no-sync mypy src
```

### 3. Instalar Pre-commit Hooks

```bash
uv run --locked --no-sync pre-commit install --install-hooks
```

______________________________________________________________________

## Padrões de Código

### Style Guide

- Seguir **PEP 8**
- Usar **type hints** em todo código
- Docstrings no formato **Google Style**
- Máximo de 79 caracteres por linha (ruff, Blue-style formatting)

### Perfis Ruff

O Ruff usa uma seleção base explícita para `src/`, `tests/`, `scripts/` e
`examples/`. O script `scripts/check-ruff-policy.py` é o único entrypoint
interno para os perfis completos: `base` verifica a seleção base, `docs` aplica
as regras Google de docstrings em `src/`, `scripts/` e `examples/` (exceto
`**/__init__.py`) e `security` aplica as regras `S` ao código e aos scripts e
aos testes com somente `S101` ignorado.

A seleção base preserva as regras de simplificação e correção existentes e
adiciona dois contratos focados. `C901` limita a complexidade ciclomática
McCabe a **10 por função**: complexidade 10 é aceita e 11 ou mais falha.
`BLE001`, `TRY203`, `TRY400` e `TRY401` impedem capturas cegas, relançamentos
inúteis e logs que descartem ou repitam o contexto da exceção. O grupo `TRY`
completo e `PLR0912` não fazem parte deste gate.

```bash
# Verificar todos os perfis e a forma da política no pyproject.toml
uv run --locked --no-sync python scripts/check-ruff-policy.py --profile all

# Reproduzir somente o gate de complexidade e exceções
uv run --locked --no-sync ruff check --select C901,BLE001,TRY203,TRY400,TRY401 src tests scripts examples

# Verificar apenas formatação, sem alterar arquivos
uv run --locked --no-sync ruff format --check src tests scripts examples
```

Esta é uma política fechada: o checker rejeita qualquer chave Ruff fora da
forma e dos valores canônicos, inclusive `exclude`, `extend`, `ignore`,
`extend-ignore`, `extend-select`, `extend-per-file-ignores` e tabelas aninhadas
inesperadas. A única exceção por arquivo permitida é `S603` em
`scripts/process_runner.py`, que centraliza a execução de comandos allowlisted,
resolvidos e sem shell para os scripts de tooling. Esses scripts não devem
chamar `subprocess` diretamente.

### Exemplo de Docstring

```python
def download_docs(
    self,
    destination_path: str,
    list_docs: list[str] | None = None,
) -> DownloadResultCVM:
    """Baixa documentos CVM.

    Args:
        destination_path: Diretório onde salvar arquivos.
        list_docs: Lista de tipos de documentos. Se None, baixa todos.

    Returns:
        Objeto DownloadResultCVM com resultados do download.

    Raises:
        InvalidDocumentName: Se tipo de documento for inválido.
        InvalidDestinationPathError: Se o caminho de destino for inválido ou não seguro.
    """
    pass
```

______________________________________________________________________

## Testes

### Executar Testes

```bash
# Todos os testes
uv run --locked --no-sync pytest

# Com cobertura
uv run --locked --no-sync pytest --cov

# Apenas unitários
uv run --locked --no-sync pytest -m unit
```

Antes de abrir PR, rode o pipeline completo:

```bash
uv run --locked --no-sync pre-commit run --all-files --show-diff-on-failure
uv run --locked --no-sync pytest
```

### Quality Gates Locais

O hook `pre-commit` valida o índice staged e mantém a atualização de
dependências fora do fluxo de commit. Ele nunca executa `uv sync`, `uv lock`
ou atualização de versões: `uv lock --check` apenas comprova a coerência atual
do lockfile. O hook `pre-push` executa as verificações mais caras de tipos,
cobertura e vulnerabilidades antes de publicar uma branch.

O hook local do Gitleaks verifica somente o conteúdo staged para manter o
feedback de commit rápido. A CI executa uma varredura adicional em modo de
diretório sobre um checkout limpo, portanto ela não depende de haver arquivos
staged. O `pip-audit` permanece fora do estágio `pre-commit` rápido e é
executado na validação mais pesada de `pre-push` e da CI.

Quando uma dependência precisar mudar, faça isso explicitamente, revise o
diff de `uv.lock`, sincronize o ambiente e só então faça o commit:

```bash
uv lock --upgrade
uv sync --locked --all-extras --dev
git add pyproject.toml uv.lock
```

Os gates de diff, integridade de testes e sintaxe shell examinam apenas o
conteúdo staged durante um commit. O CI executa os mesmos scripts sobre a faixa
de commits da pull request ou do push, portanto um `SKIP` de diff sem arquivos
staged não equivale a aprovação de CI.

`.agents/` permanece rastreado para que cada clone distribua os validadores
portáteis, mas é uma projeção gerada e mantida pelo repositório separado
`central-skills`; seus arquivos gerados nunca devem ser editados manualmente.
Colaboradores comuns e usuários do projeto não precisam instalar
`central-skills`. Um mantenedor que alterar a seleção ou a projeção deve
corrigir a fonte canônica, regenerar com `harness-sync` e executar o check:

```bash
harness-sync --check
```

O hook `check-harness-sync` é manual e somente para mantenedores que possuem o
executável opcional instalado. Ele não participa dos estágios padrão de
`pre-commit`, `pre-push` ou da CI; se o executável não existir, o check falha
explicitamente em vez de produzir um `SKIP` enganoso.

Os hooks genéricos recebem uma exclusão explícita para `.agents/`, `.claude/`,
`.codex/`, `.opencode/` e `.github/prompts/`. Portanto, eles não formatam nem
analisam essas projeções. Os validadores rastreados dentro de `.agents/` são a
exceção deliberada: podem ser executados diretamente do clone e não dependem
de uma instalação externa. A ausência do executável opcional de sincronização
não bloqueia commits ou pushes normais; falhas reais dos validadores devem ser
corrigidas, nunca contornadas desativando os hooks.

### Escrever Testes

```python
import pytest
from globaldatafinance import FundamentalStocksDataCVM

@pytest.mark.unit
class TestFundamentalStocksData:
    def test_get_available_docs(self):
        """Testa obtenção de documentos disponíveis."""
        cvm = FundamentalStocksDataCVM()
        docs = cvm.get_available_docs()

        assert isinstance(docs, dict)
        assert "DFP" in docs
        assert len(docs) > 0
```

______________________________________________________________________

## Workflow Git

### Branches

- `main`: Código estável
- `develop`: Desenvolvimento
- `feature/nome-feature`: Novas funcionalidades
- `fix/nome-bug`: Correções de bugs

### Commits

Use mensagens descritivas:

```bash
# Bom
git commit -m "feat: add asynchronous parallel worker pool for CVM downloads"
git commit -m "fix: resolve socket timeout during multi-year COTAHIST extraction"

# Evite
git commit -m "update"
git commit -m "fix bug"
```

### Pull Requests

1. Crie branch a partir de `develop`
2. Faça suas alterações
3. Adicione testes
4. Atualize documentação
5. Abra PR para `develop`

______________________________________________________________________

## Checklist de PR

- [ ] Código segue PEP 8
- [ ] Type hints adicionados
- [ ] Docstrings completas
- [ ] Testes adicionados
- [ ] Testes passando
- [ ] Documentação atualizada
- [ ] Pre-commit hooks passando

______________________________________________________________________

## Contato

- GitHub Issues: [Abrir issue](https://github.com/jordanestralioto/Global-Data-Finance/issues)
- Email: estraliotojordan@gmail.com
