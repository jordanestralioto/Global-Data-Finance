# Integrity And Isolation

## Invariante antes da abstração

Descreva o estado inválido que deve ser impossível e quem pode tentar criá-lo:
request, job, retry, importação ou manutenção. Escolha a menor garantia que o
impede no banco real; uma transação genérica não substitui a análise da corrida.

| Invariante                                                | Decisão a fechar                                                           | Prova relevante                                              |
| --------------------------------------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Um evento externo só é aplicado uma vez no escopo correto | Chave estável e `UNIQUE` no escopo, conflito/upsert e resultado do retry   | Escritores simultâneos e replay; efeito aplicado uma vez     |
| Saldo ou estoque não fica negativo                        | Escrita condicional atômica, constraint aplicável e fronteira transacional | Duas sessões disputando o mesmo recurso                      |
| Uma atualização não sobrescreve outra silenciosamente     | Versão/precondição ou lock curto; conflito explícito                       | Update com versão obsoleta rejeitado                         |
| Mudanças em várias linhas permanecem consistentes         | Transação, isolamento e ordem de locks apropriados à engine                | Falha intermediária e concorrência com sessões independentes |

Não prescreva `upsert` sem definir a chave de conflito e quais campos podem ser
atualizados. Um replay que soma novamente ao saldo continua errado mesmo que
não crie outra linha. Trate colisões com payload diferente segundo o domínio.

Defina retries limitados para os conflitos recuperáveis reais da engine.
Não repita uma operação com efeito externo irreversível sem identidade estável
e estratégia de recuperação. Prefira transações curtas; não mantenha locks
durante chamadas de rede.

## Ownership de relações

Prove por onde cada acesso identifica o owner, inclusive leituras por ID,
updates, deletes, agregações, workers e acessos administrativos. Uma FK prova
existência/relação; a autorização depende do escopo efetivamente aplicado.

Um filho pode herdar ownership pelo pai se o caminho confiável de acesso fizer
essa verificação. A ausência de `tenant_id` na filha não demonstra uma falha por
si só. Por outro lado, filtrar só a tela ou checar o pai em apenas um endpoint
deixa outros caminhos sem garantia.

Se o filho armazena o tenant também, impeça divergência entre o tenant copiado
e o pai. Avalie FK composta como `(tenant_id, parent_id)` referenciando uma chave
compatível no pai, conforme a engine. Duas FKs independentes que apenas provam
que o tenant e o pai existem não provam que pertencem ao mesmo escopo.

Para unicidade local, defina a chave dentro do tenant. Em soft delete,
especifique se o nome/chave pode ser reutilizado e como a engine mantém essa
regra sob concorrência. Um índice de tenant melhora alguns acessos, mas não
substitui a autorização.

Teste com dois owners e controles positivos para ambos, mais tentativas
cruzadas de leitura e mutação. Inclua associação entre filho e pai de tenants
diferentes quando o modelo permite construir essa tentativa. RLS, grants e
papéis administrativos exigem prova específica da engine; siga o roteamento
do corpo da skill.

## Tipos que precisam de uma decisão de domínio

Evite decidir pelo nome do campo. Resolva as ambiguidades que alteram o contrato:

- Dinheiro: moeda, precisão, escala, unidade mínima e arredondamento. Um tipo
  decimal sozinho não impede mistura de moedas ou arredondamento divergente.
- Taxa/medida: escolha exatidão ou aproximação conforme o cálculo; nem todo
  campo chamado `rate` representa dinheiro.
- Tempo: distinga instante absoluto, data civil e horário local recorrente.
  Preserve as informações de fuso necessárias ao domínio e às conversões.
- Identificador: trate códigos externos e zeros à esquerda como identidade,
  sem inferir aritmética ou segurança por serem UUIDs/strings.
- Enum e nulidade: defina estados válidos, significado de ausência e
  compatibilidade com versões antigas que ainda não conhecem um estado novo.

Antes de converter dados existentes, meça valores fora do domínio, colisões e
conversões ambíguas. Defina o tratamento de rejeitados e valide a transformação
na fronteira de dados, além do caminho feliz da aplicação.
