# Como contribuir

Use Python `>=3.12,<4.0`, Git e uv. Crie a branch a partir de `develop` e
abra o pull request para essa mesma branch.

## Preparar o ambiente

```bash
git clone https://github.com/jordanestralioto/Global-Data-Finance.git
cd Global-Data-Finance
uv sync --locked --all-extras --dev
uv run --locked --no-sync pre-commit install --install-hooks
git switch -c fix/cotahist-validation develop
```

`uv sync` prepara o ambiente uma vez. Depois disso, execute as ferramentas com
`uv run --locked --no-sync` para usar as dependências já resolvidas.

## Fazer a alteração

- Siga a [arquitetura](architecture.md): comportamento CVM e B3 pertence à
  respectiva fonte; compartilhe apenas o que for reutilizável.
- Preserve assinaturas, resultados, exceções e schemas públicos. Mudanças
  incompatíveis exigem uma decisão explícita e migração documentada.
- Use nomes, código, comentários e commits em inglês. Anote tipos, use
  docstrings Google e mantenha o formato Ruff de 79 caracteres.
- Use `_` para helpers restritos ao módulo. Um nome compartilhado entre
  módulos não se torna, por isso, parte da API pública. Mantenha estado mutável
  privado e exponha operações quando outro módulo precisar acessá-lo.
- Valide entradas e caminhos antes de escrever. Preserve as causas das falhas.
- Atualize testes que comprovem o comportamento e a regressão, e mantenha as
  páginas de produto em português e inglês.

## Validar antes do PR

```bash
uv run --locked --no-sync pre-commit run --all-files --show-diff-on-failure
uv run --locked --no-sync pytest
```

O pytest padrão seleciona testes determinísticos. Para cobertura, marcadores,
integrações e dados locais, use o [guia de testes](testing.md).

| Mudança | Validação adicional |
| --- | --- |
| Código Python | `uv run --locked --no-sync mypy src --pretty` |
| Documentação | `uv run --locked --no-sync mkdocs build --strict` |
| Empacotamento | `uv build` e [aceite de release](release-readiness.md) |

Os hooks instalados distribuem as verificações por custo:

| Estágio | O que verifica |
| --- | --- |
| `pre-commit` | Integridade do diff, lockfile, sintaxe, formatação, lint e contratos. |
| `commit-msg` | Formato Conventional Commits. |
| `pre-push` | Tipos, testes com cobertura e auditoria de dependências. |

As entradas canônicas ficam em `.pre-commit-config.yaml` e `pyproject.toml`.
Para reproduzir o estágio completo de push, execute
`uv run --locked --no-sync pre-commit run --hook-stage pre-push --all-files`.
Os gates de diff durante o commit inspecionam o índice; na CI, inspecionam o
intervalo cumulativo desde a release anterior. Sem alterações staged, gates
baseados em diff podem retornar `SKIP` mesmo com `--all-files`; isso não
comprova aprovação desses gates. O Gitleaks local examina o índice; a CI também
verifica o checkout completo.

## Enviar o PR

Revise o diff e adicione somente os caminhos da alteração. Formatação automática
precisa ser revisada antes de entrar no índice.

```bash
git commit -m "fix: validate COTAHIST inputs before writing"
```

Descreva o problema, o comportamento final, os comandos de validação e os checks
pulados ou dependentes de ambiente externo. Para exclusões ou consolidações de
testes, registre a justificativa em `.test-integrity-policy.json`.

## Dependências e tooling interno

Altere dependências deliberadamente com uv e revise `pyproject.toml` e `uv.lock`.
Não edite o lockfile à mão. Os hooks validam a resolução; atualizações e
sincronização do ambiente ficam fora do commit.

As projeções de agentes em `.agents/`, `.claude/`, `.codex/` e `.opencode/`
são mantidas pelo repositório `central-skills`. Altere a fonte e regenere em
vez de editar os arquivos gerados. `harness-sync --check` é um check manual de
mantenedores; colaboradores comuns não precisam instalar essa ferramenta.

Para reportar vulnerabilidades, siga a
[política de segurança](https://github.com/jordanestralioto/Global-Data-Finance/blob/develop/SECURITY.md).
