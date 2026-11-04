---
name: modularizar
description: >-
  Use para sanear god files, god components e módulos monolíticos com migração
  auditável. Ative quando o usuário pedir "quebra esse arquivo gigante", "esse
  componente virou monstro", "separa em módulos", "extrai
  utilitários" ou invocar `[$modularizar]`. Aplique quando imports, exports,
  callers, contratos e gates precisarem ser rastreados. Não use para ajustes
  locais simples, pequenos renames, funções isoladas grandes ou quando o melhor
  caminho for planejar a arquitetura antes de tocar no código; nesse caso,
  prefira `architecture`.
---

# Modularizar

## Guardrails permanentes

- **Saneie antes de modularizar:** trate repetição, complexidade, comentários ruins, naming fraco e visibilidade inadequada antes de quebrar o arquivo em partes. Isso evita espalhar problemas antigos por vários módulos novos.
- **Reaproveite antes de extrair:** se a duplicação já foi resolvida em outro ponto do repositório, prefira migrar para a abstração existente em vez de criar mais um helper local.
- **Otimize com evidência:** proponha melhorias de complexidade e Big-O quando o ganho esperado for claro, com impacto, risco e validação registrados no plano.
- **Pode quebrar e migrar:** a skill pode atualizar callers, imports, exports, entrypoints e utilitários compartilhados quando isso deixar o design final melhor, desde que cada mudança fique registrada e aprovada.
- **Privado Python achado na Fase 1 vira público:** ao encontrar código Python com naming privado inadequado para a superfície real de uso durante a Fase 1, promova o símbolo de privado para público já no saneamento profundo; não empurre esse ajuste para a Fase 2 nem preserve underscore por inércia.
- **Arquivos extraídos precisam ter basename público:** na Fase 2, não crie arquivos extraídos cujo basename comece com `_`. Arquivos canônicos exigidos pela linguagem para entrypoint, como `__init__.py`, são exceção somente quando cumprem esse papel de entrypoint, não como módulo extraído de responsabilidade.
- **Promova o que virar reutilizável:** símbolos extraídos que passam a servir outros módulos devem virar públicos. O restante pode continuar interno para não inflar a API sem motivo.
- **Compatibilidade vem do entrypoint canônico, não do arquivo legado:** o god file deve virar um módulo/pacote por responsabilidade real, e a compatibilidade deve ser preservada pelo entrypoint público final desse módulo ou pacote. O arquivo legado deve ser removido na Fase 2; se a remoção quebrar imports, callers, exports ou testes, o agente deve corrigir a fallout até não restar gateway legado.
- **Faça a limpeza completa:** comentários obsoletos, redundantes ou pouco profissionais devem ser removidos ou reescritos; nomes ambíguos ou anti-profissionais devem ser corrigidos.
- **Modularize por responsabilidade real:** a divisão final deve refletir fronteiras de responsabilidade, não apenas uma quebra mecânica em pastas.

## Roteamento por etapa

01. Trate todo caso como workflow faseado. Não há subfluxo leve sem gates.
02. Identifique a etapa atual antes de abrir referências adicionais:
    - sem plano, Gate 1 pendente ou Fase 1 ainda em execução -> abra apenas `references/PHASE_1.md`
    - Gate 1 aprovado, Fase 1 executada, a avaliação pós-Fase 1 marcou `PHASE_2_NEEDED: YES` e o usuário quer seguir para a extração -> abra apenas `references/PHASE_2.md`
03. Abra `references/PLAN_TEMPLATE.md` somente quando for preencher ou atualizar `modularizar_<target-basename>.md`.
04. Abra `references/OUTPUT_TEMPLATE.md` somente quando for montar `modularizar_<target-basename>-output.md`.
05. Não carregue os dois references de fase na mesma passada de contexto, a menos que esteja revisando a skill em si. O objetivo é manter uma única frente operacional ativa por vez.
06. Enquanto estiver na Fase 1, escreva no plano apenas baseline, proposta e execução da própria Fase 1. Não preencha `## 6. Phase 2A - Modularization Proposal` nem `## 7. Phase 2B - Modularization Execution Log` antes de `GATE_1_APPROVED: YES` e `PHASE_1_EXECUTED: YES`.
07. Depois de executar a Fase 1, preencha a avaliação de necessidade da Fase 2. Só considere a Fase 2 quando o alvo ainda tiver tamanho ou complexidade material e existir uma necessidade estrutural concreta de separar responsabilidades; tamanho isolado ou redistribuição mecânica não bastam.
08. Se `PHASE_2_NEEDED: NO`, registre a justificativa, mantenha `## 6` e `## 7` intocadas, valide `phase1-complete` e encerre o workflow na Fase 1 sem pedir o Gate 2.
09. Antes de editar código, peça a aprovação explícita do gate correspondente.
10. Em cada gate, valide com `.agents/skills/modularizar/scripts/modularizar_guard.sh` antes de avançar.
11. Se o escopo mudar materialmente em qualquer etapa, revise o plano e peça nova aprovação antes de continuar.

## Procedimento

N/A

## Exemplos

### Caso positivo

**Entrada:** "Quebra esse componente enorme, remove duplicação, reaproveita os helpers já existentes e deixa os nomes profissionais."
**Saída esperada:** Abrir `modularizar`, roteá-lo para `references/PHASE_1.md`, criar o plano faseado, listar o inventário completo da Fase 1 e parar no Gate 1 antes de qualquer execução.

### Caso positivo

**Entrada:** "Esse service está virando um god file; se precisar mexer nos callers e promover utilitários públicos, pode fazer, mas me mostra tudo por fase."
**Saída esperada:** Abrir `modularizar`, registrar impactos em callers/imports/exports no plano, executar a limpeza aprovada, avaliar se o alvo continua materialmente grande ou complexo e só abrir `references/PHASE_2.md` quando a avaliação registrar `PHASE_2_NEEDED: YES`.

### Caso positivo

**Entrada:** "Quebra esse arquivo Python grande em módulos, mas mantém o import público pelo pacote."
**Saída esperada:** Abrir `modularizar`, registrar na Fase 1 a promoção necessária de símbolos Python privados, e na Fase 2 exigir entrypoint canônico via pacote sem preservar o arquivo legado como gateway.

### Caso negativo

**Entrada:** "Desenha a arquitetura nova do backend para suportar múltiplos bounded contexts."
**Por quê não:** Isso é arquitetura ou planning amplo; use `architecture` ou `openspec-workflow`.

### Caso negativo

**Entrada:** "Mede o gargalo desse fluxo antes de qualquer mudança."
**Por quê não:** Isso é profiling puro; use `performance-profiling`.

### Caso negativo

**Entrada:** "Após a limpeza o arquivo ficou coeso; não extraia módulos só para distribuir o código."
**Por quê não:** Registre `PHASE_2_NEEDED: NO`, conclua a Fase 1 e não abra a referência da Fase 2 nem peça o Gate 2.

### Caso negativo

**Entrada:** "Extrai `_helper.py` e deixa `foo.py` só reexportando tudo para manter compatibilidade."
**Por quê não:** Isso viola o contrato da Fase 2. Arquivos extraídos não podem ter basename privado e o arquivo legado deve ser removido, não preservado como shim ou gateway.

## Evals de trigger

Deve acionar:

- "quebra esse arquivo gigante em módulos"
- "limpa completamente esse código confuso e remove duplicação"
- "extrai utilitários compartilhados desse bloco monolítico"
- "modulariza esse god component sem esconder os impactos nos callers"
- "saneia esse módulo enorme e me mostra o plano faseado"
- "modularisa esse arquivozao e reaproveita os utils que ja existem"
- "quebra esse arquivo em módulos mas mantém o import público pelo pacote"
- "[$modularizar] src/foo/bar.py"

Não deve acionar:

- "define a arquitetura dessa feature nova"
- "mede o gargalo dessa query"
- "investiga esse bug intermitente sem causa raiz"
- "redesenha esse endpoint REST"
- "só organiza esse arquivo grande por legibilidade; não precisa mexer em callers, contratos ou gates"
- "preciso de um refactor amplo multi-time sem alvo claro"
- "cria `_helper.py` e deixa o arquivo antigo como shim"

## Evals de workflow

### Cenário 1: roteamento para a Fase 1

**Entrada:** "Esse service virou um god file. Remove duplicação, reutiliza utilitários existentes, melhora o algoritmo e me mostra tudo por fase."

- [ ] abre `references/PHASE_1.md`
- [ ] não abre `references/PHASE_2.md` antes do Gate 2
- [ ] cria `modularizar_<target-basename>.md`
- [ ] pede Gate 1 antes de editar código

### Cenário 2: transição controlada para a Fase 2

**Entrada:** "Depois da limpeza, extrai os módulos, ajusta os callers e promove só o que virar reutilizável."

- [ ] abre `references/PHASE_2.md`
- [ ] não reabre `references/PHASE_1.md` como referência principal da execução
- [ ] registra evidência de tamanho ou complexidade material remanescente e uma necessidade estrutural concreta
- [ ] marca `PHASE_2_NEEDED: YES`
- [ ] valida `phase2` antes de extrair módulos
- [ ] gera `modularizar_<target-basename>-output.md`

### Cenário 3: Fase 2 não necessária

**Entrada:** "Após a limpeza o arquivo ficou coeso; não extraia módulos só para distribuir o código."

- [ ] registra `PHASE_2_NEEDED: NO`
- [ ] registra a evidência pós-Fase 1 e a justificativa da decisão
- [ ] usa `Structural separation needed: NO` e valida `phase1-complete`
- [ ] não abre `references/PHASE_2.md`
- [ ] não solicita nem preenche o Gate 2
- [ ] mantém `## 6` e `## 7` sem conteúdo novo

### Cenário 4: invariantes mantidos na Fase 2

**Entrada:** "Extrai `_helper.py` e deixa `foo.py` só redirecionando imports."

- [ ] `references/PHASE_2.md` deixa explícito que basename privado é inválido
- [ ] `references/PHASE_2.md` deixa explícito que gateway legado é inválido
- [ ] `validate-plan --phase phase2` continua falhando se o plano violar esses pontos

## Scripts

- `.agents/skills/modularizar/scripts/modularizar_guard.sh`: inicializa o plano, valida cada gate de fase e confere o relatório final do workflow.

## Referências

Leia apenas o arquivo relevante para a etapa atual:

| Situação                                                                                   | Arquivo                         |
| ------------------------------------------------------------------------------------------ | ------------------------------- |
| Sem plano, Gate 1 pendente ou Fase 1 em execução                                           | `references/PHASE_1.md`         |
| Gate 1 aprovado, Fase 1 executada, `PHASE_2_NEEDED: YES` e modularização prestes a começar | `references/PHASE_2.md`         |
| Preencher ou atualizar o plano faseado                                                     | `references/PLAN_TEMPLATE.md`   |
| Montar o relatório final com evidência das execuções                                       | `references/OUTPUT_TEMPLATE.md` |
