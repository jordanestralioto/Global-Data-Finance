# Context Discovery

Use este arquivo antes de comparar padrões. O objetivo é transformar um pedido
vago em um frame de decisão que explique por que a arquitetura precisa mudar.

## Descoberta mínima

Capture pelo menos estes blocos:

1. **Escopo real da decisão**
   O que exatamente está mudando: módulo, boundary frontend/backend, serviço,
   leitura vs escrita, job, integração externa, contrato público ou ownership?

2. **Problema e pressão atual**
   O problema é latência, falha em cascata, conflito de edição, deploy acoplado,
   regra duplicada, custo operacional, compliance ou dificuldade de evoluir?

3. **Stack e constraints existentes**
   Quais tecnologias, limites de equipe, janela de entrega, legado e contratos já
   existem? A arquitetura deve respeitar o repositório atual antes de propor ruptura.

4. **Evidência e lacunas**
   Quais fatos foram verificados em código, configuração, testes ou medições?
   Registre a fonte; marque hipóteses e preferências como tais. Busque respostas no
   projeto antes de perguntar ao usuário. Uma causa ainda não medida pede uma
   recomendação condicionada e o sinal que validaria a hipótese.

## Atributos de qualidade

Escolha os atributos que realmente decidem o caso. Nem todo cenário precisa de todos.

| Atributo              | Perguntas úteis                                                                                     |
| --------------------- | --------------------------------------------------------------------------------------------------- |
| Latência              | A resposta precisa ser imediata? O usuário espera feedback síncrono?                                |
| Consistência          | Pode haver leitura defasada ou conflito eventual?                                                   |
| Isolamento de falha   | Quando uma parte quebra, o resto do sistema pode continuar?                                         |
| Operabilidade         | Quem observa, sobe, debuga e reconcilia essa solução?                                               |
| Facilidade de mudança | O sistema muda toda semana ou é mais estável?                                                       |
| Verificabilidade      | Quais regras e contratos podem ser checados localmente, com entradas controladas?                   |
| Isolamento de mudança | Quais arquivos, contratos e estados outra pessoa ou agente precisa conhecer para editar esta parte? |
| Segurança/compliance  | A decisão mexe em segredo, auditoria, permissão ou trilha regulatória?                              |
| Custo                 | A solução adiciona infraestrutura, licenças ou dependência organizacional?                          |

## Perguntas por sintoma

### Carga e shape operacional

- O pico é de leitura, escrita, processamento em lote ou integração externa?
- O tráfego cresce junto ou partes diferentes escalam de formas diferentes?
- O problema é throughput contínuo ou cauda longa em casos raros?

### Consistência e ownership

- Existe uma fonte de verdade clara para os dados e regras?
- Mais de um ator edita o mesmo recurso?
- A decisão cria duplicação de regra ou de estado?

### Falha e blast radius

- Quando esta parte falha, qual parte do produto cai junto?
- Retries são seguros ou geram duplicidade?
- A falha precisa ser isolada por processo, deploy ou apenas por fila interna?

### Operação e observabilidade

- Quem vai manter a solução em produção?
- O time já tem tracing, fila, scheduler, alarms e runbooks para esse tipo de desenho?
- O custo de suporte da opção complexa cabe no estágio atual do produto?

### Verificabilidade e edição independente

- Quais comandos nativos verificam a fronteira? Descubra-os nas instruções e na
  configuração de build/teste, sem presumir linguagem, runner ou gerenciador.
- É possível exercitar regras locais com entradas controladas e dependências
  explícitas? Que falhas ainda exigem testes de integração ou ambiente externo?
- Quanto custa obter feedback e reproduzir uma falha: tempo, infraestrutura e
  acesso necessário? Registre custos medidos; identifique estimativas.
- Uma mudança exige entender estado global implícito ou editar um arquivo que
  concentra responsabilidades sem relação? Quais contratos limitam esse contexto?
- Se o projeto usa agentes em paralelo, existem ownership e pontos de integração
  explícitos? A divisão permite validar cada mudança e depois a integração?

Escolha esses atributos quando afetarem o risco dominante. Testabilidade e edição
independente também servem a pessoas; não exigem subagentes, nova infraestrutura
ou divisão em serviços. Gates locais complementam os testes das dependências reais.

### Reversibilidade

- Dá para migrar em etapas?
- O que fica caro de desfazer depois: contrato, dados, deploy, ownership, vendor?
- Quais sinais objetivos mostrariam que a decisão precisa ser revisitada?

## Saída esperada desta fase

Antes de escolher um padrão, o agente deveria conseguir preencher algo parecido com:

```yaml
decision_frame:
  scope: <fronteira em discussão>
  problem: <causa raiz>
  constraints:
    - <stack, prazo, legado, compliance, ownership>
  dominant_attributes:
    - <atributo 1>
    - <atributo 2>
    - <atributo 3>
  risks_if_unchanged:
    - <o que continua ruim se nada mudar>
```

Se esse frame ainda estiver vago, a comparação entre alternativas vai sair genérica.
