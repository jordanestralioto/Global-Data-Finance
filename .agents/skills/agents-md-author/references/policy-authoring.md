# Autoria de regras específicas do projeto

## Separe fatos, políticas e preferências

Faça três perguntas antes de escrever uma regra:

1. **O que existe?** Confirme comportamento em código, manifest, lockfile,
   configuração, CI ou teste executável.
2. **O que governa?** Leia as instruções, convenções, ownership e decisões
   aceitas que se aplicam ao alvo.
3. **O que o usuário prefere?** Registre uma preferência declarada sem alterar
   a descrição do estado real do projeto.

Materialize um fato com seu valor e caminho de alto roteamento quando ele muda
uma escolha recorrente. Materialize uma política quando sua fonte tem autoridade
para aquele escopo. Aplique uma preferência quando ela é explícita e compatível
com o contrato atual. Se a preferência exige uma migração ainda não feita,
descreva o estado existente e deixe a migração como trabalho planejado.

## Idioma e colaboração

Separe idioma de chat, código, comentários, documentação e Git. Uma mensagem
casual em determinado idioma não estabelece a política do repositório. Registre
uma preferência de chat sem usá-la para deduzir a língua de código ou docs.
Inclua uma regra de idioma no `AGENTS.md` quando o alvo a declarar ou uma
preferência explícita e compatível orientar decisões recorrentes.

## Ferramentas e comandos

Confirme o dependency manager em manifests e lockfiles; confronte comandos com
CI ou documentação operacional atual. Nomeie o framework e o padrão de
contribuição apenas quando o manifest, entrypoint, configuração ou arquitetura
confirmarem seu escopo.

Registre comandos que agentes realmente usam: setup, execução, testes,
formatter, lint, typecheck, build ou validação agregada. Prefira comandos
exatos e a fonte que os mantém. Não copie um gate roster inteiro para o
`AGENTS.md` se um único comando oficial e um link explicarem a rota.

## Regras duráveis

Acrescente políticas que mudam decisões recorrentes, como ownership de schemas,
limites de autorização, invariantes de dados, padrão arquitetural obrigatório,
compatibilidade pública ou fonte de geração de arquivos. Não registre detalhes
incidentais de funções nem uma preferência técnica como se já fosse arquitetura
implantada.

Mantenha orientação operacional curta e útil a qualquer cliente: proteja
segredos na comunicação, consulte fontes canônicas, nomeie divergências sem
inventar uma resposta e relate verificações que falharam ou foram ignoradas.
Permissões, ações destrutivas e controles mecânicos pertencem às regras do
cliente e aos hooks/gates que realmente existem no alvo; não invente esses
controles para preencher o documento.

## Quando fontes divergem

Registre os caminhos e as afirmações de cada fonte. Não use um fallback como
verdade resolvida, não escolha apenas pela recência do arquivo e não apresente
um plano como comportamento vigente. Continue com partes independentes e
descreva o ponto que ainda não tem uma regra confirmada. Peça decisão só quando
ela for necessária para documentar a próxima ação corretamente.
