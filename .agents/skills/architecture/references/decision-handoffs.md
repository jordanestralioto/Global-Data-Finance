# Decision Handoffs

Use esta referência para compor a análise com um fluxo de decisão existente.
`architecture` avalia fronteiras e trade-offs; o fluxo ativo continua responsável
por persistência, fases, promoção de decisões e autorização de implementação.

## Descobrir o fluxo no projeto

- Leia as instruções locais e o documento ativo, quando houver. Descubra onde o
  projeto registra decisões e quais comandos validam seus artefatos.
- Reutilize decisões e autorizações já concedidas no escopo atual. Uma recomendação
  arquitetural não amplia por si só a permissão para escrever ou implementar.
- Use a skill de destino se estiver disponível. Se ela não estiver instalada,
  informe a rota, o motivo e o componente necessário; entregue a análise na
  conversa, sem inventar comandos ou caminhos para reproduzir o lifecycle.
- Resolva referências e assets pelo pacote instalado. Registros pertencem ao
  repositório em análise; não dependem de caminhos da central nem de outro projeto.

## Dúvidas abertas e sabatina

Ter dúvidas abertas exige investigação e perguntas pontuais, não uma sessão
persistente automática. Encaminhe para `resolve-open-questions` quando o usuário
pedir uma sabatina persistente, registro das decisões ou retomada futura. Deixe o
preflight, a confirmação inicial e a abertura do documento com essa skill.

Se uma sabatina já estiver ativa, a fase registrada governa a emissão de ADR:

| Fase                     | Papel da análise arquitetural                                              | ADR e implementação                               |
| ------------------------ | -------------------------------------------------------------------------- | ------------------------------------------------- |
| `em andamento`           | Alimentar dúvidas, fatos, alternativas e premissas no documento autorizado | ADR adiado; nenhuma implementação                 |
| `aguardando confirmacao` | Esclarecer o entendimento; correções reabrem a discussão                   | ADR adiado; nenhuma implementação                 |
| `fechada`                | Usar as decisões confirmadas e sua procedência                             | Seguir o fluxo de rascunhos e handoff da sabatina |

Depois de `fechada`, a sabatina classifica as decisões que qualificam para ADR,
usa seu próprio template de rascunho sem número e liga cada rascunho às decisões
que o sustentam. Não substitua esse template pelo ADR curto desta skill nem
promova o rascunho ao catálogo canônico. O workflow seguinte respeita a autorização
própria de sua rota; confirmar o entendimento não inicia implementação.

## Fronteira formal e OpenSpec

Encaminhe para triagem em `openspec-workflow` quando houver pedido explícito do
workflow ou evidência de contrato compartilhado duradouro, múltiplos consumidores
ou owners independentes, rollout, rollback ou lifecycle auditável.

Entregue o problema, as alternativas, os custos, a evidência dessa fronteira e as
premissas ainda abertas. A skill de destino escolhe a rota e aplica seus
guardrails antes da primeira escrita formal. Quantidade de arquivos ou passos e
a simples discussão de arquitetura não bastam para criar uma change.

Quando já existir uma change, vincule a análise ao artefato correspondente em vez
de abrir um registro paralelo com decisão divergente. Preserve o status proposto
ou aceito definido pelo lifecycle do projeto.

## ADR fora de uma sabatina

Siga os critérios de `output-contract.md` e a convenção local. Sem uma convenção
de registro definida, entregue o ADR curto na conversa; a escolha de um diretório
não deve ser presumida a partir de outro consumidor.

Use `../assets/adr-short-template.md` se o projeto não fornecer template próprio.
Marque como `Proposed` uma recomendação ainda não aceita. Use `Accepted` somente
quando houver decisão confirmada e o lifecycle permitir esse status. Rascunhos
ainda não promovidos conservam o status proposto do registro. Persistir o registro
exige escopo de escrita autorizado; em consulta, entregue o conteúdo na resposta,
com status sustentado pela evidência e sem criar arquivos por iniciativa da skill.
