---
name: architecture
description: >-
  Use para decisões estruturais de software com trade-offs reais. Ative quando o
  usuário perguntar "isso fica onde na arquitetura?", "separo em módulos?", "crio outro
  serviço?", "vale usar fila?", "monólito ou serviço?", "isso está acoplado
  demais?", "preciso de ADR" ou "como organizo essa responsabilidade?". Cobre
  fronteiras, ownership, consistência, deploy, operabilidade, verificabilidade e
  custo de mudança.
  Não use para bugs isolados, refatorações locais delimitadas, escolha de
  índices, layout visual ou planos simples sem decisão arquitetural.
---

# Architecture

## Fundamentos não-óbvios

O melhor critério raramente é "o que times maiores costumam usar". Tamanho de
equipe, volume e maturidade influenciam a análise, mas não decidem sozinhos.
Escolha a menor mudança estrutural que resolva o risco dominante.

Simplicidade é default, não dogma. Adiar complexidade faz sentido quando o risco
principal continua coberto; ignorar falha, latência, consistência ou isolamento
porque "depois a gente vê" costuma apenas empurrar dívida para produção.

Descubra os comandos de build, teste e validação no repositório em análise. A
fronteira deve fazer sentido para a linguagem e o runtime existentes; a skill não
pressupõe framework, gerenciador de pacotes ou infraestrutura de um consumidor.

## Roteamento para referências

Leia apenas os arquivos relevantes para a decisão em mãos:

| Problema                                                      | Arquivo                            |
| ------------------------------------------------------------- | ---------------------------------- |
| Descobrir contexto, constraints e atributos de qualidade      | `references/context-discovery.md`  |
| Escolher padrões e fronteiras por sintomas e trade-offs       | `references/pattern-selection.md`  |
| Consultar padrões comuns, custos operacionais e disqualifiers | `references/patterns-reference.md` |
| Estruturar comparação, decisão, mitigação e ADR               | `references/trade-off-analysis.md` |
| Compor análise com sabatina, ADR e lifecycle formal           | `references/decision-handoffs.md`  |
| Ver o contrato esperado da resposta final                     | `references/output-contract.md`    |
| Ver exemplos concretos de decisões parecidas                  | `references/examples.md`           |

Use `api-patterns` para detalhar HTTP, handlers, authz, status codes ou contratos
de API. Para schema, tipos, constraints, migrations, índices e ownership dos dados,
use `database-design`; para auditar RLS, grants ou service role, use
`vulnerability-scanner`. Essas skills complementam a decisão de fronteira
quando ela continuar arquitetural. Dúvidas de organização local de
componente, hook ou módulo seguem para `modularizar` ou `frontend-design`.

Use `resolve-open-questions` quando houver intenção explícita de persistir ou
retomar a discussão. Use `openspec-workflow` para triar contrato compartilhado
duradouro, múltiplos consumidores ou owners independentes, rollout, rollback ou
auditoria. Muitas perguntas ou arquivos, sozinhos, não justificam esses fluxos.
Consulte `references/decision-handoffs.md` para preservar fases, autorizações e
o comportamento quando a skill de destino não estiver instalada.

## Procedimento

1. Classifique se a dúvida é realmente arquitetural antes de responder: escolher
   framework, banco ou ferramenta não basta. Pergunte se a decisão altera
   fronteiras, ownership, estratégia de deploy, consistência, blast radius,
   falha, observabilidade, contratos compartilhados ou custo de mudança. Se não
   alterar nada disso, redirecione para a skill mais apropriada.
   Se já houver sabatina ou lifecycle ativo, confira sua fase e limites de escrita
   antes de produzir ADR, plano ou implementação.

2. Descubra o contexto antes do padrão.
   Reúna problema real, sintomas, restrições, stack já existente, pressão de prazo,
   atributos de qualidade relevantes e o que precisa continuar fácil depois da
   mudança. Use `references/context-discovery.md`.
   Separe fatos verificados, hipóteses e preferências; não apresente um gargalo
   presumido como causa comprovada.

3. Escolha 3 a 5 critérios de avaliação antes de escolher alternativa.
   Exemplos: latência, consistência, custo operacional, isolamento de falha,
   facilidade de mudança, segurança, compliance, observabilidade e custo de deploy.
   Inclua verificabilidade e isolamento de mudanças quando decidirem o caso;
   suporte a trabalho com agentes não exige serviços separados nem subagentes.
   Não avalie tudo com o mesmo peso.

4. Compare pelo menos 2 alternativas reais.
   Inclua a opção mais simples que ainda possa resolver o problema. Se uma
   restrição comprovada impuser um caminho único, registre a razão e sua evidência
   em `alternatives_constraint`, conforme `references/output-contract.md`.
   Preserve os custos aceitos e os sinais que reabririam a escolha; não invente
   uma segunda opção inviável para completar a lista.

5. Explicite o custo operacional da alternativa escolhida.
   Fila, orquestração, retries, eventual consistency, tracing distribuído,
   coordenação entre times, múltiplos deploys ou repositórios, contrato público e
   migração incremental precisam aparecer como custo concreto, não como
   abstração elegante.

6. Recomende uma direção clara.
   A resposta final deve dizer qual opção vence, por que vence neste contexto, o
   que fica mais difícil depois dela, quais irreversibilidades foram aceitas e em
   que sinais a decisão deve ser revisitada. Sem dizer o que piora, a
   recomendação está incompleta.

7. Produza um ADR curto quando a decisão sobreviver à conversa.
   Se a escolha afetar mais de um owner, mais de um deploy, contrato público ou
   direção estrutural duradoura, siga `references/decision-handoffs.md` antes de
   emitir o registro. Em sabatina ainda aberta, declare o ADR adiado; depois do
   fechamento, use o fluxo de rascunhos da sabatina. Nos demais casos, use
   `references/trade-off-analysis.md` e `assets/adr-short-template.md`, respeitando
   a convenção de ADR e a autorização de escrita do projeto.

8. Se o usuário pedir implementação, use o contrato desta skill como checklist
   interno antes de editar código. Não pule direto para tecnologia específica sem
   fechar o problema estrutural.
   Use os gates nativos do projeto e separe o que eles comprovam das verificações
   de integração que ainda dependem de infraestrutura externa.

## Anti-patterns recorrentes

- Escolher microservices porque o sistema "vai crescer" sem evidência de fronteiras
  estáveis, necessidades de deploy independente ou benefício real de isolamento.
- Escolher fila para esconder operação síncrona mal modelada, sem contrato de job,
  idempotência, observabilidade e estratégia de falha.
- Escolher CQRS sem divergência real entre modelos de escrita e leitura, ou eventos
  sem necessidade de desacoplamento e tolerância operacional ao processamento assíncrono.
- Empurrar regra crítica para frontend quando ela define source of truth, segurança,
  compliance ou invariantes de negócio.
- Prescrever framework cedo demais. Framework entra depois que a fronteira, o fluxo
  e os atributos de qualidade já estão claros.
- Criar serviços, camadas ou repositórios apenas para dividir contexto entre
  agentes, quando contratos internos e ownership explícito resolvem o conflito.
- Tratar testes locais aprovados como prova de contratos ou falhas externas que
  esses testes não exercitam.

## Formato de saída recomendado

Uma decisão concluída entrega, em prosa:

- escopo, causa raiz, restrições e 3 a 5 atributos de qualidade com evidência;
- pelo menos duas alternativas reais, incluindo a mais simples viável; caminho
  único só com a restrição e a evidência que excluem as demais;
- uma vencedora explícita e os custos aceitos, que não podem ficar vazios;
- o que fica mais difícil depois e o que é difícil de desfazer;
- sinais observáveis para revisar a escolha e a necessidade de ADR.

Durante descoberta ainda aberta, explicite as lacunas e o caráter provisório da
recomendação. Leia `references/output-contract.md` quando o consumidor pedir o
YAML ou quando precisar das exceções e regras de qualidade detalhadas.

## Exemplos

### Caso positivo — isolamento sem overengineering

**Entrada:** "O módulo de importação trava o backend quando o provider demora. Extraio
um worker com fila ou deixo no app principal?"
**Saída esperada:** identificar atributos dominantes como latência, isolamento de
falha, retries, operabilidade e custo de deploy; comparar pelo menos job interno,
worker isolado e serviço separado; recomendar a menor fronteira que resolva o risco
principal; incluir revisit trigger e ADR curto se a decisão for duradoura.

### Caso positivo — fronteira de responsabilidade

**Entrada:** "Essa regra de cálculo de risco fica no frontend ou no backend?"
**Saída esperada:** avaliar source of truth, sensibilidade da regra, necessidade
de consistência, custo de duplicação e impacto em UX; recomendar backend para a
invariante central e frontend apenas para projeção ou visualização se fizer sentido.

### Caso negativo

**Entrada:** "Onde coloco esse hook do React no meu repositório?"
**Por quê não:** decisão local de organização e implementação. Direcione para
`modularizar`, `frontend-design` ou `react-performance`.

## Assets

- `assets/adr-short-template.md`: template enxuto para decisões persistentes, com
  contexto, decisão, trade-offs, consequências e revisit trigger.
