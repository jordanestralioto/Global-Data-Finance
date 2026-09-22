---
name: agents-md-author
description: >-
  Use para criar, recriar, revisar ou fortalecer um AGENTS.md que explique o
  projeto, oriente a navegação dos agentes e defina políticas rigorosas de
  desenvolvimento, qualidade e execução. Ative quando o usuário pedir "cria um
  agents.md", "documenta este projeto para agentes", "define as regras dos
  agentes" ou exigir que arquitetura, comandos e preferências não sejam
  inventados. Cobre
  repositórios simples, monorepos e arquivos AGENTS.md locais. Não use para
  criar outra skill, escrever um README comum ou decidir arquitetura.
---

# AGENTS.md Author

## Contrato do artefato

Trate `AGENTS.md` como o manual operacional de maior precedência dentro do
escopo que ele governa. O documento precisa permitir que outro agente responda,
sem adivinhar:

1. o que o sistema faz, para quem e com quais invariantes;
2. onde começar e como navegar por código, documentação e operações;
3. como desenvolver neste projeto, inclusive idioma, gerenciador, framework,
   comandos oficiais e padrão de qualidade;
4. o que pode executar autonomamente, o que deve validar e onde deve parar.

O pacote desta skill é a autoridade de estrutura e política operacional base. O
repositório alvo fornece fatos técnicos e políticas locais; preferências
explícitas do usuário fornecem o modo de colaboração e podem definir regras de
desenvolvimento quando não falsificam o estado real do projeto.

Leia integralmente, antes de escrever:

- `assets/AGENTS.template.md`: headings, tabelas, regras gerais e Execution
  Policy completa;
- `references/content-contract.md`: conteúdo obrigatório e fontes por seção;
- `references/policy-authoring.md`: resolução de idioma, tooling, framework,
  qualidade e preferências do usuário;
- `references/source-discovery.md`: descoberta multi-stack, monorepos e
  navegação baseada em evidência.

Não procure um repositório externo para imitar e não use o projeto onde a skill
está instalada como fonte de fatos. A portabilidade vem de separar o baseline
bundled dos dados coletados no alvo, não de enfraquecer as regras.

Não otimize o artefato por contagem de linhas ou tokens. Otimize pelo contexto
operacional mínimo suficiente: cada detalhe materializado deve economizar
descoberta ou impedir uma escolha errada, e cada detalhe removido deve continuar
alcançável por uma rota owner clara.

## Procedimento

01. Resolva o escopo e a hierarquia de instruções.

    - Identifique o caminho exato do `AGENTS.md` alvo e a raiz governada por ele.
    - Leia todos os `AGENTS.md` ancestrais aplicáveis antes de propor texto.
    - Leia o arquivo alvo existente antes de editar e preserve regras válidas
      fora do pedido.
    - Em monorepos, mantenha políticas transversais no root. Crie arquivos locais
      somente quando stack, comandos, ownership, contratos ou riscos diferirem.
    - Um arquivo local herda o superior e registra diferenças; não replique a
      política inteira em toda subárvore.

02. Resolva o perfil operacional do usuário e do projeto antes da prosa.

    Construa esta matriz internamente:

    | Decisão                                           | Valor | Fonte | Autoridade | Escopo | Estado                     |
    | ------------------------------------------------- | ----- | ----- | ---------- | ------ | -------------------------- |
    | idioma de chat                                    | ...   | ...   | ...        | ...    | confirmed/unknown/conflict |
    | idioma de código, comentários, docs e Git         | ...   | ...   | ...        | ...    | ...                        |
    | gerenciador de dependências                       | ...   | ...   | ...        | ...    | ...                        |
    | command runner e validação oficial                | ...   | ...   | ...        | ...    | ...                        |
    | framework atual e regra para novas implementações | ...   | ...   | ...        | ...    | ...                        |
    | formatter, lint, tipos e testes                   | ...   | ...   | ...        | ...    | ...                        |
    | estilo de mudança e compatibilidade               | ...   | ...   | ...        | ...    | ...                        |

    - Use preferências explicitamente declaradas pelo usuário na conversa ou em
      instruções aplicáveis. O idioma usado casualmente na mensagem, sozinho,
      não define o idioma de código, documentação ou commits.
    - Use manifests, lockfiles, CI e scripts para confirmar o tooling real. Uma
      preferência não transforma um gerenciador ou framework ausente em fato.
    - Quando o usuário escolhe uma regra compatível com o projeto, registre-a
      como `USER_PREFERENCE` e escreva uma diretiva concreta em `Mandatory Rules`.
    - Quando preferência e contrato vigente colidem, mantenha o estado real,
      classifique `CONFLICT` e explique que adotar a preferência exige uma mudança
      separada. Não documente uma migração inexistente como política atual.
    - Se uma preferência essencial não estiver declarada, não invente. Para um
      draft, use uma regra conservadora baseada no repositório; para declarar o
      documento pronto para aprovação, obtenha a decisão faltante.

03. Faça descoberta somente de leitura.

    - Localize orientação, governança, manifests, lockfiles, entrypoints,
      configuração, scripts oficiais, CI, testes, documentação, ADRs, runbooks e
      ownership.
    - Confirme conteúdo dentro dos arquivos. Nomes de diretório são pistas, não
      prova de arquitetura ou responsabilidade.
    - Leia exemplos de ambiente e código de configuração para descobrir nomes de
      variáveis; não abra valores de `.env`, cofres ou credenciais.
    - Não execute build, deploy, migração, pipeline, acesso externo ou qualquer
      fluxo com efeitos colaterais apenas para descobrir como documentar.

04. Construa o ledger de evidências antes do texto final.

    | Claim        | Classe   | Fonte                       | Estado                        | Destino  |
    | ------------ | -------- | --------------------------- | ----------------------------- | -------- |
    | \<afirmação> | <classe> | \<arquivo:linha ou decisão> | \<confirmed/unknown/conflict> | \<seção> |

    Use somente estas classes:

    - `PORTABLE_BASELINE`: política copiada do template e independente de stack,
      domínio ou organização;
    - `REPO_FACT`: comportamento confirmado por código, manifest, CI, teste ou
      documentação vigente;
    - `REPO_POLICY`: regra confirmada por instrução aplicável, governança,
      CODEOWNERS ou decisão aceita;
    - `USER_PREFERENCE`: modo de trabalho explicitamente escolhido pelo usuário,
      como idiomas, ferramenta preferida ou estilo de mudança;
    - `USER_DECISION`: aprovação pontual, como owner ou status do documento;
    - `EXPLICIT_UNKNOWN`: informação procurada e não encontrada, representada por
      fallback declarado;
    - `CONFLICT`: fontes ou autoridades atuais discordam e exigem decisão.

    Nenhum comando, path, versão, métrica, componente, fase, owner, idioma,
    gerenciador ou framework entra no documento sem classe e fonte.

    Antes de materializar uma claim confirmada, aplique um filtro de inclusão.
    Ela entra quando muda uma decisão recorrente, protege uma boundary durável,
    indica o owner correto ou funciona como âncora estável de alto roteamento.
    Exemplos de âncoras são entrypoint ou facade pública, composition root,
    factory ou registry, owner de extensão e gate ou configuração canônica de
    qualidade. A existência de documentação detalhada não é, sozinha, motivo
    para remover uma âncora que diz ao agente onde ler, editar, registrar ou
    validar. Se a claim apenas descreve anatomia interna, default, schema ou uma
    lista sem efeito decisório, mantenha-a no ledger e navegue para a fonte
    canônica em vez de copiá-la para o `AGENTS.md`.

05. Produza um mapa de navegação, não apenas uma descrição.

    Confirme e registre:

    - o entrypoint humano: README, portal ou onboarding;
    - o entrypoint de runtime e o caminho executável, com os paths estáveis que
      levam à facade, composição, dispatch ou persistência relevantes;
    - os pontos de extensão recorrentes e onde implementar, registrar, exportar,
      testar e validar, quando o repositório possui essa rota estável;
    - o documento de arquitetura e o owner de detalhes por domínio;
    - onde ficam configuração, testes, operações, runbooks, contratos e decisões;
    - quais fontes são canônicas, planejadas, geradas, exploratórias ou
      não canônicas, quando essa classificação existir;
    - a ordem de leitura para uma primeira mudança segura.

    `System Overview` explica identidade e limites. `Pipeline Architecture`
    explica fluxo, ownership e onde começar no código. `Related Documentation`
    fornece a rota de leitura por pergunta. Um agente não deve precisar varrer o
    repositório inteiro para descobrir o próximo documento.

06. Materialize o template e preencha cada contrato.

    Para arquivo novo, gere o scaffold sem sobrescrever destino existente:

    ```bash
    python3 <skill-directory>/scripts/init_agents_md.py --output <path/to/AGENTS.md>
    ```

    Para arquivo existente, não rode o scaffolder. Edite o documento preservando
    as regras válidas. Em ambos os casos:

    - mantenha os headings, tabelas e política completa do template;
    - remova todo comentário `AGENTS_AUTHOR` após resolver a instrução;
    - escreva missão, boundaries, entradas, saídas, consumidores e invariantes;
    - inclua somente métricas adotadas; sem metas, use `Not documented` e Draft;
    - descreva o fluxo executável, gates, ownership e rota de navegação; nomeie
      os paths concretos de alto roteamento, mas não enumere classes, módulos
      privados ou passos internos que não mudam onde o agente atua;
    - materialize a rota de extensão quando ela for estável: owner da
      implementação, composition root, factory ou registry, export público,
      testes e documentação aplicáveis;
    - liste superfícies de configuração e comandos oficiais que mudam decisões
      recorrentes; deixe defaults, schemas e listas exaustivas em suas fontes;
    - identifique linguagem, runtime, gerenciador, frameworks e tooling
      estruturais com versões quando confirmadas; preserve configurações
      pequenas e decisórias de formatter ou linter, sem reproduzir o manifest;
    - ordene a documentação por progressive disclosure e por autoridade.

07. Componha `Mandatory Rules` como política de desenvolvimento forte.

    Preserve todas as regras gerais preenchidas no template. Depois acrescente
    diretivas concretas, com fonte, para:

    - idioma de chat, código, comentários, documentação e Git;
    - gerenciador de dependências, command runner e proibição de misturar managers;
    - framework e padrões arquiteturais a preservar em novas implementações;
    - formatter, lint, typecheck, testes e comando de validação oficial;
    - invariantes de dados, segurança, ownership e contratos públicos;
    - preferência de compatibilidade, migração, legado e tamanho de mudança;
    - rota inicial para questões de arquitetura, operações e testes.

    Escreva valores exatos: `Use <manager>`, `Chat = <idioma>`, `Run <comando>`.
    Não escreva “use a ferramenta adequada” quando o projeto já revela qual é.
    Não transforme detalhes efêmeros de módulos em regras globais; a política
    deve orientar decisões repetidas e apontar para o documento owner dos detalhes.

08. Preserve `Execution Policy` próxima ao baseline completo.

    - Mantenha os sete subtítulos e todos os controles concretos do template.
    - Customize nomes de boundary (`repository`/`workspace`) somente para refletir
      o escopo real.
    - Uma política superior pode fortalecer ou substituir uma regra, mas registre
      a fonte e não remova silenciosamente hard blocks, proteção de segredos,
      alinhamento, validação, segurança ou tratamento de falhas.
    - Preferências do usuário podem tornar a autonomia mais restritiva; não podem
      autorizar bypass de permissões, exposição de segredos ou ação destrutiva sem
      consentimento exato.

09. Trate conflitos e lacunas proporcionalmente.

    - Um fato ausente não bloqueia tudo: use fallback explícito, `Status: Draft`
      e reporte a decisão pendente.
    - Um conflito sobre comando oficial, segurança, ownership, idioma obrigatório,
      contrato público, gerenciador ou topologia bloqueia a claim afetada.
    - Se arquitetura não estiver suficientemente documentada, descreva somente o
      fluxo comprovado e identifique onde faltam ownership e documentação.
    - Não declare `Canonical` enquanto houver `Unassigned`, `Not documented`,
      conflito material ou política essencial não aprovada.

10. Valide estrutura, política e fidelidade.

    ```bash
    python3 <skill-directory>/scripts/validate_agents_md.py --file <path/to/AGENTS.md>
    python3 <skill-directory>/scripts/validate_agents_md.py --file <path/to/AGENTS.md> --strict-governance --format json
    ```

    Confirme também que links locais existem, comandos têm fonte, o perfil
    operacional foi materializado, a navegação chega a arquivos reais e nenhum
    segredo foi copiado. O validador estrutural não prova fidelidade factual.
    Faça ainda uma revisão de escopo: remova inventários de dependências, hooks,
    variáveis, classes, formatos e etapas internas que não alterem uma decisão
    recorrente do agente. Não remova, apenas para reduzir tamanho, o caminho
    concreto do runtime, a rota de extensão ou o gate/configuração canônica que
    evita descoberta ou implementação no owner errado.

11. Entregue relatório auditável.

    ```markdown
    Action: CREATED|UPDATED|REVIEWED|BLOCKED
    File: <path>
    Document status: DRAFT|READY_FOR_APPROVAL|CONFIRMED
    Operational profile: <languages; manager; framework; validation>
    Portable policy: APPLIED|STRENGTHENED
    Confirmed facts: <summary with sources>
    User preferences applied: <list or "none declared">
    Explicit unknowns: <list or "none">
    Conflicts: <list or "none">
    Validation: <command and result>
    ```

## Anti-patterns

- Produzir um inventário de pastas sem explicar fluxo, ownership ou ordem de
  leitura. Navegação precisa responder onde começar e quando abrir cada fonte.
- Escrever “siga os padrões do projeto” quando linguagem, manager, framework e
  checks já podem ser nomeados exatamente.
- Tratar preferência como fato: gostar de `pnpm` não prova que um projeto `npm`
  já migrou. Registre o conflito e separe a possível migração.
- Inferir preferência de idioma pela língua de uma única mensagem. Use decisão
  explícita para chat, código, docs e Git.
- Reduzir `Execution Policy` a frases genéricas e apagar a lista concreta de
  operações bloqueadas.
- Copiar stack, paths, métricas ou nomes de componentes de outro projeto.
- Confundir evidência com conteúdo obrigatório e transformar o `AGENTS.md` em
  espelho do manifest, da árvore de módulos, do CI ou de uma referência de
  feature.
- Confundir compactação com qualidade e remover facade, composition root,
  factory/registry, ponto de extensão ou política de lint que orienta uma ação
  recorrente.
- Escolher silenciosamente entre README, manifest e CI conflitantes.
- Declarar `Canonical` apenas porque o texto foi concluído.

## Exemplos

### Caso positivo

**Entrada:** “Crie o AGENTS.md. Fale comigo em português, mantenha código e Git
em inglês, use o gerenciador já adotado e preserve o framework atual.”

**Saída esperada:** confirmar manager e framework em manifests/lockfiles/CI,
registrar os idiomas como `USER_PREFERENCE`, materializar regras exatas em
`Mandatory Rules`, mapear a navegação real e preservar a Execution Policy
completa.

### Caso negativo

**Entrada:** “Crie uma skill para padronizar documentação de API.”

**Por quê não:** o artefato pedido é outra skill; use `skill-governance`.

## Evals de trigger

Deve acionar:

- “Cria um AGENTS.md forte para este projeto.”
- “Documenta o projeto e ensina os agentes onde começar.”
- “Inclui minhas preferências de idioma, package manager e framework nas rules.”
- “Revisa a Mandatory Rules e a Execution Policy deste AGENTS.md.”
- “Meu monorepo precisa de AGENTS.md raiz e por pacote?”
- “Remove regras inventadas, mas deixa políticas de qualidade completas.”

Não deve acionar:

- “Cria uma skill com frontmatter e evals.” → `skill-governance`.
- “Qual arquitetura devo escolher?” → `architecture`.
- “Escreve um README de onboarding.” → documentação geral.
- “Troca npm por pnpm neste projeto.” → mudança de tooling, não documentação.

## Evals de workflow

### Eval A — preferências explícitas e tooling confirmado

Entrada: “Crie o AGENTS.md deste projeto. Chat em português; código, docs e Git
em inglês. Use o manager e o framework já configurados.”

Assertions:

- [ ] separa `USER_PREFERENCE` de `REPO_FACT`;
- [ ] nomeia idiomas, manager, framework e comando oficial sem frases genéricas;
- [ ] `Mandatory Rules` contém regras concretas para os quatro itens;
- [ ] `Execution Policy` preserva os sete subtítulos com todos os controles concretos;
- [ ] o mapa de navegação aponta apenas para caminhos existentes;
- [ ] o validador normal termina com código 0.

### Eval B — preferência incompatível com o repositório

Entrada: “Eu prefiro pnpm, então documente pnpm”, em projeto cujo manifest,
lockfile e CI confirmam outro manager e não existe migração aplicada.

Assertions:

- [ ] registra a preferência e o estado real separadamente;
- [ ] classifica a adoção imediata como `CONFLICT`;
- [ ] não escreve pnpm como comando atual;
- [ ] mantém `Status: Draft` e relata que migração é uma mudança separada.

### Eval C — monorepo com navegação e políticas locais

Entrada: “Crie instruções para um monorepo com stacks e comandos diferentes em
dois serviços, mas com a mesma política de qualidade.”

Assertions:

- [ ] o root contém política transversal, mapa macro e comandos globais;
- [ ] arquivos locais registram somente diferenças de stack, commands e riscos;
- [ ] cada serviço tem entrypoint e rota de documentação comprovados;
- [ ] a política geral não é duplicada em cada subárvore;
- [ ] todos os arquivos produzidos passam no validador normal.

### Eval D — documento factual demais

Entrada: “Enxugue este AGENTS.md: ele repete classes, dependências, variáveis,
hooks e formatos que já possuem documentação owner.”

Assertions:

- [ ] preserva boundaries, invariantes, comandos recorrentes e política de
  execução;
- [ ] substitui detalhes de implementação por navegação para owners existentes;
- [ ] mantém os paths concretos de alto roteamento necessários para alcançar o
  entrypoint, a composição e o dispatch sem varrer o repositório;
- [ ] mantém regras de extensão e a configuração/gate de lint quando elas mudam
  onde implementar, registrar ou validar;
- [ ] mantém comandos exatos sem reproduzir o roster de hooks ou etapas da CI;
- [ ] não remove regras específicas que ainda mudam decisões recorrentes;
- [ ] o documento resultante passa no validador normal.
