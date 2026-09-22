# Contrato de conteúdo para `AGENTS.md`

## Sumário

- Estrutura fixa e metadados com fallbacks explícitos.
- Função obrigatória de cada seção.
- Separação entre baseline, fatos, políticas e preferências.
- Navegação por progressive disclosure.
- Critérios para draft, aprovação e canonicalidade.

## Estrutura fixa

Use os headings de nível 2 abaixo, exatamente nesta ordem:

1. `## System Overview`
2. `## Success Metrics`
3. `## Pipeline Architecture`
4. `## Configuration & Runtime`
5. `## Technical Stack`
6. `## Mandatory Rules`
7. `## Execution Policy`
8. `## Related Documentation`

`Configuration & Runtime` contém `### Commands`. `Execution Policy` contém, na
ordem: `### Precedence`, `### Secrets`,
`### Repo Alignment`, `### Autonomy`, `### Validation`,
`### Execution Safety` e `### Failure Handling`.

Não renomeie `Pipeline Architecture` em projetos que não sejam pipelines: a
estrutura é fixa. Nesse caso, descreva o fluxo real de request, runtime, build,
eventos ou processamento e diga claramente qual modelo se aplica.

## Classes de conteúdo

| Classe              | Pode materializar?              | Fonte exigida                                      | Exemplos                                              |
| ------------------- | ------------------------------- | -------------------------------------------------- | ----------------------------------------------------- |
| `PORTABLE_BASELINE` | sim, do template bundled        | template                                           | segurança, qualidade geral e limites operacionais     |
| `REPO_FACT`         | sim                             | código, manifest, CI, teste ou doc vigente         | stack, versão, comando, entrypoint, fluxo, consumidor |
| `REPO_POLICY`       | sim                             | instrução, governança, ownership ou decisão aceita | idioma obrigatório, branching, boundaries, manager    |
| `USER_PREFERENCE`   | sim, se compatível com os fatos | declaração explícita do usuário                    | idioma de chat, ferramenta preferida, clean cutover   |
| `USER_DECISION`     | sim                             | aprovação explícita                                | owner, status, escolha entre fontes conflitantes      |
| `EXPLICIT_UNKNOWN`  | somente via fallback            | busca registrada sem resultado                     | `Unassigned`, `Not documented`                        |
| `CONFLICT`          | não como verdade resolvida      | fontes/autoridades divergentes                     | README e CI discordam; preferência exige migração     |

Todo comentário `AGENTS_AUTHOR` é uma instrução de geração e deve desaparecer do
arquivo final. Os blocos já preenchidos de `Mandatory Rules` e `Execution Policy`
são `PORTABLE_BASELINE`; podem ser fortalecidos, mas não silenciosamente
reduzidos.

## Resultado mínimo por seção

### `System Overview`

Responda em prosa curta:

- qual é o nome e a missão do sistema;
- quem ou o que o consome;
- quais entradas e saídas definem sua boundary;
- quais invariantes e prioridades orientam decisões;
- quais componentes adjacentes estão fora do escopo.

Fontes aceitáveis: README vigente, metadados de package, entrypoints, arquitetura
aceita, deploy config e runtime. Se a missão só puder ser observada parcialmente,
escreva a parte comprovável e mantenha Draft.

### `Success Metrics`

Inclua somente targets já adotados pelo projeto: SLOs, thresholds de gate,
critérios de release, limites de qualidade ou invariantes mensuráveis. Use SLO,
config, CI, testes, observabilidade ou contratos aceitos. Recomendações genéricas
como “100% de qualidade” não são métricas.

Sem targets confirmados, use uma linha `Project-owned metrics | Not documented`
e mantenha Draft.

### `Pipeline Architecture`

Explique o caminho executável desde o entrypoint até outputs ou efeitos. Nomeie
componentes principais, boundaries, gates e ownership. Depois escreva a rota de
navegação:

1. primeiro arquivo para visão macro;
2. documento ou módulo owner dos detalhes;
3. fonte operacional para executar ou diagnosticar;
4. fonte de decisões permanentes, quando existir.

Use código, manifests, deploy config, ADRs aceitos e docs vigentes. Não deduza
camadas pelos nomes de diretório. Um inventário sem fluxo e sem “onde começar”
não satisfaz esta seção.

Preserve paths concretos quando forem âncoras estáveis de alto roteamento, como
facade ou entrypoint público, composition root, factory/registry, owner de
extensão e gate canônico. Isso não é inventário: essas âncoras definem onde o
agente começa, implementa, registra ou valida. Omita a anatomia interna que não
muda nenhuma dessas decisões.

### `Configuration & Runtime`

A tabela de superfícies deve incluir, quando existirem:

- objeto ou arquivo de configuração;
- runtime e versão;
- dependency manager, lockfile e workspace config;
- framework config e entrypoint;
- environment examples e nomes de variáveis públicas;
- deploy, container ou migration config.

A tabela `Commands` deve nomear comandos oficiais de setup, run, format, lint,
typecheck, testes, validação, build e docs conforme aplicável. Confirme-os em
manifests, task runners, CI ou documentação operacional vigente. Não execute um
comando com side effects apenas para descobri-lo.

### `Technical Stack`

Liste explicitamente:

- linguagens e versões;
- runtime e dependency manager;
- framework principal e bibliotecas estruturais;
- data/database/queue quando centrais;
- formatter, linter, typechecker e test framework;
- tooling de segurança, build, deploy e documentação.

Inclua valores pequenos e estáveis de formatter/linter quando eles restringirem
diretamente novas implementações, como largura de linha, estilo de aspas,
convenção de docstrings ou limite de complexidade. Deixe seleções extensas de
regras e exceções na configuração owner.

Omitir uma categoria inexistente é correto. Esconder stack confirmada atrás de
“use o tooling do projeto” não é.

### `Mandatory Rules`

Esta seção é a política diária de desenvolvimento. Ela contém três camadas, na
ordem:

1. todas as regras gerais já preenchidas no template (disciplina de engenharia,
   fatoração coesa, zero duplicação, ausência de imports circulares, escopo estrito,
   testes com prova de comportamento, ceticismo e verificação empírica);
2. perfil operacional resolvido do usuário e do projeto;
3. invariantes, boundaries e rotas específicas do sistema.

O perfil operacional deve nomear valores exatos para idioma, manager/runner,
framework/padrão de contribuição e quality gates. Se um item realmente não
existir, registre isso no relatório. Se existir mas ainda não tiver autoridade
para virar política, mantenha Draft e peça a decisão; não deixe regra vaga.

As regras específicas devem ser duráveis e decisórias. Bons exemplos de classes
de regra:

- imutabilidade, idempotência ou determinismo de dados;
- ownership de schemas, contratos e aliases;
- boundary de autenticação/autorização;
- uso obrigatório de abstração/framework já adotado;
- clean cutover versus compatibilidade exigida;
- documento inicial para arquitetura e owner dos detalhes.

Detalhes de função, lista extensa de módulos e procedimentos incidentais
pertencem aos documentos owner, não a esta seção. Paths de alto roteamento e
regras de extensão são diferentes: mantenha-os quando evitarem que o agente
edite a camada errada, omita um registro/export ou use o gate incorreto.

### `Execution Policy`

Preserve o baseline completo do template. A seção regula como o agente age, não
o domínio do sistema. Ela deve manter:

- precedência explícita;
- lista concreta de Git destrutivo, remote piping, escrita fora do escopo e
  bypass de controles;
- proteção e tratamento de exposição de segredos;
- alinhamento a contratos e stop rule para fontes divergentes;
- critérios objetivos de autonomia;
- validação repo-native e obrigação de declarar skips/falhas;
- dry run, inspeção de target e legibilidade de ações perigosas;
- fail-closed em locks de segurança, permissão e autenticação.

Política superior pode fortalecer o texto. Remoção ou relaxamento precisa de
fonte, justificativa e autoridade; preferência do usuário não pode autorizar uma
violação de segurança ou de permissão.

### `Related Documentation`

Ordene por progressive disclosure e diga quando abrir cada fonte. Um conjunto
completo, quando existir, normalmente cobre: orientação, onboarding,
arquitetura, manual de código, operações, runbooks, referência de contratos,
testes, governança e decisões.

Inclua apenas caminhos existentes. Reproduza classes documentadas; sem taxonomia,
use `Unclassified`. Identifique fontes planejadas, geradas, exploratórias,
internas, arquivadas ou não canônicas quando o próprio repositório sustentar essa
classificação. Nunca invente autoridade pelo nome do diretório.

## Tabelas obrigatórias

Mantenha estes headers, mesmo quando uma linha precisar usar `Not documented`:

```markdown
| Metric | Target |
| Surface | Location | Purpose |
| Action | Command |
| Doc | Knowledge class | Purpose |
```

Não use `Not documented` para esconder busca incompleta. O relatório final deve
listar categorias inspecionadas e decisões ainda pendentes.

## Precedência factual

Use primeiro a precedência declarada pela governança do alvo. Sem ela, aplique
este fallback apenas para decidir fatos técnicos:

1. comportamento implementado, manifests, lockfiles, CI e testes executáveis;
2. decisões arquiteturais aceitas e documentação marcada como vigente;
3. documentação de orientação sem status explícito;
4. planos, RFCs, proposals e mudanças ainda não implementadas;
5. outputs locais, debug, exemplos e material gerado.

Essa ordem não resolve conflito de política por conta própria. Divergência sobre
segurança, owner, comando oficial, idioma obrigatório, manager, contrato público
ou topologia recebe `CONFLICT` e decisão explícita.

## Estado de conclusão

- `Draft`: contém fallback, conflito pendente, perfil operacional essencial
  incompleto ou ainda não recebeu aprovação.
- `Ready for approval`: estrutura, fatos, navegação e política foram validados,
  sem conflito material, mas canonicalidade depende de autoridade humana ou
  organizacional.
- `Confirmed`: owner e status foram confirmados, o perfil operacional está
  completo e os gates relevantes passaram.

O validador estrutural não concede esses estados. O relatório deve declarar a
evidência para o estado escolhido.
