# API Lifecycle And Compatibility

> Mudança de contrato é produto, não detalhe de implementação.

## Estratégia de versionamento

Escolha a estratégia com base no tipo de consumidor:

- API pública ou multi-consumidor: versão explícita, geralmente em URI
- API interna com consumidor único e controlado: evolução sem versão pode ser aceitável
- GraphQL: evolua por adição e deprecation, não por `/v2`
- tRPC: tipos ajudam, mas breaking change continua sendo breaking change

## O que costuma ser breaking change

- remover campo
- mudar tipo ou nullability
- alterar semântica de código de erro
- trocar paginação offset por cursor sem transição
- mudar auth exigida para uma rota já publicada
- alterar formato do payload de webhook sem versionamento/documentação

Adicionar campo opcional costuma ser seguro, mas ainda pode afetar clientes frágeis
que fazem parsing rígido demais. Documente mesmo assim.

## Deprecation

Quando um endpoint, campo ou header for perder suporte:

- marque como deprecated na documentação/contrato
- avise alternativa recomendada
- mantenha período de transição claro
- registre data prevista de remoção

Headers úteis em HTTP:

```http
Deprecation: @1688169599
Sunset: Thu, 01 Oct 2026 00:00:00 GMT
Link: </api/v2/workspaces>; rel="successor-version"
```

`Deprecation` usa uma data estruturada com prefixo `@`, conforme
[RFC 9745](https://www.rfc-editor.org/rfc/rfc9745.html#section-2.1).
`Sunset` informa quando o recurso ficará indisponível; não confunda essa data
com o início da depreciação. Os valores acima são ilustrativos.

## Códigos e erros estáveis

- mantenha `code` estável entre versões quando possível
- não exponha detalhes internos só para "ajudar debug"
- prefira adicionar contexto seguro a trocar a semântica de erro existente

## Rollout seguro

- adicione antes de remover
- suporte período de dupla leitura/escrita quando necessário
- trate migração de cliente como parte da entrega
- monitore uso da rota antiga antes de desligar

## Webhooks e eventos

Eventos também têm lifecycle:

- versionar payload quando houver consumidores externos
- não remova campos sem comunicação
- documente ordering, retries e deprecation de event types

## Checklist

- Estratégia de versionamento compatível com o tipo de consumidor
- Breaking changes identificadas antes da implementação
- Deprecation com alternativa e data de sunset
- Error codes e paginação preservados com consistência
- Eventos e webhooks tratados como contrato versionado
