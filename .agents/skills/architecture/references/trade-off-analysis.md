# Trade-off Analysis

Use esta referência para comparar alternativas e produzir uma decisão que seja
auditável depois. O objetivo não é dar nota bonita, e sim deixar claro por que
uma opção venceu neste contexto.

## Rubrica mínima

Avalie cada alternativa pelos critérios que realmente importam para o caso:

- **Time to value:** quanto atrasa ou acelera a entrega segura.
- **Consistência/correção:** risco de conflito, duplicação ou estado incoerente.
- **Latência e UX:** impacto no caminho síncrono do usuário.
- **Isolamento de falha:** quanto um problema se espalha.
- **Operabilidade:** deploy, observabilidade, retries, runbooks, suporte.
- **Facilidade de mudança:** quão caro fica evoluir ou desfazer depois.
- **Verificabilidade:** quais regras têm feedback local reproduzível, quais
  comandos do projeto as verificam e quais riscos dependem de integração externa.
- **Isolamento de mudança:** contexto, contratos e estado compartilhado necessários
  para editar uma fronteira; ownership e validação conjunta quando houver paralelismo.
- **Custo total:** infraestrutura, coordenação entre times e dependências novas.

Selecione 3 a 5 critérios dominantes. Registre evidência ou identifique a estimativa
para cada comparação; não dê vantagem automática a uma opção apenas por facilitar
o trabalho de uma ferramenta ou agente.

## Quadro de comparação

Use um quadro como este antes de recomendar:

```markdown
| Opção | Resolve o problema central? | Benefícios | Custos aceitos | O que fica mais difícil | Quando deixa de servir |
|---|---|---|---|---|---|
| A | sim/parcial/não | ... | ... | ... | ... |
| B | sim/parcial/não | ... | ... | ... | ... |
```

Evite falsa precisão. `alto/medio/baixo` ou `sim/parcial/não` costuma comunicar
melhor do que números arbitrários.

## Recomendação

Use `output-contract.md` para os campos e a exceção de caminho único com restrição
comprovada. Inclua mitigação dos custos dominantes: quem executa, como se verifica
o resultado e qual sinal pede revisão. Sem medição suficiente, explicite a
premissa e a condição da recomendação; não invente números ou alternativas.

## ADR curto

Antes de emitir ou persistir ADR, siga `decision-handoffs.md`. A sabatina ativa
governa o adiamento e seus rascunhos; o projeto governa localização e promoção.
Nos demais casos, use o template local ou `../assets/adr-short-template.md`, sem
duplicar seu conteúdo nesta referência.

## Sinais de decisão fraca

- a opção vencedora não foi nomeada
- só existe uma alternativa descrita sem restrição comprovada
- o texto fala em escalabilidade genérica sem atributo dominante
- não existe custo operacional explícito
- "depois a gente extrai" aparece sem revisit trigger claro
- um gate local é usado como prova de comportamento externo que ele não testa
- a análise confunde recomendação provisória, decisão aceita e autorização de escrita
