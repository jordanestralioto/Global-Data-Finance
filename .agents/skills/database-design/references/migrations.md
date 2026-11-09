# Migrations

## Compatibilidade vem dos callers reais

Identifique quem lê e escreve a estrutura: versões da aplicação, workers,
imports, relatórios, jobs atrasados e ferramentas operacionais. Defina se
versões antigas e novas coexistem e por quanto tempo. Não transforme rename,
`NOT NULL` ou mudança de tipo em rollout único sem verificar esse contrato.

Uma operação pode ser compatível em banco novo ou em uma janela controlada.
Justifique esse caso com os callers e as condições reais; não imponha um
ritual de múltiplos deploys quando ele não protege nenhuma garantia.

## Expansão e transição com escrita concorrente

Para substituir uma coluna em uso, planeje:

1. Adicione a representação nova sem invalidar writers antigos.
2. Defina como escritas novas e antigas mantêm as representações consistentes
   durante a transição. Dual write precisa de atomicidade ou reconciliação
   explícita; dois updates independentes não formam uma garantia.
3. Faça backfill retomável em lotes, com cursor estável e proteção contra
   sobrescrever uma versão mais nova. Defina reprocessamento e rejeitados.
4. Valide cobertura e equivalência enquanto as escritas continuam. Uma contagem
   única antes do cutover não prova que a corrida foi fechada.
5. Mude a leitura com regra de preferência/fallback e comportamento explícito
   para registros ainda não convertidos. Observe divergências.
6. Encerre o uso antigo somente após evidência sobre todas as versões e jobs.
7. Remova a estrutura antiga em uma etapa cuja recuperação esteja definida.

Não fixe backfill antes de atualizar writers como ordem universal. O protocolo
deve evitar que um writer antigo crie dados fora da cópia depois que ela passou.

Para adicionar obrigatoriedade, separe preenchimento, escritores compatíveis,
validação de legado e enforcement quando a engine permitir. Uma coluna nova
com default pode ser barata ou causar reescrita: confirme versão, expressão e
comportamento da ferramenta de migration.

## Operação, retomada e recuperação

Registre os dados que mudam a execução:

- Duração tolerável de espera e de bloqueio, transações abertas e taxa de escrita.
- Método de construção de índice suportado, restrições transacionais e como
  detectar/limpar artefatos de uma construção interrompida.
- Tamanho de lote, progresso persistido, limites operacionais e critério para
  parar ou retomar o backfill sem repetir efeitos.
- Plano para conversão inválida, colisões de unicidade e dados que chegam tarde.
- Recuperação após cada ponto: retorno do código, roll-forward, restauração ou
  reconciliação. Reverter DDL não recupera automaticamente dados removidos.

Use uma cópia representativa ou banco descartável para validar SQL gerado,
constraints, concorrência e compatibilidade. Para impacto operacional, compare
com o volume e a configuração do destino; um teste vazio não prova o orçamento
de locks de uma tabela quente.

## Detalhes específicos de engine

Confira versão e documentação antes de sugerir DDL online/concurrent,
enforcement adiado ou timeout. `references/native-tooling.md` distingue espera
por lock, validação de constraints e comportamento do runner. Para SQLAlchemy,
Prisma ou outra ferramenta, inspecione o SQL e a transação efetivamente usados,
sem assumir que a API de migration preserva o método planejado.

DDL destrutivo encontrado pelo helper é um pedido de revisão do rollout, não
prova de que a operação é indevida. A ausência de alerta também não prova
compatibilidade: o helper não conhece versões implantadas nem o estado aplicado.
