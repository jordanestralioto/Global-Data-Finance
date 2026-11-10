# Behavioral Evals

Use artefatos reais ou fixtures autocontidas e registre os passos, decisões e
evidências do agente. Não dê a resposta esperada ao avaliador independente.
As assertions abaixo avaliam o workflow; testes do parser não demonstram ganho
comportamental da skill. Compare com uma execução sem a skill quando for medir
esse ganho; não atribua percentuais de utilidade sem esse experimento.

## 1. Retry e rollout com duas versões

**Pedido:** "A aplicação Ruby e workers ainda leem/escrevem `total_cents`.
Quero usar `amount_cents`; há escritas durante o backfill e reentrega de eventos.
Revisa o desenho e proponha implementação e validação."

Forneça schema e acessos mínimos, versão da engine quando conhecida e restrições
de deploy. Não é necessário ter um runtime Ruby instalado para revisar o contrato.

Assertions:

- [ ] Identifica os callers antigos e novos antes da remoção.
- [ ] Define como capturar escritas durante o backfill sem sobrescrever valores novos.
- [ ] Liga a deduplicação à identidade estável do evento e ao seu escopo.
- [ ] Trata replay com mesmo payload e conflito com payload diferente explicitamente.
- [ ] Inclui teste com escritores simultâneos e com versões coexistentes.
- [ ] Distingue plano proposto de validação realmente executada.

## 2. Ownership herdado por um filho

**Pedido:** "No serviço Go, `orders` tem `workspace_id`; `order_items` só tem
`order_id`. O acesso ao item faz join com o pedido e filtra o workspace.
Preciso duplicar `workspace_id` em cada item?"

Forneça schema, consultas e caminho de mutação. Inclua controle de escopo no
caminho confiável para permitir uma decisão baseada nos acessos reais.

Assertions:

- [ ] Avalia o caminho de autorização e a associação ao pai.
- [ ] Não declara BOLA só pela ausência da coluna na filha.
- [ ] Não apresenta FK ou índice como substituto de autorização.
- [ ] Se propuser duplicar escopo, explica como impedir divergência entre pai e filho.
- [ ] Pede/projeta controles positivos e tentativas cruzadas de leitura/mutação.

## 3. Modelos em outra linguagem e cobertura honesta

**Pedido:** "Este projeto Java tem modelos em `src/models`. Execute a triagem
portátil e diga o que já foi comprovado; a stack Java não está instalada."

Forneça modelos textuais e configuração nativa mínima do projeto, sem banco ativo.

Assertions:

- [ ] Usa o helper Python sem importar/executar a aplicação Java.
- [ ] Informa arquivos inventariados e análise semântica pendente.
- [ ] Não transforma exit 3/zero unidades em schema aprovado.
- [ ] Localiza a ferramenta nativa configurada ou explicita a informação faltante.
- [ ] Continua a análise independente possível sem inventar testes executados.

## 4. Cursor com empates

**Pedido:** "A listagem filtra workspace/status e usa cursor só por `created_at`.
Muitos registros têm o mesmo timestamp e entram pedidos durante a paginação."

Assertions:

- [ ] Define ordenação total com desempate único.
- [ ] Alinha cursor, predicado de continuação e índice à mesma ordem e filtros.
- [ ] Define o contrato sob inserções/updates entre páginas.
- [ ] Não afirma snapshot estável apenas pela presença de cursor.
- [ ] Não proíbe OFFSET sem considerar volume e necessidade de navegação.

## 5. Modo de relação e acesso async

**Pedido:** escolha um caso Prisma com `relationMode = "prisma"` e writer
externo, ou SQLAlchemy async com acesso a atributo expirado após commit.

Assertions:

- [ ] Confirma versão/configuração antes da recomendação específica.
- [ ] Distingue contrato do cliente e garantia efetiva no banco/runtime.
- [ ] Verifica SQL/caminho de execução em vez de inferir pela API do ORM.
- [ ] Escolhe prova observável para a falha descrita.

## 6. Fronteiras de trigger

Use pares próximos em linguagem informal e registre o destino:

| Pedido                                                         | Rota esperada                                                      |
| -------------------------------------------------------------- | ------------------------------------------------------------------ |
| "O SELECT deste endpoint está lento; tenho a query e o plano." | `database-design`, ou `supabase` se o centro for tuning específico |
| "O endpoint ficou lento, não sei se é rede ou banco."          | `performance-profiling`                                            |
| "Como garanto que jobs não criem dois registros iguais?"       | `database-design`                                                  |
| "Qual status HTTP retorno para o duplicado?"                   | `api-patterns`                                                     |
| "Meu schema conceitual tem ownership suficiente?"              | `database-design`                                                  |
| "A policy RLS permite tenant errado."                          | `supabase`                                                         |

Avalie a decisão de rota e o resultado da tarefa. Citar o nome de uma referência
ou reproduzir uma frase do corpo não é, por si só, uma assertion de comportamento.
