---
name: systematic-debugging
description: >-
  Use para debugging estruturado quando a causa raiz for incerta. Ative com "não
  sei por que quebra", "acha a causa raiz", "bug intermitente", "funciona na
  minha máquina", "CI passa mas local falha", "deu stack trace", "módulo não
  encontrado", "import quebrou", "env não carrega" ou "por que esse erro
  acontece?". Cobre reprodução, isolamento de hipóteses e validação de correção.
  Não use para problemas já identificados como performance, validação final de
  testes ou bugs com causa e correção já delimitadas.
---

# Systematic Debugging

## Fundamentos

- **Sintoma vs Causa Raiz:** Se a superfície visível mostra um erro, a falha raramente nasce exatamente ali. O problema pode estar na entrada, na camada intermediária, na integração ou no armazenamento. Depurar a borda errada desperdiça tempo.
- **O Anti-Pattern do "Chute Cego":** Alterar o código baseado em suposições ("Acho que se eu mover essa lógica resolve") sem reproduzir o bug antes destrói a base de código a longo prazo. Você só pode alterar código de produção quando a Causa Raiz for PROVADA.
- **Isolamento de Variáveis:** Se o bug só ocorre em uma rota, fluxo, job ou comando, não mude componentes globais sem evidência. Se o log mostra dezenas de mensagens, comece pela primeira falha material.
- **Ambiente Quebrado Parece Bug de Código:** Antes de depurar import, bootstrap, runtime ou falha que só acontece numa máquina, confirme que o ambiente local bate com o que o repositório declara. Corrigir código sobre um setup corrompido só mascara a causa real.
- **Bug Intermitente Nem Sempre Reproduz 10/10:** Quando o defeito é flaky, a meta não é perfeição artificial; a meta é obter um sinal observável, estreito e repetível o bastante para distinguir hipóteses concorrentes sem corrigir no escuro.

## Procedimento

Adote as fases abaixo na ordem. Quando o sintoma apontar para setup local, a Fase 0 é obrigatória antes de tocar em código.

1. **Fase 0: Preflight de Ambiente**
   - Use esta fase quando houver sinais como "funciona na minha máquina", CI/local divergente, falha de import, módulo ausente, variáveis ausentes ou suspeita de drift de runtime ou dependências.
   - Compare os arquivos de configuração de ambiente usados no projeto com seus exemplos ou templates, se existirem. Verifique apenas presença e nomes de chaves; nunca faça dump dos valores.
   - Use a documentação viva do projeto, manifests, arquivos de exemplo e arquivos de versão como fonte de verdade. Se houver duas instruções operacionais conflitantes, resolva esse drift documental antes de concluir que a aplicação está lendo o arquivo "errado".
   - Confirme o fluxo oficial de bootstrap, sincronização de dependências e inicialização definido pelo repositório antes de concluir que o bug é de código.
   - Se houver gerenciador de versões, lockfile ou manifesto de dependências, valide primeiro esse estado e só então reinstale ou re-sincronize dependências quando houver drift real.
   - Se a falha for apenas processo, porta ocupada, worker, healthcheck ou operação contínua, pare aqui e encaminhe para `server-management`.
   - Se a evidência apontar para segredo exposto, config insegura, credencial vazando ou risco material de segurança, pare aqui e escale para `security-engineer`.
2. **Fase 1: Reprodução Estável**
   - Não crie código corretivo. Primeiro tente escrever um teste, script ou sequência mínima que gere o erro de forma determinística.
   - Se o bug for intermitente e não fechar 10 em 10 vezes, reduza o escopo até obter um sinal observável e repetível o bastante para comparar hipóteses: uma chamada específica, um input, uma condição de corrida, um horário, uma flag, ou um log invariável.
   - Se você não consegue reproduzir nem obter sinal mínimo, não aplique fix "por feeling". Continue coletando evidência ou declare bloqueio explícito de reprodução.
3. **Fase 2: Identificação do Escopo (Binary Search)**
   - Isole o sistema por camadas. O erro está na interface visível, no serviço intermediário, na integração ou na infraestrutura? Use a ferramenta de menor nível adequada para testar a camada abaixo independentemente da camada acima.
4. **Fase 3: Confirmação da Causa Raiz**
   - Instrumente o ponto exato antes da falha com logs, assertions, dumps sanitizados ou inspeção de estado. Capture a evidência mínima necessária para provar a hipótese vencedora.
5. **Fase 4: Resolução e Validação (Fix)**
   - Aplique o Fix.
   - Execute novamente o cenário da Fase 1 e valide que o sintoma desapareceu sem criar regressão óbvia no fluxo afetado.

## Exemplos

### Caso positivo

**Entrada:** Usuário relata bug complexo com sintomas, regressão ou causa desconhecida.
**Saída esperada:** Reproduzir, isolar hipótese, provar causa raiz e verificar correção com evidência.

### Caso positivo

**Entrada:** "No CI passa, mas aqui está dando erro de import e minhas variáveis parecem sumidas."
**Saída esperada:** Executar a Fase 0, comparar arquivos de ambiente com seus exemplos, validar versões e manifestos declarados, conferir o estado de dependências com os comandos oficiais do repositório e só depois seguir para hipótese de código.

### Caso positivo

**Entrada:** "O bug acontece só às vezes e ninguém consegue reproduzir sempre do mesmo jeito."
**Saída esperada:** Reduzir a superfície até obter um sinal mínimo comparável entre hipóteses, documentar o que reproduz e o que não reproduz, e só então propor correção.

### Caso negativo

**Entrada:** Usuário pede implementar feature clara sem bug.
**Por quê não:** Não há debugging; implemente ou planeje.

### Caso negativo

**Entrada:** "Preciso configurar healthcheck, workers e restart automático do serviço."
**Por quê não:** O problema dominante é operação/runtime de servidor. Encaminhe para `server-management`, não para debugging estruturado.

### Caso negativo

**Entrada:** "Encontrei um token exposto no serviço e quero classificar a severidade."
**Por quê não:** O problema dominante virou risco material de segurança. Escale para `security-engineer`, não continue como debugging genérico.

## Evals de trigger

Deve acionar:

- "bug intermitente sem causa clara"
- "funciona na minha máquina mas no CI passa"
- "está dando erro de import ou módulo ausente"
- "minhas variáveis não estão carregando"
- "preciso achar root cause"

Não deve acionar:

- "feature nova bem definida"
- "configura workers e healthcheck"
- "audita segredo exposto no serviço"
- "gera README"

## Evals de workflow

### Reproducao e Hipotese

- [ ] a resposta explicita o sintoma observado antes de propor correção
- [ ] a resposta descreve um cenário mínimo de reprodução ou um sinal mínimo para bugs intermitentes
- [ ] a resposta lista pelo menos uma hipótese descartada ou reduzida por evidência

### Preflight de Ambiente

- [ ] quando o sintoma envolve setup local, a resposta verifica arquivos de ambiente contra seus exemplos sem expor valores
- [ ] quando o sintoma envolve setup local, a resposta valida arquivos de versão, manifests ou lockfiles relevantes
- [ ] a resposta usa o fluxo oficial do repositório antes de concluir que o bug é de código

### Fechamento

- [ ] a resposta não aplica fix antes de declarar a evidência que sustenta a causa raiz
- [ ] a resposta valida o cenário afetado após a correção ou declara explicitamente por que a validação ficou bloqueada
- [ ] a resposta encaminha para `server-management` ou `security-engineer` quando o problema dominante sai do escopo de debugging
