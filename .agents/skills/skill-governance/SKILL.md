---
name: skill-governance
description: >-
  Use para criar, avaliar, reescrever ou governar agent skills. Ative quando o
  usuário pedir "cria uma skill", "melhora essa skill", "essa skill não dispara",
  "a description está boa?", "essa skill ainda vale a pena?", "devo fazer skill
  ou script?", "revise esse SKILL.md", "monta os evals dessa skill" ou perguntar
  sobre `references/`, `scripts` e assets da skill. Para `AGENTS.md` ou
  instruções gerais do repositório, use `agents-md-author`. Não use para alterar
  código comum do projeto, escrever documentação geral ou criar workflows
  OpenSpec sem relação com skills.
---

# Skill Governance

Skills falham por dois motivos quase universais: **a description não dispara** (o
agente nunca lê a skill) ou **o corpo não instrui** (o agente lê, mas faria igual
sem ela). Toda decisão aqui existe para eliminar um desses dois problemas. O
segundo cresce a cada geração de modelo: instrução que antes mudava o resultado
pode virar ruído que só consome contexto.

## Procedimento

1. **Decida se é skill.** Vale quando o workflow tem etapas cuja ordem importa,
   errar sem guia tem custo real, a tarefa se repete com variações ou existe
   conhecimento não-óbvio (restrições, anti-patterns, convenções do projeto). Não
   vale quando a melhor resposta é um script determinístico, uma regra curta de
   agente, um documento estático ou uma tarefa rara. Se não vale, entregue a
   alternativa com uma frase de justificativa.
2. **Parta de material real.** Uma tarefa executada com as correções que você
   precisou fazer, runbooks, comentários de revisão, incidentes e fixes do
   histórico produzem instruções específicas. Pedir a um LLM "as boas práticas de
   X" produz conselho que o agente já seguiria sozinho.
3. **Escreva os evals antes de refinar o corpo**, como dados fora do caminho de
   execução (seção "Evals"). Um caso que você não consegue escrever como prompt
   realista ainda não justifica instrução.
4. **Escreva a description e o corpo** conforme as seções abaixo.
5. **Meça contra um baseline.** Rode 2–3 prompts de `evals.json` com a skill e
   sem ela (ou com a versão anterior, ao revisar), cada execução em contexto
   limpo: subagente ou sessão nova. Leia as transcrições, não só a saída final.
   Corte o que sai igual nas duas execuções; reforce onde a skill muda o
   resultado. Se o agente reinventa o mesmo auxiliar em toda execução, ele
   pertence a `scripts/`.
6. **Meça o gatilho** com `scripts/run_trigger_evals.py`. Ajuste a description
   pelas falhas do conjunto de treino e escolha a versão pela taxa de acerto no
   conjunto de validação.
7. **Valide a estrutura** com `scripts/validate_evals.py` e com o validador de
   skills do repositório, quando existir, antes de declarar conclusão. Gate
   estrutural passando não prova que a skill dispara nem que ajuda; sem execução
   registrada, apresente os evals como casos propostos.

Ao **revisar** uma skill existente, diagnostique primeiro qual das duas falhas
domina. Entregue achados ordenados por impacto (gatilho, depois instrução, depois
tamanho e estrutura), cada um com o trecho atual e a reescrita proposta. Manter
como está, enxugar ou aposentar são respostas válidas quando o baseline sustenta.

## Anatomia e carregamento

```
skill-name/
├── SKILL.md      ← obrigatório
├── scripts/      ← código executado sem precisar ser lido
├── references/   ← docs carregados sob demanda
└── assets/       ← templates, schemas, arquivos usados na saída
```

O agente carrega a skill em camadas — isso decide o que vai onde:

1. **Metadata** (`name` + `description`) — sempre no contexto, para todas as
   skills instaladas (~100 tokens cada)
2. **Corpo do SKILL.md** — carregado inteiro quando a skill dispara; mantenha
   abaixo de 500 linhas (~5 mil tokens)
3. **Recursos** — carregados só quando o corpo manda

Tudo que o agente precisa para começar vai no corpo. O que só serve a cenários
específicos vai em `references/`, com ponteiro dizendo **quando** ler cada arquivo
("leia o arquivo de erros se a API devolver 4xx", não "veja references/"). Aponte
para referências diretamente do SKILL.md: cadeias em que um arquivo remete a outro
tendem a ser lidas pela metade. Arquivos de referência acima de 100 linhas
precisam de sumário no topo, porque o agente costuma pré-visualizar arquivos
longos só pelo começo: a primeira seção `##` é `## Sumário` (ou `## Contents`)
e lista cada seção `##` do arquivo.

Se a skill atende stacks com instruções distintas, crie um arquivo por variante em
`references/` (`aws.md`, `gcp.md`) e deixe no corpo só a decisão de qual ler.

Evals não pertencem a essa árvore de execução; a seção "Evals" diz onde ficam.

### Frontmatter

A especificação aberta de Agent Skills, lida por Claude Code, Codex, OpenCode e
outros clientes, define limites; um cliente pode truncar ou rejeitar a skill que
os ultrapassa:

- `name`: até 64 caracteres, só minúsculas, números e hífens, sem hífen no início,
  no fim ou duplicado, e igual ao nome da pasta
- `description`: até 1024 caracteres — ela cresce a cada ajuste de gatilho, então
  confira o tamanho ao final

Use só `name` e `description`. É o subconjunto que todo cliente entende, e os
validadores do harness rejeitam chaves extras. Campos de um cliente específico
(como `allowed-tools`) só cabem em skill local de projeto que usa apenas esse
cliente.

## Como escrever a description (o gatilho)

A description é o único texto que o agente lê antes de decidir usar a skill. Todo
"quando usar" fica aqui: o corpo só é lido depois do disparo, então nenhuma lista
de casos no corpo muda a decisão. Escreva como instrução ao agente ("Use
para..."), com a linguagem que um humano real usaria para descrever o problema.

**Ruim:**

```yaml
description: Gera release notes estruturadas para deploys.        # descreve output, não situação
description: Executa pipeline de changelogs com diff semântico.   # vocabulário que ninguém usa
description: Ajuda com documentação de software.                  # sem fronteira: ativa para tudo ou nada
```

**Bom — situação, linguagem real, pedido implícito e fronteira:**

```yaml
description: >
  Use para escrever ou melhorar release notes e changelogs de qualquer deploy.
  Ative quando o usuário pedir "documenta o que mudou", "gera as notas da versão"
  ou colar commits e querer transformar em texto para o cliente. Para mensagens
  de commit, use `commit-conventions`.
```

Nomeie na própria description a fronteira com skills vizinhas que disputam o mesmo
pedido; é o que separa near-misses. Skills são instaladas seletivamente: ao
encaminhar para outra skill no corpo, diga o que fazer se ela não estiver
instalada (descrever a especialidade e o próximo passo) em vez de assumir que
existe.

## Como escrever o corpo

O corpo só existe para o que o agente **não faria bem sem ele**.

**Inclua:**

- Procedimento com ordem que importa
- Gotchas: fatos do ambiente que contrariam a suposição razoável e correções que
  você precisou fazer ao agente — costumam ser o conteúdo de maior valor
- Restrições não-óbvias e o motivo delas existirem
- Um padrão com alternativa breve, em vez de um menu de opções equivalentes
- Template de saída quando o formato precisa ser preciso
- Casos negativos que dizem o que fazer quando a skill disparou para um pedido
  vizinho

**Não inclua:**

- Introduções genéricas ("esta skill serve para...")
- Seções de "quando usar" ou listas de pedidos que devem acionar — isso é papel
  da description
- Evals ou ponteiros para eles
- O que o agente já faz bem sozinho; na dúvida, o baseline do procedimento decide

Calibre a rigidez à fragilidade: dê liberdade onde várias abordagens servem e seja
prescritivo (comando exato, sequência fixa) onde a operação é frágil, destrutiva ou
precisa de consistência.

### Tom e estilo

Use forma imperativa. Explique o *porquê* das restrições em vez de proibir sem
razão — modelos atuais seguem melhor o raciocínio do que a ênfase, e Sempre ou
Nunca em maiúsculas tende a gerar aplicação exagerada fora do caso pretendido.

**Ruim:**

```markdown
Nunca crie dois arquivos ao mesmo tempo. É OBRIGATÓRIO validar o YAML antes.
```

**Bom:**

```markdown
Valide o YAML antes de declarar conclusão — erros de frontmatter são silenciosos
e corrompem o carregamento da skill sem mensagem de erro visível.
```

### Scripts

Um script bundled deve rodar sem que o agente precise lê-lo: dependências
declaradas, erro com mensagem acionável, código de saída diferente de zero na falha
e saída estruturada (JSON) quando o agente vai interpretar o resultado. No corpo,
documente o comando e o significado da saída, não a implementação.

## Estrutura mínima de um SKILL.md

```markdown
---
name: nome-da-skill
description: >
  [quando ativar + o que faz + variações de linguagem do usuário + fronteiras]
---

# Nome da Skill

## Procedimento
1. ...

## Exemplos

### Caso positivo
**Entrada:** ...
**Saída esperada:** ...

### Caso negativo
**Entrada:** ...
**Por quê não:** ...
```

## Evals

Evals são dados de teste, não instrução. O corpo só é lido depois do disparo, e
um arquivo apontado por ele pode ser lido durante a própria execução avaliada,
que passa a enxergar o critério de correção. Por isso:

- Guarde-os como JSON no formato do padrão aberto: `triggers.json` mede o
  gatilho e `evals.json`, o comportamento.
- O padrão usa `evals/` dentro da pasta da skill. Quando a pasta é publicada ou
  projetada para outros repositórios, guarde-os em `evals/<nome-da-skill>/` na
  raiz do repositório-fonte, fora do que é distribuído.
- Não aponte para eles no `SKILL.md` nem em `references/`. Quem mantém a skill X
  trabalha com esta skill, não com X.

Os exemplos abaixo são da skill hipotética de release notes usada na seção
sobre a description.

### `triggers.json`

```json
[
  {"query": "terminei o merge da 2.4; antes de criar a tag, escreve o que muda pra quem usa o app", "should_trigger": true},
  {"query": "como escrevo a mensagem desse commit de correção?", "should_trigger": false, "routes_to": "commit-conventions"}
]
```

- Ao medir ou otimizar o gatilho, mire em 8–10 consultas de cada lado; o
  validador exige ao menos 3.
- Os negativos valiosos são near-misses: compartilham vocabulário, mas pedem
  outro caminho. `routes_to` é obrigatório neles e nomeia a skill, o agente ou
  `none` (o agente resolve sem skill); negativo sem destino plausível não testa
  fronteira.
- Positivos úteis não repetem a description: frases copiadas dela testam a
  description contra si mesma. O validador rejeita positivo que contém uma
  frase entre aspas da description com duas palavras ou mais, ou que é igual a
  qualquer uma delas. Varie formalidade, typos, contexto e pedidos em que a
  necessidade aparece no meio de uma tarefa maior.
- Antes de otimizar a description, marque ~40% de cada lado com
  `"split": "validation"` e não use esses casos para reescrevê-la; descrição
  ajustada às próprias consultas falha nas próximas.

### `evals.json`

```json
{
  "skill_name": "release-notes",
  "evals": [
    {
      "id": "refactor-fora-das-notas",
      "prompt": "monta o texto da versão 2.4 a partir de git log v2.3..v2.4; metade dos commits é refactor interno",
      "expected_output": "Notas agrupadas por tipo de mudança, sem os refactors internos.",
      "assertions": ["output não cita commits de refactor interno", "output separa novidades de correções"]
    }
  ]
}
```

- `prompt` é a mensagem que um usuário real escreveria, com caminhos e contexto.
- Assertions são binárias e verificáveis: "output contém campo `action`
  preenchido", não "o agente escolheu corretamente". Depois da primeira
  execução, troque ou remova a assertion que passa com e sem a skill — ela não
  mede a skill.
- `runs` (opcional) registra execuções:
  `{"model": "...", "status": "not run" | "executed", "evidence": "<caminho>"}`.
  `executed` exige `evidence`.

### Validar e executar

```bash
python3 <skill-dir>/scripts/validate_evals.py --skills-root <pasta-de-skills> [--evals-root evals] [--agents-root agents]
python3 <skill-dir>/scripts/run_trigger_evals.py --skill <nome> --triggers <dir>/triggers.json [--split validation]
```

`validate_evals.py` confere schema, mínimos, duplicatas e destinos de
`routes_to`. Sem `--evals-root`, procura `evals/` dentro de cada skill. Sai com
`0` (válido), `1` (achados) ou `2` (uso inválido); `--format json` devolve os
achados estruturados.

`run_trigger_evals.py` roda cada consulta 3 vezes com `claude -p`, ferramentas
restritas a `Skill` e `Read`, e conta como disparo a chamada da skill pelo nome
exato ou a leitura do `SKILL.md` que esse nome executa, por qualquer caminho que
leve ao mesmo arquivo. Uma cópia aninhada de mesmo nome é outro comando
(`apps/web:deploy`) e não conta, mesmo com frontmatter igual. Cada execução abre
uma sessão paga; `--max-budget-usd` limita cada uma. O caso passa quando a taxa
fica do lado certo do limiar (`0.5`); uma execução com erro invalida o caso. O
runner mede só se a skill avaliada dispara: um negativo aprovado não prova que
o agente escolheu o `routes_to`. Ele só mede skill instalada, pessoal ou de
projeto, e recusa antes de abrir sessões se as cópias instaladas divergem. O
JSON de saída registra o modelo e o caminho e o hash do frontmatter da cópia que
o cliente carrega: o resultado vale só para esse cliente, esse modelo e essa
versão, e os demais clientes continuam não medidos. Sai com `0` (todos
passaram), `1` (falhas) ou `2` (erro de execução ou de uso).

## Exemplos

### Caso positivo

**Entrada:** "essa skill de deploy não dispara quando peço 'sobe pra produção'"
**Saída esperada:** Diagnosticar falha de gatilho, reescrever a description com a
linguagem do usuário e a fronteira com skills vizinhas, propor `triggers.json`
com near-misses e não mexer no corpo antes de confirmar que o problema é o
gatilho.

### Caso positivo

**Entrada:** "essa skill de React ainda vale a pena com os modelos atuais?"
**Saída esperada:** Propor ou executar comparação com e sem a skill, separar os
trechos que o modelo já cumpre sozinho dos que mudam o resultado e recomendar
manter, enxugar ou aposentar com a evidência obtida.

### Caso negativo

**Entrada:** "cria uma skill para renomear CSVs com a data no nome"
**Por quê não:** Tarefa determinística de uma etapa; entregue um script com uma
frase de justificativa.

### Caso negativo

**Entrada:** "cria o AGENTS.md deste repositório"
**Por quê não:** Instrução de repositório não é skill. Use `agents-md-author`; se
não estiver instalada, oriente pelo conteúdo esperado do arquivo, sem criar skill.

## Checklist antes de entregar

- [ ] Frontmatter só com `name` (igual à pasta) e `description` (≤ 1024 caracteres)
- [ ] A description usa a linguagem do usuário, cobre pedidos informais e nomeia
  fronteiras com skills vizinhas
- [ ] O corpo não tem seção "quando usar", lista de evals nem ponteiro para evals
- [ ] Cada instrução muda o resultado em relação ao baseline, ou está registrada
  como não medida no relatório da revisão, não no corpo
- [ ] As instruções explicam o porquê, com rigidez proporcional à fragilidade
- [ ] Existe pelo menos um exemplo negativo
- [ ] `triggers.json` prioriza near-misses com `routes_to`, `evals.json` tem
  assertions binárias e `validate_evals.py` passa
- [ ] Evals sem execução registrada aparecem como propostos
- [ ] SKILL.md abaixo de 500 linhas; referências apontadas do corpo, com quando
  ler, e sumário nas que passam de 100 linhas
- [ ] Scripts rodam sem ser lidos: erro acionável, código de saída e saída estruturada
- [ ] Handoffs para outras skills dizem o que fazer se ela não estiver instalada
