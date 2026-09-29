# Descoberta de fontes e instruções ativas

## Descubra a cadeia da sessão

Comece pelo diretório de início da sessão, não apenas pela raiz Git:

```bash
pwd
git rev-parse --show-toplevel
```

Registre o alvo exato e o diretório atual. Leia as instruções que o cliente
aplica entre a raiz e o diretório de início, além das instruções globais que o
cliente declara aplicáveis. Confira `AGENTS.override.md` e `AGENTS.md` nos
diretórios relevantes. A ordem de precedência e o modo como arquivos globais
entram na cadeia dependem do cliente.

Considere um nome alternativo somente quando a configuração ou a documentação
do cliente confirma que ele é carregado. No Codex, verifique
`project_doc_fallback_filenames`; nomes de exemplo incluem `TEAM_GUIDE.md` e
`.agents.md`. Outros clientes podem reconhecer nomes como `CLAUDE.md`,
`GEMINI.md` ou `.github/copilot-instructions.md`, mas não os trate como ativos
sem confirmação para o cliente e repositório alvo. A existência de um arquivo,
inclusive `CLAUDE.md`, não prova que ele foi carregado ou que é a fonte
canônica.

Identifique o limite de tamanho ou profundidade configurado e o que acontece
quando a cadeia o alcança. Para Codex, consulte a configuração atual de
`project_doc_max_bytes`; a documentação oficial informa um padrão de 32 KiB,
ajustável pela configuração. Não copie esse padrão para outro cliente nem
declare todo arquivo descoberto como contexto carregado. Consulte
[Custom instructions with AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)
para o comportamento e as opções atuais do Codex.

Ao editar instruções aninhadas, preserve a herança: o root guarda regras comuns;
um arquivo local contém apenas diferenças da subárvore. Se a cadeia ativa ou o
limite de contexto não puderem ser confirmados, descreva a incerteza em vez de
adivinhar a precedência.

## Confirme fatos do projeto

Faça uma descoberta limitada ao caminho que a solicitação requer:

1. Leia o `AGENTS.md` alvo e seus ancestrais aplicáveis antes de propor texto.
2. Localize README, onboarding, governança e `CODEOWNERS` quando existirem.
3. Inspecione manifests, lockfiles, configurações, entrypoints, CI e comandos
   owner para confirmar stack, ownership e validação.
4. Abra código ou testes apenas para resolver uma afirmação necessária, não para
   inventariar o repositório inteiro.
5. Mapeie o caminho inicial, o owner dos detalhes e o próximo documento útil.

Comandos úteis para listar candidatos sem assumir uma stack:

```bash
rg --files -g 'AGENTS.md' -g 'AGENTS.override.md' -g 'README*' -g 'CONTRIBUTING*' -g 'CODEOWNERS'
rg --files -g 'pyproject.toml' -g 'package.json' -g 'Cargo.toml' -g 'go.mod' -g 'pom.xml' -g 'build.gradle*' -g '*.csproj' -g '*.sln' -g 'Gemfile' -g 'composer.json' -g 'Package.swift' -g 'Makefile' -g 'Taskfile*' -g '.github/workflows/*'
```

Use `--help`, listagem de tasks e checks secos para confirmar sintaxe quando o
comando for seguro. Não execute build, deploy, migração ou acesso externo só
para decidir o que escrever.

## Fontes por tipo de afirmação

| Afirmação               | Fontes fortes                                                         | Não basta isoladamente                            |
| ----------------------- | --------------------------------------------------------------------- | ------------------------------------------------- |
| Objetivo e consumidores | README atual, metadados de pacote, entrypoint, configuração de deploy | Nome de diretório                                 |
| Owner ou boundary       | Governança, `CODEOWNERS`, arquitetura aceita, wiring e testes         | Autor mais frequente no Git                       |
| Comando oficial         | Manifest ou task runner junto de CI ou documentação operacional atual | Exemplo antigo                                    |
| Manager e lockfile      | Configuração de workspace, manifest, lockfile e CI                    | Ferramenta instalada localmente                   |
| Framework atual         | Manifest, imports estruturais, entrypoint e configuração              | Dependência transitiva                            |
| Idioma de código e docs | Política de contribuição ou decisão explícita                         | Idioma casual da conversa ou maioria dos arquivos |
| Métrica de qualidade    | SLO, configuração, gate, teste ou observabilidade já adotados         | Sugestão genérica                                 |
| Documento canônico      | Governança, portal ou metadado de status                              | Estar dentro de `docs/`                           |

Arquivos de `.env`, cofres, tokens, chaves e sessões não são fontes para o
documento. Leia exemplos sem expor valores secretos.

## Quando fontes divergem

Registre cada caminho e a afirmação que ele sustenta. Não escolha silenciosamente
entre README, manifest, CI ou política concorrentes. Continue fatos independentes
e explique a divergência que ainda muda a orientação. Peça uma decisão quando
ela for necessária para escrever a próxima regra corretamente.
