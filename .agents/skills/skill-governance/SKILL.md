---
name: skill-governance
description: >-
  Use para criar, avaliar, reescrever ou governar agent skills. Ative quando o
  usuário pedir "cria uma skill", "melhora essa skill", "essa skill não dispara",
  "a description está boa?", "devo fazer skill ou script?",
  "revise esse SKILL.md" ou perguntar sobre `references/`, `scripts` e assets da
  skill. Não use para alterar código comum do projeto, escrever documentação
  geral ou criar workflows OpenSpec sem relação com skills.
---

# Skill Author

## Por que skills falham

Skills falham por dois motivos quase universais: **a description não dispara** (o
agente nunca lê a skill) ou **o corpo não instrui** (o agente lê mas faria igual
sem ela). Toda decisão aqui existe para eliminar um desses dois problemas.

______________________________________________________________________

## Decisão inicial: skill ou não?

Antes de escrever uma linha, responda:

**Vale criar uma skill quando:**

- O workflow tem múltiplas etapas com ordem que importa
- Errar sem guia tem custo real
- A tarefa vai se repetir com variações de contexto
- Existe conhecimento não-óbvio: anti-patterns, restrições, trade-offs

**Não vale quando a melhor resposta for:**

- Um script determinístico de baixo julgamento
- Uma regra curta de agente
- Um documento estático de referência
- Uma tarefa rara ou com output trivial

Se não vale, entregue a alternativa correta com uma justificativa de uma frase.

______________________________________________________________________

## Anatomia de uma skill

```
skill-name/
├── SKILL.md              ← obrigatório
├── scripts (opcional)    ← código executável e reutilizável
├── references (opcional) ← docs carregados sob demanda
└── assets (opcional)     ← templates, fontes, ícones
```

### Sistema de carregamento em 3 níveis

O agente carrega a skill em camadas — entender isso muda o que vai onde:

1. **Metadata** (name + description) — sempre no contexto, ~100 palavras
2. **Corpo do SKILL.md** — carregado quando a skill dispara, ideal abaixo de 500 linhas
3. **Recursos bundled** — carregados sob demanda, sem limite de tamanho

A consequência prática: tudo que o agente precisa para começar vai no SKILL.md.
O que só é necessário em cenários específicos vai em `references/`. Scripts que
rodam sem precisar ser lidos vão em `scripts/`.

### Regra de tamanho

Mantenha o SKILL.md abaixo de 500 linhas. Se estiver se aproximando do limite,
extraia seções para `references/` com ponteiros claros de quando ler cada arquivo.
Para arquivos de referência maiores que 300 linhas, inclua um sumário no topo.

### Quando separar por domínio

Se a skill atende múltiplos frameworks ou stacks com instruções distintas, organize
por variante em vez de empilhar tudo no SKILL.md:

```
cloud-deploy/
├── SKILL.md              ← workflow principal + decisão de qual variante usar
└── references/
    ├── aws.md
    ├── gcp.md
    └── azure.md
```

O agente lê só o arquivo relevante para o contexto. Isso mantém o SKILL.md enxuto
e evita que instruções de AWS poluam o contexto de um deploy GCP.

______________________________________________________________________

## Como escrever a description (o gatilho)

A description é o único texto que o agente lê antes de decidir usar a skill.
Se ela falhar, nada mais importa. Todo "quando usar" fica aqui — nunca no corpo.

**Ruim — descreve output, não situação:**

```yaml
description: Gera release notes estruturadas para deploys.
```

O agente não dispara se o usuário escrever "preciso documentar o que mudou nessa versão".

**Ruim — vocabulário técnico que o usuário não usa:**

```yaml
description: Executa pipeline de geração de changelogs com diff semântico.
```

Nenhum usuário real pede isso com essas palavras.

**Ruim — genérico demais:**

```yaml
description: Ajuda com documentação de software.
```

Ativa para tudo ou para nada. Sem fronteira, sem utilidade.

**Bom — captura situação, linguagem real e variações:**

```yaml
description: >
  Use essa skill para escrever ou melhorar release notes e changelogs de qualquer deploy.
  Ative quando o usuário pedir "documenta o que mudou", "gera as notas da versão",
  "preciso de um changelog", ou descrever commits e querer transformar em texto
  para o cliente.
```

**Bom — empurrativo, cobre pedido implícito e linguagem casual:**

```yaml
description: >
  Use para triar, classificar e encaminhar bugs reportados. Ative mesmo quando
  o pedido for informal: "esse bug é grave?", "o que faço com esse erro?",
  "como priorizo esses problemas?". Ative também quando o usuário colar um
  stack trace e pedir orientação sobre severidade ou próximos passos.
```

Regra prática: escreva a description antecipando como um humano real descreveria
o problema — não como você nomearia a função internamente.

______________________________________________________________________

## Como escrever o corpo

O corpo só existe para o que o agente **não faria bem sem ele**.

**Inclua:**

- Procedimento com ordem que importa
- Restrições não-óbvias e o motivo delas existirem
- Anti-patterns comuns e como reconhecê-los
- Formato de saída quando o output precisa ser preciso

**Não inclua:**

- Introduções genéricas ("esta skill serve para...")
- Seções de "quando usar" — isso é papel da description
- Instruções que qualquer LLM seguiria por padrão

**Teste de utilidade:** um agente consegue executar a tarefa lendo só o corpo, sem
inferir o que falta? Se não, complete. Se sim e ainda está longo, corte o óbvio.

### Tom e estilo

Use forma imperativa nas instruções. Explique o *porquê* das restrições em vez de
proibir sem razão — modelos respondem melhor ao entendimento do que ao imperativo
rígido. Se você está escrevendo Sempre ou Nunca em maiúsculas, pare e pergunte se
não é melhor explicar o raciocínio por trás da regra.

**Ruim:**

```markdown
Nunca crie dois arquivos ao mesmo tempo. É OBRIGATÓRIO validar o YAML antes.
```

**Bom:**

```markdown
Valide o YAML antes de declarar conclusão — erros de frontmatter são silenciosos
e corrompem o carregamento da skill sem mensagem de erro visível.
```

### Padrão para exemplos no corpo

Exemplos tornam restrições concretas. Use entrada e saída esperada lado a lado:

```markdown
**Exemplo:**
Entrada: usuário pede skill para renomear arquivos CSV com data no nome
Saída esperada: rejeitar — tarefa determinística de uma etapa; um script resolve
```

### Scripts reutilizáveis

Se durante os testes o agente gerou o mesmo script auxiliar em múltiplos cenários,
esse script pertence a `scripts/` — escreva uma vez, instrua a skill a usá-lo.
Reinventar a mesma lógica a cada invocação é desperdício de contexto e fonte de
inconsistência.

______________________________________________________________________

## Estrutura mínima de um SKILL.md

```yaml
---
name: nome-da-skill
description: >
  [quando ativar + o que faz + variações de linguagem do usuário]
---
```

```markdown
# Nome da Skill

## [Contexto não-óbvio — omita se trivial]

## Procedimento
1. ...
2. ...

## Exemplos

### Caso positivo
**Entrada:** ...
**Saída esperada:** ...

### Caso negativo
**Entrada:** ...
**Por quê não:** ...

## Evals de trigger

Deve acionar:
- "[pedido formal]"
- "[pedido informal / edge case]"

Não deve acionar:
- "[near-miss — parece mas não é]"
- "[caso claramente fora do escopo]"
```

______________________________________________________________________

## Evals: o que torna um caso útil

Casos óbvios não testam nada — "escreva um script bash" nunca vai acionar uma
skill de governança independente de como a description esteja escrita.

O valor real está nos near-misses:

- Pedidos que compartilham vocabulário mas precisam de outro caminho
- Pedidos informais ou com typo que deveriam acionar
- Pedidos ambíguos onde esta skill compete com outra

Para evals de workflow, cada cenário precisa de assertions binárias verificáveis:

```markdown
- [ ] output contém campo `action` preenchido
- [ ] `action` é `create`, não `reject`
- [ ] output não contém placeholders em aberto
```

"O agente escolheu corretamente" não é uma assertion — não pode ser verificada
sem subjetividade.

______________________________________________________________________

## Processo de criação e iteração

1. Entenda a intenção: o que a skill deve fazer, quando disparar, qual o output
2. Escreva o rascunho do SKILL.md
3. Crie 2–3 prompts de teste realistas e compartilhe antes de rodar
4. Execute os testes e, enquanto rodam, escreva as assertions
5. Revise com base no feedback — generalize a partir dos exemplos, não overfite
6. Repita até o output ser consistente e o usuário satisfeito
7. Otimize a description com evals de trigger incluindo near-misses

Ao revisar: leia as transcrições, não só os outputs finais. Se o agente repete
os mesmos passos auxiliares em todo teste, esse trabalho pertence a `scripts/`.

## Evals de trigger

Deve acionar:

- "cria uma skill nova para o repositório"
- "a description dessa skill está boa ou precisa melhorar?"
- "essa skill não está disparando quando peço X"
- "revisa a estrutura do meu SKILL.md"

Não deve acionar:

- "escreve um script bash para renomear arquivos"
- "cria uma change OpenSpec com proposal e design"
- "escreve a documentação do projeto no README"
- "configura o linter do Python"

______________________________________________________________________

## Checklist antes de entregar

- [ ] A description captura pedidos informais, não só formais
- [ ] Nenhuma seção "quando usar" foi adicionada ao corpo
- [ ] O corpo instrui algo que o agente não faria sozinho
- [ ] As instruções explicam o porquê, não apenas proíbem
- [ ] Existe pelo menos um exemplo negativo
- [ ] Evals de trigger incluem near-misses, não só casos óbvios
- [ ] Evals de workflow têm assertions binárias verificáveis
- [ ] Nenhuma seção repete o que outra já diz
- [ ] O SKILL.md tem menos de 500 linhas
- [ ] Scripts reutilizáveis estão em `scripts/` e otimizados para o melhor big O Notation possivel e também inline
- [ ] As `references/` (se criadas) foram otimizadas para relatar cenários isolados (em vez de diversos cenários com pouca profundidade)
