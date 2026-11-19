---
name: agents-md-author
description: >-
  Use para criar, revisar ou enxugar um `AGENTS.md` com o que agentes não
  descobririam sozinhos: comandos exatos, regras e gotchas do repositório e
  rotas não óbvias no código. Ative quando o usuário pedir "cria um agents.md",
  "documenta o projeto para agentes", "meu AGENTS.md está grande demais",
  "onde o agente deve começar?" ou uma revisão de instruções locais em um
  monorepo. Abrange documentos raiz e de subárvore. Para criar ou revisar
  skills, use `skill-governance`; para decidir arquitetura, `architecture`. Não
  use para escrever um README comum.
---

# AGENTS.md Author

## Procedimento

1. Determine o caminho do documento e o escopo que ele governa. Descubra a raiz
   do repositório e o diretório de início da sessão; leia as instruções que o
   cliente realmente aplica nessa cadeia. Confira arquivos `AGENTS.override.md`,
   `AGENTS.md` e nomes de fallback somente quando o cliente os reconhecer ou
   estiver configurado para carregá-los. Relate dados da sessão na devolutiva;
   leve-os ao documento somente quando forem política compartilhada do projeto.
   Consulte
   `references/source-discovery.md` se a cadeia, os fallbacks ou os limites do
   cliente não forem óbvios.

2. Leia o documento alvo antes de editar. Para afirmações necessárias, confirme
   a fonte responsável em código, manifest, CI, testes, governança ou
   documentação atual. Use somente os arquivos e subsistemas relevantes; nome
   de diretório, preferência isolada ou plano não comprova um fato atual. Não
   trate caminhos ou comandos dos exemplos da skill como fatos do alvo. Não
   abra valores de `.env`, credenciais ou cofres.

   Para documentar validação, confronte manifest/task runner, documentação e CI
   existente. Inclua arquivos ocultos ao localizar CI, como `.github/workflows/`;
   `rg --files` sem `--hidden` pode omiti-los.

3. Ao criar uma orientação raiz, use `assets/AGENTS.template.md`. Ao revisar um
   arquivo existente, proponha cada corte com o motivo e preserve regras válidas
   fora do pedido. Uma orientação local herda a política aplicável acima dela e
   registra somente diferenças da subárvore. Para copiar o esqueleto raiz sem
   sobrescrever um arquivo, use
   `python3 <skill-directory>/scripts/init_agents_md.py --output <path/to/AGENTS.md>`;
   `--stdout` permite inspecioná-lo sem gravar.

4. Escreva só o que muda o comportamento do agente. Agentes seguem essas
   instruções à risca e cada linha custa contexto em toda tarefa; mapas de
   diretórios, listas de componentes e práticas que o agente já segue por padrão
   aumentam o custo sem melhorar o resultado. Priorize, nesta ordem:

   - comandos exatos, com flags, que o agente não deduziria do manifest;
   - regras e gotchas não óbvios: convenções fora do padrão, arquivos gerados e
     seu gerador, invariantes e erros que agentes ou revisões já cometeram;
   - rotas não óbvias: qual caminho possui uma responsabilidade e qual documento
     responde a qual pergunta.

   Para cada linha, pergunte se o agente erraria sem ela; se não, corte. Não
   repita o README nem a árvore de diretórios, mas mantenha o propósito do
   projeto: este arquivo entra em toda sessão, e o README só quando o agente
   decide abri-lo. O que o projeto prioriza quando objetivos conflitam e o que
   fica fora de escopo vêm de uma decisão registrada ou do usuário; sem fonte,
   pergunte na devolutiva em vez de deduzir do código. Mire em menos de 200
   linhas por arquivo. O template sugere `Project Overview`,
   `Development Workflow`, `Engineering Rules` e `Navigation`; funda, renomeie,
   traduza conforme a política do alvo ou omita as que não acrescentam nada.

5. Registre regras específicas somente quando forem fatos ou políticas
   confirmados no alvo: idioma, `__init__.py`, manager, framework e regras de
   qualidade não entram por suposição. Um erro que o agente repetiu ou que uma
   revisão pegou é o candidato mais forte a regra. O Python executa os helpers
   da skill; não implica que o projeto use Python, `uv` ou qualquer outra stack.
   Consulte `references/policy-authoring.md` quando houver escolha de política
   ou fontes conflitantes.

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

   Acrescente `--size-report` para conferir bytes UTF-8 e linhas contra a meta
   de 200 linhas. Se o alvo tiver um orçamento confirmado por arquivo,
   `--max-bytes <bytes>` emite aviso ao ultrapassá-lo, sem mudar o resultado
   estrutural. A medida de um arquivo não valida a cadeia do cliente. Os
   detalhes de marcadores, tamanho e inicialização estão em
   `references/content-contract.md`.

## Referências

Abra somente a referência que resolve uma dúvida concreta:

| Situação                                                     | Arquivo                          |
| ------------------------------------------------------------ | -------------------------------- |
| Entender o conteúdo esperado em cada seção                   | `references/content-contract.md` |
| Resolver fatos, preferências ou políticas divergentes        | `references/policy-authoring.md` |
| Descobrir instruções ativas, fallbacks ou limites do cliente | `references/source-discovery.md` |

## Exemplos

### Caso positivo

**Entrada:** “Cria um AGENTS.md para o monorepo e mostra onde começar em cada
serviço.”

**Saída esperada:** registrar comandos confirmados, regras não óbvias e o
caminho inicial de cada serviço; manter diferenças locais nos arquivos de cada
serviço; apontar o próximo documento sem repetir o README nem listar a árvore.

### Caso positivo

**Entrada:** “Meu AGENTS.md tem 400 linhas; enxuga sem perder o que importa.”

**Saída esperada:** propor cortes com motivo (trechos colados do README, árvore
de diretórios, práticas que o agente já segue, regras que um lint impõe) e
manter propósito, prioridades, comandos, gotchas e rotas confirmados.

### Caso negativo

**Entrada:** “Corrige um bug no serviço de pagamentos.”

**Por quê não:** a tarefa é corrigir código. Use a skill de domínio adequada se
necessário; só altere `AGENTS.md` se o usuário pedir essa documentação ou se uma
regra recorrente precisar ser registrada.
