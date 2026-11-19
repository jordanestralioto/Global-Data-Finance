# Contrato de conteúdo para `AGENTS.md`

## Sumário

- [Por que enxuto](#por-que-enxuto)
- [Estrutura raiz](#estrutura-raiz)
- [Arquivos locais](#arquivos-locais)
- [Evidência e concisão](#evid%C3%AAncia-e-concis%C3%A3o)
- [Inicialização portátil](#inicializa%C3%A7%C3%A3o-port%C3%A1til)
- [Validação estrutural](#valida%C3%A7%C3%A3o-estrutural)

## Por que enxuto

Um estudo de 2026 com vários agentes
([Gloaguen et al., arXiv:2602.11988](https://arxiv.org/abs/2602.11988)) mediu
que arquivos de contexto gerados por LLM reduziram a taxa de sucesso, os
escritos por desenvolvedores renderam ganho de até cerca de 4% e os arquivos
elevaram o custo de inferência em mais de 20%. Os agentes seguiram as
instruções: citar uma ferramenta ou rotina de testes aumentou seu uso. Visões
gerais do repositório, várias delas listas de diretórios, não reduziram os
passos até os arquivos certos. O estudo cobre repositórios Python, mede só a
resolução de tarefas verificadas por testes e não avaliou declarações de
propósito ou prioridades. Por isso o conteúdo raiz é curto e só contém o que
mudaria uma decisão do agente: propósito e prioridades que o código não mostra,
comandos exatos, convenções fora do padrão e rotas ligadas a erros já
observados.

## Estrutura raiz

O template sugere quatro headings de nível 2: `Project Overview`,
`Development Workflow`, `Engineering Rules` e `Navigation`. Nenhum é
obrigatório. Funda, renomeie, reordene ou omita seções conforme o alvo; traduza
os títulos quando a política explícita do repositório exigir outro idioma.
Arquivos que ainda usam as cinco seções anteriores continuam válidos.

### Project Overview

Uma ou duas frases sobre o que o projeto é, que problema resolve e para quem,
mais o limite ou invariante que muda onde o trabalho deve acontecer. Mantenha o
propósito mesmo quando o README também o descreve: o `AGENTS.md` entra em toda
sessão, e o README só quando o agente decide abri-lo. Aponte para o README em
vez de repetir detalhes.

Acrescente o que o projeto prioriza quando objetivos conflitam e o que fica
fora de escopo. Prioridade é política, não fato: a fonte é uma decisão
registrada ou o próprio usuário, nunca uma inferência a partir do código. Sem
fonte, deixe-as fora do documento e pergunte por elas na devolutiva, sem
bloquear o restante. Corte qualquer frase que serviria para qualquer projeto,
como "qualidade, performance e manutenibilidade".

### Development Workflow

Registre comandos exatos confirmados para setup, execução, testes e validação.
Inclua formatter, linter, type checker ou build somente quando o projeto usa
essas ferramentas. Prefira o gate agregado oficial quando ele cobre as etapas;
aponte para a configuração owner quando o roster completo já existe nela.

### Engineering Rules

Só regras que o agente erraria sem ler: convenções fora do padrão, arquivos
gerados e seu gerador, invariantes de dados ou segurança, compatibilidade
pública e erros que agentes ou revisões já cometeram. Não pré-preencha práticas
que agentes seguem por padrão, como inspecionar antes de editar, manter
mudanças coesas ou atualizar testes. Não copie regras que um hook ou linter já
impõe.

### Navigation

Só rotas que o agente não encontraria rápido: qual caminho possui uma
responsabilidade e qual documento responde a qual pergunta, com o momento de
lê-lo. Não use uma lista de diretórios como substituto de navegação.

## Arquivos locais

Um `AGENTS.md` sob uma subárvore herda as instruções aplicáveis de seus
ancestrais. Ele registra somente diferenças locais de stack, ownership,
comandos, contratos, riscos ou navegação. Repita uma regra compartilhada apenas
quando o contexto local exige uma exceção que seria difícil perceber de outra
forma. Quando não houver um root document, escreva só regras que realmente
governam o escopo local.

## Evidência e concisão

Separe quatro tipos de afirmação:

- comportamento técnico confirmado por código, manifest, CI, teste ou
  documentação atual;
- política confirmada por instruções, governança ou decisão do projeto;
- preferência explicitamente declarada pelo usuário;
- questão desconhecida ou fontes atuais conflitantes.

Não converta preferência em fato nem um plano futuro em política atual. Quando
fontes discordarem, nomeie cada fonte e a afirmação que ela sustenta; não
invente uma resolução. Continue com fatos independentes e peça decisão somente
quando o conflito impedir a orientação correta.

Contexto da sessão, caminhos absolutos do ambiente e limites particulares do
cliente pertencem à devolutiva. Não os copie para instruções reutilizáveis sem
uma política compartilhada do alvo que justifique sua presença. Caminhos e
comandos dos exemplos da skill também não comprovam fatos do projeto.

Mantenha um detalhe só quando o agente erraria sem ele: onde começar quando não
é óbvio, qual boundary preservar ou como validar uma mudança recorrente.
Encaminhe defaults, schemas, inventários extensos e anatomia que não mude uma
decisão para seu owner canônico. Mire em menos de 200 linhas por arquivo, a
meta documentada pelo Claude Code; para o Codex, o limite combinado da cadeia
está em `references/source-discovery.md`.

Não exija tabela de métricas, superfície de configuração, comandos ou
documentação. Use tabelas quando melhorarem comparação ou consulta; não invente
targets de qualidade para preencher uma estrutura.

## Inicialização portátil

`scripts/init_agents_md.py --output <path/to/AGENTS.md>` copia o template raiz
distribuído com a skill. O diretório de destino precisa existir; arquivo ou
link existente não é sobrescrito. `--stdout` imprime o template sem criar
arquivos. O resultado é um rascunho com marcadores de autoria, não documentação
factual pronta. Para uma orientação local, escreva somente o delta da subárvore.

Os dois helpers usam apenas a biblioteca padrão de Python e resolvem o template
a partir da própria skill instalada. Execute-os com um intérprete disponível;
não adicione Python às dependências do projeto, nem deduza sua linguagem ou
seus comandos a partir do intérprete usado para a documentação.
As saídas padrão e de erro dos helpers usam UTF-8, inclusive quando o ambiente
configura outro encoding, para preservar caminhos com acentos.

## Validação estrutural

`scripts/validate_agents_md.py` oferece dois escopos:

- `--scope root` (padrão): exige pelo menos uma seção de nível 2 e rejeita
  seções vazias ou duplicadas, além de verificar marcadores de autoria e links
  Markdown relativos. Não exige nomes, quantidade nem ordem de seções.
- `--scope local`: exige apenas conteúdo não vazio e aceita links relativos e
  marcadores da mesma forma, sem exigir os headings herdados do root.

Comentários HTML não contam como seções raiz nem como conteúdo dessas seções.
Marcadores de autoria nos comentários continuam sendo verificados. Destinos de
links malformados geram erros no relatório estrutural, sem interromper sua emissão.

O JSON `agents-md-policy.v3` identifica o escopo e a checagem como
`structural`. Uma saída aprovada não comprova comandos, arquitetura, owners ou
políticas. Faça a revisão factual com as fontes do alvo e relate-a
separadamente; não exija status de aprovação formal.

`TODO`, `TBD`, `FIXME` e `YYYY-MM-DD` em código inline são literais permitidos,
como uma regra sobre comentários `TODO` ou um formato de data. No texto comum,
continuam sinalizando possível autoria incompleta. Marcadores explícitos como
`[PROJECT_NAME]`, `{{TEST_COMMAND}}`, `<replace this>` e `AGENTS_AUTHOR` continuam
sendo rejeitados mesmo dentro de código inline. Exemplos em blocos cercados de
código não são inspecionados por esses checks.

### Tamanho e orçamento opcional

`--size-report` acrescenta `size` e `warnings` ao JSON, sem alterar os campos
padrão. `size` contém `utf8_bytes`, `lines` e `max_bytes` (`null` quando não
informado). A contagem de bytes inclui o arquivo UTF-8 completo, com comentários
e finais de linha. Sem essas opções, o formato e os códigos `0/1/2` permanecem
iguais. Falhas de leitura ou encoding retornam `2` sem medidas de tamanho.

`--max-bytes <inteiro positivo>` implica `--size-report` e emite um aviso quando
o arquivo ultrapassa esse orçamento. Igualar o orçamento é permitido. O aviso não
altera o status ou o código estrutural; erros de estrutura continuam falhando.
A CLI não bloqueia por tamanho: a meta de 200 linhas orienta a autoria, e
`--max-bytes` serve para um orçamento confirmado pelo alvo.

A CLI mede um arquivo; ela não descobre instruções ancestrais, configura o
cliente, confirma carregamento ou verifica o orçamento da cadeia combinada.
Faça essa conferência com `references/source-discovery.md`. Um gate de tamanho
obrigatório pertence à política do alvo: por exemplo, `.max-lines.toml` pode
classificar `**/AGENTS.md` como `documentation` quando esse gate for adotado.
