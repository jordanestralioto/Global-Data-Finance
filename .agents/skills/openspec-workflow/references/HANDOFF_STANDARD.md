# HANDOFF STANDARD

Este é o contrato de autoria para changes `spec-driven`. Os artefatos são
escritos integralmente em inglês para um desenvolvedor júnior que conhece
somente `AGENTS.md` e a documentação canônica ligada por ele. O texto precisa
eliminar decisões implícitas; clareza para um especialista não basta.

## Lifecycle e gates

| Momento                                    | Comando obrigatório                                     | Escopo                                            |
| ------------------------------------------ | ------------------------------------------------------- | ------------------------------------------------- |
| depois de um `/opsx:continue`              | `opsx-handoff --mode artifact --artifact <id> <change>` | somente o artefato criado                         |
| fim de `/opsx:ff` e antes de `/opsx:apply` | `opsx-handoff --mode bundle <change>`                   | bundle apply-ready completo                       |
| antes de sucesso do `apply`                | `opsx-handoff --mode apply <change>`                    | bundle, tarefas, paths e evidência mecânica atual |
| no `verify` e antes de archive             | `opsx-handoff --mode completion <change>`               | apply, evidência semântica e sync exato           |

`continue` cria exatamente um artefato. `ff` é a rota para criar o bundle
inteiro. `explore` é read-only. Apply nunca antecipa completion. Um erro do completion gate bloqueia archive e
não admite confirmação interativa.

O gate implementado hoje suporta somente `schema: spec-driven`. Outro schema
falha explicitamente em vez de receber validação parcial ou enganosa.

## Proposal

`proposal.md` contém seções não vazias `## Why`, `## What Changes`,
`## Non-Goals` e `## Impact`.

- `Why` descreve primeiro o defeito observável.
- `Non-Goals` nomeia comportamento e caminhos vizinhos que permanecem fora.
- `Impact` cita caminhos concretos do repositório, fronteiras e consumidores.
- Toda capability declarada recebe sua delta spec.

## Delta specs

Cada heading `### Requirement:` contém `SHALL` ou `MUST` e descreve um único
comportamento testável. Cada cenário tem seu próprio `WHEN` e `THEN`; tokens em
outro cenário não completam um cenário incompleto.

Os títulos usam uma categoria explícita:

```markdown
#### Scenario: [happy] Recorded discount is preserved
- WHEN a cancelled order has a recorded discount of `10.00`
- THEN the stored discount remains `10.00`
```

Cada requisito cobre `[happy]`, `[negative]` e `[boundary]`. Uma categoria
realmente inaplicável usa, sob o mesmo requisito, a forma estruturada:

```markdown
- [boundary] N/A: The value is an opaque identifier with no ordered boundary.
```

A justificativa deve ser específica. `N/A` sozinho é inválido.

## Design

`design.md` contém `## Glossary`, em inglês, com todas as siglas e termos de
domínio usados em prosa. Cada decisão usa heading `### Dn: ...` e registra:

- o caminho concreto onde aterrissa;
- a alternativa rejeitada;
- o motivo da rejeição e o invariante preservado.

`## Open Questions` fica ausente ou declara que nenhuma pergunta bloqueante
resta. Uma frase terminada em `?` é bloqueio de autoria.

## Tasks e tipos

`tasks.md` começa com uma tabela de três colunas:

```markdown
## 0. Traceability

| Requirement | Scenarios | Tasks |
|---|---|---|
| A cancelled order SHALL retain its discount | [happy] Recorded discount; [negative] Missing discount; [boundary] Zero discount | 1.1, 1.2 |
```

Nomes de requisito e cenário são exatos. IDs apontam para tasks existentes, e
cada requisito liga pelo menos uma task `[implementation]` e uma `[test]`.

Toda task usa `- [ ] X.Y [type] description`:

O template nativo do OpenSpec pode mostrar a forma mínima sem `[type]` e sem a
tabela. As `rules` injetadas por `openspec/config.yaml` têm precedência sobre
esse exemplo mínimo: preserve o prefixo parseável e acrescente a estrutura
deste contrato.

- `[prerequisite]`: cita uma capability existente entre crases;
- `[implementation]`: cita caminho repo-relative concreto, sem glob, diretório
  genérico ou filename solto;
- `[test]`: cita caminho sob uma raiz configurada de testes e nomeia os
  cenários exatos que prova;
- `[validation]`: contém o comando exato que produz a evidência estruturada.

Exemplo final com o comando oficial declarado pelo repositório:

```markdown
- [ ] 4.1 [validation] Run `<comando-oficial-de-validacao> --evidence-path openspec/changes/add-example/evidence/gate-report.json` and require exit code `0`.
```

Tasks de remoção citam exatamente um caminho. Ao concluir, esse caminho deve
estar ausente; tasks mistas de remover e alterar são divididas.

## Evidência de conclusão

Markdown ou logs copiados soltos não são prova. O arquivo canônico é
`openspec/changes/<change>/evidence/gate-report.json`, escrito pelo executor oficial do projeto:

```bash
<comando-oficial-de-validacao> --evidence-path openspec/changes/<change>/evidence/gate-report.json
```

O relatório estende o schema canônico `gate-report`, preserva seus campos de
lifecycle e registra status e exit code de cada gate, perfil efetivo e
fingerprint SHA-256 sobre `HEAD`, paths e bytes de `changedFiles`, perfil,
comandos e resultados dos gates. O próprio arquivo de saída é excluído do hash.
Completion recomputa o fingerprint e aceita apenas `resultStatus: passed` com
todos os gates bloqueantes em `passed` e `exitCode: 0`.

## Exceções legadas

Somente changes anteriores ao contrato podem constar no allowlist versionado
`legacyExemptions` de `openspec/handoff.json`. Cada entrada exige `reason` e
`removeWhen`. Um arquivo `.handoff-exempt` local não tem efeito. Não crie
exceção para change nova. A allowlist só evita que dívida documental legada
quebre `artifact`/`bundle`; ela nunca ignora erros de `completion` nem libera
archive.

## Limite do gate

O gate prova estrutura, resolução de traceabilidade, existência/ausência de
caminhos, fechamento de tasks e validade/frescor da evidência. Correção
semântica, qualidade do código e aderência real ao domínio continuam sendo
responsabilidade dos testes e gates do repositório e da revisão humana.
