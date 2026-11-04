---
name: agents-md-author
description: >-
  Use para criar ou revisar um `AGENTS.md` que ajude agentes a entender o
  objetivo do projeto, onde começar no código, como validar e quais regras do
  repositório seguir. Ative quando o usuário pedir "cria um agents.md",
  "documenta o projeto para agentes", "onde o agente deve começar?" ou uma
  revisão de instruções locais em um monorepo. Abrange documentos raiz e de
  subárvore. Não use para criar outra skill, escrever um README comum ou decidir
  arquitetura.
---

# AGENTS.md Author

## Procedimento

1. Determine o caminho do documento e o escopo que ele governa. Descubra a raiz
   do repositório e o diretório de início da sessão; leia as instruções que o
   cliente realmente aplica nessa cadeia. Confira arquivos `AGENTS.override.md`,
   `AGENTS.md` e nomes de fallback somente quando o cliente os reconhecer ou
   estiver configurado para carregá-los. Consulte
   `references/source-discovery.md` se a cadeia, os fallbacks ou os limites do
   cliente não forem óbvios.

2. Leia o documento alvo antes de editar. Para afirmações necessárias, confirme
   a fonte responsável em código, manifest, CI, testes, governança ou
   documentação atual. Use somente os arquivos e subsistemas relevantes; nome
   de diretório, preferência isolada ou plano não comprova um fato atual. Não
   abra valores de `.env`, credenciais ou cofres.

3. Ao criar uma orientação raiz, use `assets/AGENTS.template.md`. Ao atualizar
   um arquivo existente, preserve regras válidas fora do pedido. Uma orientação
   local herda a política aplicável acima dela e registra somente diferenças da
   subárvore.

4. Organize a orientação raiz em cinco blocos. Os títulos do template são
   sugestões em inglês; escreva no idioma permitido pela política explícita do
   repositório alvo:

   - `Project Overview`: missão, consumidores e limites principais.
   - `Architecture & Ownership`: primeiro caminho de código, fluxo e owners.
   - `Development Workflow`: comandos confirmados para configurar, executar e
     validar.
   - `Engineering Rules`: práticas de engenharia e políticas duráveis do alvo.
   - `Documentation Map`: documento certo para a próxima pergunta.

   Cada detalhe deve ajudar a escolher onde começar, editar, testar ou aprender.
   Com títulos traduzidos, confira manualmente as cinco funções: a CLI só
   confirma a estrutura. Métricas, tabelas e inventários são opcionais; não os
   inclua sem função decisória.

5. Mantenha as regras portáteis concretas: inspecione a fonte responsável,
   preserve contratos e fronteiras, faça mudanças coesas, atualize testes e
   documentação afetados, valide de forma proporcional e relate checks que
   falharam ou não rodaram. Idioma, `__init__.py`, manager, framework e regras de
   qualidade específicas entram somente quando são fatos ou políticas
   confirmados no alvo. Consulte `references/policy-authoring.md` quando houver
   escolha de política ou fontes conflitantes.

6. Faça uma revisão factual separada da validação estrutural. Links relativos
   precisam apontar para caminhos existentes; comandos precisam ter uma fonte;
   conflitos precisam nomear as fontes e afirmações sem inventar uma resposta.
   Proteja segredos na comunicação. A CLI valida estrutura, marcadores e links;
   ela não confirma arquitetura, comandos ou políticas.

7. Execute a validação apropriada ao escopo:

   ```bash
   python3 <skill-directory>/scripts/validate_agents_md.py --file <path/to/AGENTS.md> --scope root
   python3 <skill-directory>/scripts/validate_agents_md.py --file <path/to/AGENTS.md> --scope local
   ```

   `root` é o padrão. Use `local` apenas para uma orientação de subárvore. Não
   declare o documento factual ou pronto apenas porque o comando terminou com
   código `0`; informe a revisão de conteúdo, a validação executada e qualquer
   conflito ou check que ficou pendente. Não exija uma etapa formal de aprovação.

## Referências

Abra somente a referência que resolve uma dúvida concreta:

| Situação                                                     | Arquivo                          |
| ------------------------------------------------------------ | -------------------------------- |
| Entender o conteúdo esperado em cada seção                   | `references/content-contract.md` |
| Resolver fatos, preferências ou políticas divergentes        | `references/policy-authoring.md` |
| Descobrir instruções ativas, fallbacks ou limites do cliente | `references/source-discovery.md` |
| Executar os evals de navegação e fidelidade factual          | `references/evals.md`            |

## Exemplos

### Caso positivo

**Entrada:** “Cria um AGENTS.md para o monorepo e mostra onde começar em cada
serviço.”

**Saída esperada:** documentar o objetivo e os caminhos iniciais confirmados;
manter comandos e diferenças locais nos owners corretos; apontar o próximo
documento sem listar a árvore inteira.

### Caso negativo

**Entrada:** “Corrige um bug no serviço de pagamentos.”

**Por quê não:** a tarefa é corrigir código. Use a skill de domínio adequada se
necessário; só altere `AGENTS.md` se o usuário pedir essa documentação ou se uma
regra recorrente precisar ser registrada.

## Evals de trigger

Deve acionar:

- “Cria um AGENTS.md forte para este projeto.”
- “Documenta o objetivo e ensina o agente onde começar no código.”
- “Esse arquivo local deve repetir as regras do root?”
- “Revisa as instruções do meu monorepo e resolve o que está conflitante.”

Não deve acionar:

- “Cria uma skill com frontmatter e evals.” → `skill-governance`.
- “Qual arquitetura devo escolher?” → `architecture`.
- “Escreve um README de onboarding.” → documentação geral.
- “Troca npm por pnpm neste projeto.” → alteração de tooling.

## Evals de workflow

Os três cenários com assertions estão em `references/evals.md`. O estado da
execução com Luna Max fica registrado separadamente das validações estruturais.
