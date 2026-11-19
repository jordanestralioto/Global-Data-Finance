# Como contribuir

Use Python `>=3.12,<4.0`, Git e uv. Crie a branch a partir de `develop` e
abra o pull request para essa mesma branch.

## Preparar o ambiente

```bash
git clone https://github.com/jordanestralioto/Global-Data-Finance.git
cd Global-Data-Finance
uv sync --locked --all-extras --dev
uv run --locked --no-sync pre-commit install --install-hooks
uv run --locked --no-sync python scripts/check_push_snapshot.py --install
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

Rascunhos e registros de trabalho locais ficam em `docs/internal/`. Esse
diretório é ignorado pelo Git e excluído do `check-docs-contracts`, incluindo
a exigência de tradução para inglês, e do build do MkDocs.

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
| `pre-push` | Snapshot enviado, tipos, testes com cobertura e auditoria de dependências. |

As entradas canônicas ficam em `.pre-commit-config.yaml` e `pyproject.toml`.
Para reproduzir o estágio completo de push, execute
`uv run --locked --no-sync pre-commit run --hook-stage pre-push --all-files`.
No `git push`, toda ref enviada com commits novos precisa apontar para o
checkout atual, e esse checkout precisa ser exatamente o commit: sem mudanças
staged ou não staged, sem arquivos não rastreados, sem arquivos rastreados
ocultos por `assume-unchanged` ou `skip-worktree` (como num checkout esparso) e
sem fontes Python ou configurações de ferramentas ignoradas que os testes
possam carregar. Do contrário, os testes validariam outro snapshot. Num push
incremental, o pre-commit guarda as mudanças rastreadas não staged em stash
antes dos hooks e as restaura depois; os hooks validam então o índice. Quando o
push inclui o commit raiz, como o primeiro push para um remoto vazio, não há
stash e o `push-snapshot` recusa essas mudanças. O pre-commit repassa aos hooks
apenas a primeira ref do push. Por isso, o comando
`scripts/check_push_snapshot.py --install` instala um validador que o
pre-commit executa antes dos hooks, com a lista completa de refs de cada push;
ele não guarda estado entre pushes. O primeiro hook (`push-snapshot`) exige
esse validador, confere a primeira ref e o checkout e, sem o validador, falha
com o comando de instalação. Quando a ref recusada não é a primeira, o
pre-commit ainda executa os hooks antes de o Git recusar o push; interrompa com
Ctrl+C para não esperar. Envie cada branch a partir do próprio checkout limpo.
O pre-commit e o validador consideram novos apenas os commits ausentes das refs
de rastreamento locais (`refs/remotes/<remoto>/`). Se essas refs estiverem
desatualizadas, por exemplo depois de restaurarem o remoto ou apagarem uma
branch nele, um commit que elas ainda contêm é publicado sem executar os hooks.
Nesses casos, execute `git fetch --prune <remoto>` antes do push.
A reprodução manual acima informa `SKIP` nesse hook e cobre o working tree.
Ruff, detect-secrets e mdformat rodam nos hooks pelo ambiente do `uv.lock`, nas
versões da CI.
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
sincronização do ambiente ficam fora do commit. Quando uma alteração em
`pyproject.toml` muda as dependências declaradas, como ao adicionar ou remover
uma, `uv lock --check` constrói os metadados do projeto com hatchling e
hatch-vcs. Sem esses pacotes no cache do uv, a verificação precisa acessar o
índice de pacotes. Sem rede, ela falha como erro de infraestrutura e bloqueia o
commit até ser repetida com rede ou com o cache já preenchido. Alterações que
preservam as dependências, como a da descrição, não precisaram desses pacotes
no uv 0.13.7.

As projeções de agentes em `.agents/`, `.claude/`, `.codex/` e `.opencode/`
são mantidas pelo repositório `central-skills`. Altere a fonte e regenere em
vez de editar os arquivos gerados. `harness-sync --check` é um check manual de
mantenedores; colaboradores comuns não precisam instalar essa ferramenta. Os
hooks de formatação não alteram `.agents/`. Os scanners de segredo, os
validadores somente leitura, o `diff-sanity` e o `shell-syntax` inspecionam
essa projeção, porque hooks executam scripts dela. O `diff-sanity` só não aplica
a ela as regras de debug e stubs, já que os CLIs do harness imprimem por
design.

Para reportar vulnerabilidades, siga a
[política de segurança](https://github.com/jordanestralioto/Global-Data-Finance/blob/develop/SECURITY.md).
