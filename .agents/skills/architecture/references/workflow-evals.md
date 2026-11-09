# Workflow Evals

Use estes cenários para revisar instruções e avaliar comportamento após mudanças.
O validador mecânico verifica estrutura; ele não executa os prompts nem comprova
eficácia da skill.

## Protocolo de avaliação

1. Compartilhe os prompts e fixe as assertions antes das execuções. Forneça o
   contexto descrito em cada caso como fixture, sem acesso a dados de produção.
2. Para medir ganho, execute cada caso em sessões independentes com e sem esta
   skill, mantendo modelo, versão, harness, outras instruções, ferramentas,
   fixture e orçamento iguais. Evite contexto herdado da outra condição.
3. Repita cada condição ao menos 3 vezes e registre sucessos sobre o total por
   assertion. Registre recusas, falhas de ferramenta, tempo e custo disponíveis.
4. Preserve prompts, contexto, versão da skill, transcrições e saídas brutas no
   local de evidência escolhido pelo projeto. Confira as ações nas transcrições:
   dizer que não escreveu arquivos não comprova ausência de escrita.
5. Relate regressões, amostra e limitações junto do ganho observado. Revisão manual,
   cenários apenas escritos e checks estruturais ficam identificados como tais;
   sem execução pareada, não declare melhoria de eficácia medida.

As assertions abaixo admitem verificação por presença, contagem ou ação observada.
Quando a resposta usar prosa, confira a informação equivalente aos campos do
contrato; não exija YAML para considerar o caso aprovado.

## Eval 1: gatilho informal deve acionar

**Prompt:** "Como separo esses módulos sem virar um Frankenstein?"

**Assertions:**

- [ ] pergunta ou investiga quais responsabilidades e contratos estão acoplados
- [ ] nomeia uma fronteira, ownership ou custo de mudança na análise
- [ ] não escolhe framework ou cria arquivos antes de obter esse contexto

## Eval 2: detalhe local não deve acionar

**Prompt:** "Onde coloco esse hook do React?"

**Assertions:**

- [ ] trata a pergunta como organização local de código
- [ ] encaminha para `modularizar` ou `frontend-design`, sem iniciar lifecycle formal
- [ ] não propõe microservice, DDD ou boundary estrutural

## Eval 3: recomendação com trade-off explícito

**Prompt:** "Extraio um worker ou deixo essa importação no backend principal?"

**Contexto:** provider tem cauda longa medida que ocupa os slots do servidor;
o usuário tolera conclusão posterior e o time já opera uma fila monitorada.

**Assertions:**

- [ ] compara pelo menos 2 opções reais, incluindo o mesmo deploy
- [ ] nomeia a opção vencedora e a relaciona à ocupação dos slots
- [ ] explicita pelo menos um custo operacional aceito
- [ ] descreve o que ficará mais difícil depois da escolha

## Eval 4: frontend vs backend

**Prompt:** "Essa regra de risco fica no frontend ou no backend?"

**Contexto:** a regra determina elegibilidade e precisa valer também para clientes
que não usam a interface web.

**Assertions:**

- [ ] coloca a invariante de elegibilidade no backend
- [ ] distingue decisão autoritativa de visualização ou estado derivado no frontend
- [ ] explicita pelo menos um custo de duplicação ou divergência

## Eval 5: ADR obrigatório

**Prompt:** "Decidimos isolar billing em deploy separado. Mostre o ADR na conversa."

**Contexto:** decisão confirmada, sem sabatina ou lifecycle ativo e sem template
próprio do projeto.

**Assertions:**

- [ ] inclui ADR curto
- [ ] ADR não contém placeholders em aberto
- [ ] existe nota de migração ou rollback
- [ ] existe revisit trigger objetivo
- [ ] nenhuma ferramenta escreve arquivos

## Eval 6: CQRS rejeitado por exagero

**Prompt:** "Quero usar CQRS porque a dashboard está lenta."

**Assertions:**

- [ ] pede evidência do problema dominante
- [ ] compara CQRS com alternativa mais simples
- [ ] rejeita CQRS se a dor puder ser resolvida sem separar modelos

## Eval 7: caminho único imposto por evidência

**Prompt:** "Registre os custos de manter o job no processo atual."

**Contexto:** a decisão já está imposta por `deployment-contract.md:12`, cujo
conteúdo fornecido exige executar o job no processo atual até a revisão contratual;
workers e serviços externos estão explicitamente fora do escopo.

**Assertions:**

- [ ] descreve uma única opção viável no escopo
- [ ] preenche `alternatives_constraint.reason` e referencia a evidência fornecida
- [ ] registra custos aceitos e o que fica mais difícil
- [ ] identifica a revisão contratual como sinal para reabrir a escolha

## Eval 8: preferência não comprova caminho único

**Prompt:** "Gosto de microservices. Essa importação precisa de serviço próprio?"

**Contexto:** uma equipe, mesmo ritmo de deploy, operação curta e carga dentro do
orçamento medido; não existe restrição externa nem benefício de isolamento medido.

**Assertions:**

- [ ] compara pelo menos 2 opções, incluindo manter no módulo ou deploy atual
- [ ] não usa preferência por microservices como `alternatives_constraint`
- [ ] nomeia custo operacional do serviço separado

## Eval 9: sabatina aberta adia ADR

**Prompt:** "Analise as fronteiras e o ADR que vamos precisar depois."

**Contexto:** sabatina ativa, ownership ainda pendente e escrita autorizada somente
no seu documento. Execute uma variante em `em andamento` e outra em
`aguardando confirmacao`.

**Assertions:**

- [ ] identifica a recomendação como provisória e ownership como pendente
- [ ] declara ADR necessário, com emissão adiada até o fechamento confirmado
- [ ] nenhuma ferramenta cria ADR, rascunho, change ou código
- [ ] eventual escrita se limita ao documento autorizado da sabatina

## Eval 10: sabatina fechada preserva seu rascunho

**Prompt:** "Prepare o registro da decisão arquitetural que acabamos de confirmar."

**Contexto:** sabatina `fechada`, decisão estrutural qualificada com procedência e
template de rascunho fornecidos pelo fluxo. A autorização permite rascunhos e
handoff, sem iniciar a rota seguinte.

**Assertions:**

- [ ] usa o template do fluxo, com rascunho sem número e vínculo à decisão de origem
- [ ] nenhuma ferramenta promove ADR ao catálogo canônico
- [ ] nenhuma ferramenta inicia plano, change ou implementação

## Eval 11: perguntas pontuais não iniciam persistência

**Prompt:** "Antes de desenhar, quais riscos e opções você enxerga?"

**Contexto:** várias dúvidas abertas, sem pedido de registro ou retomada futura e
sem fronteira formal de contrato, rollout ou auditoria.

**Assertions:**

- [ ] responde na conversa e identifica as lacunas que afetam a recomendação
- [ ] não inicia sabatina persistente nem exige sua abertura para continuar a análise
- [ ] nenhuma ferramenta cria documento, change ou código

## Eval 12: fronteira formal encaminha para triagem

**Prompt:** "Vamos mudar o contrato público consumido por três projetos, com
migração gradual e rollback. Qual direção recomenda?"

**Contexto:** `openspec-workflow` disponível; pedido de análise, sem autorização
para escrita formal.

**Assertions:**

- [ ] encaminha para triagem em `openspec-workflow` e cita a fronteira formal
- [ ] entrega problema, alternativas, custos e premissas para o handoff
- [ ] nenhuma ferramenta cria ou modifica artefatos de lifecycle

## Eval 13: verificabilidade respeita a stack do consumidor

**Prompt:** "Onde separo as regras do provider para conseguir validá-las localmente?"

**Contexto:** regras puras estão misturadas à integração externa; o projeto tem um
check local e outro de integração declarados no README. Repita com estas fixtures:

| Linguagem | Check local declarado       | Integração declarada              |
| --------- | --------------------------- | --------------------------------- |
| Python    | `uv run pytest tests/unit`  | `uv run pytest tests/integration` |
| Go        | `go test ./internal/domain` | `go test ./integration`           |
| Rust      | `cargo test --lib`          | `cargo test --test provider`      |

**Assertions:**

- [ ] compara ao menos 2 fronteiras e menciona dependências explícitas nas regras
- [ ] usa os comandos da fixture ao descrever verificações, sem trocar a toolchain
- [ ] distingue a cobertura local da validação do provider real
- [ ] não declara um check executado ou aprovado sem resultado de ferramenta

## Eval 14: contexto de agentes não exige serviços

**Prompt:** "Pessoas e agentes conflitam no mesmo módulo. Criamos serviços?"

**Contexto:** deploy e escala independentes não são necessários; um arquivo mistura
regras e integrações com estado global. O projeto admite módulos no mesmo deploy.

**Assertions:**

- [ ] compara módulos com contratos internos à separação de serviços
- [ ] identifica estado compartilhado e ownership como pontos de coordenação
- [ ] recomenda isolar mudanças no mesmo deploy antes de acrescentar serviços
- [ ] não torna subagentes um pré-requisito da solução

## Eval 15: skill de destino ausente

**Prompt:** "Analise a mudança de contrato público de dois consumidores independentes."

**Contexto:** somente `architecture` está instalada; nenhum lifecycle está ativo.

**Assertions:**

- [ ] informa o motivo do encaminhamento e a ausência de `openspec-workflow`
- [ ] entrega a análise arquitetural na conversa
- [ ] não inventa comando, instala componentes ou cria lifecycle substituto
- [ ] não usa caminhos da central nem arquivos de outro consumidor
