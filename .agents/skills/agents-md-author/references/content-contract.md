# Contrato de conteúdo para `AGENTS.md`

## Estrutura raiz

O template sugere cinco headings de nível 2, nesta ordem:

1. `## Project Overview`
2. `## Architecture & Ownership`
3. `## Development Workflow`
4. `## Engineering Rules`
5. `## Documentation Map`

Cada bloco deve ter conteúdo útil. Seções adicionais são permitidas quando
respondem a uma pergunta recorrente ou mudam uma decisão de trabalho. Traduza
os títulos quando a política explícita do repositório alvo exigir outro idioma;
preserve as cinco funções e a ordem sugerida.

### Project Overview

Resuma o que o projeto faz, seus consumidores e limites importantes. Inclua
invariantes que mudem uma decisão de implementação. Não transforme a abertura
em um catálogo de dependências, serviços ou diretórios.

### Architecture & Ownership

Mostre por onde começar no código e como as responsabilidades fluem. Nomeie
entrypoints, owners, fronteiras e pontos de extensão estáveis quando eles
evitam editar a camada errada. Encaminhe detalhes internos para o documento ou
módulo que os mantém.

### Development Workflow

Registre comandos exatos confirmados para setup, execução, testes e validação.
Inclua formatter, linter, type checker ou build somente quando o projeto usa
essas ferramentas. Prefira o gate agregado oficial quando ele cobre as etapas;
aponte para a configuração owner quando o roster completo já existe nela.

### Engineering Rules

Preserve as práticas portáteis do template: inspecionar a fonte responsável,
respeitar contratos e boundaries, manter mudanças coesas, atualizar testes e
documentação afetados, validar proporcionalmente e relatar falhas ou skips.
Acrescente regras específicas do projeto quando estiverem confirmadas por
política ou comportamento atual. Não copie para cá cada regra de linter ou
configuração mecânica que um hook já impõe.

### Documentation Map

Ordene poucos links existentes pela pergunta que respondem: começar, entender a
arquitetura, desenvolver, operar, testar, consultar contratos ou decisões.
Explique qual abrir primeiro e qual documento possui os detalhes. Não use uma
lista de diretórios como substituto de navegação.

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

Mantenha um detalhe quando ele identifica onde começar, quem possui uma
responsabilidade, qual boundary preservar ou como validar uma mudança
recorrente. Encaminhe defaults, schemas, inventários extensos e anatomia que não
mude uma decisão para seu owner canônico.

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

- `--scope root` (padrão): exige pelo menos cinco seções de nível 2, distintas e
  não vazias, além de verificar marcadores de autoria e links Markdown
  relativos; aceita seções extras. Quando os cinco títulos padrão são usados,
  confere também sua ordem. Com títulos traduzidos, a revisão factual deve
  confirmar que as cinco funções estão presentes.
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
Use somente um orçamento confirmado para o alvo, sem default universal por
linguagem, número de linhas ou escopo.

A CLI mede um arquivo; ela não descobre instruções ancestrais, configura o
cliente, confirma carregamento ou verifica o orçamento da cadeia combinada.
Faça essa conferência com `references/source-discovery.md`. Um gate de tamanho
obrigatório pertence à política do alvo: por exemplo, `.max-lines.toml` pode
classificar `**/AGENTS.md` como `documentation` quando esse gate for adotado.
