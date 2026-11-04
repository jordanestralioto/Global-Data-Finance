# Checklist de cobertura da árvore inicial

Carregue este arquivo no passo 3 do procedimento, antes de declarar a árvore
mapeada. Ele existe porque "todas as dúvidas que eu enxergo" não produz
evidência de cobertura: o ponto cego não aparece na lista justamente por ser
cego.

Percorra os oito eixos. Cada um vira uma linha da tabela §3 do documento, com
uma destas três saídas:

- **gerou dúvida** — registre o `Qn` correspondente na seção 5;
- **gerou fato** — registre o `Fn` na seção 4, com evidência;
- **não se aplica** — escreva a razão, não a palavra "não". "Sem consumidor
  externo: a saída fica em `debug/` e nada lê" é razão; "não se aplica" sozinho
  é um eixo pulado com aparência de eixo coberto.

Relevância é julgamento seu. Um eixo irrelevante fechado com razão custa uma
linha; um eixo relevante esquecido custa uma decisão descoberta durante a
implementação, quando ela já é cara.

## 1. Escopo

O que está dentro e o que fica de fora. Qual é o menor recorte que já entrega
valor, e o que foi deliberadamente adiado. Se a mudança tem uma versão "mínima"
e uma "completa", qual das duas está sendo decidida aqui.

Pergunta de calibragem: se metade disso for cortada por falta de tempo, qual
metade cai?

## 2. Consumidores

Quem lê a saída depois: outra fase, um artefato persistido, o dashboard, um
script de operador, um agente. Consumidor que existe hoje e consumidor que a
mudança cria contam igual.

Pergunta de calibragem: se o formato mudar, quem quebra e como fica sabendo?

## 3. Contratos e dados

Schema, chave primária, unidade, escala, nulabilidade, cardinalidade, ordenação.
O que a mudança acrescenta ao contrato e o que ela passa a proibir. Se há dado
persistido, o que acontece com o que já está gravado.

Pergunta de calibragem: duas execuções sobre a mesma entrada produzem
exatamente a mesma saída? Se não, o que pode divergir?

## 4. Falhas e segurança

O que acontece quando a entrada está errada, ausente, duplicada ou grande demais.
O que deve interromper e o que deve seguir registrando. Onde entram segredo,
credencial, caminho fora do workspace ou dado de terceiro.

Pergunta de calibragem: qual falha é pior — parar a execução ou seguir com dado
suspeito? A resposta define se o caso vira gate ou aviso.

## 5. Migração e rollback

Como sair do estado atual para o novo sem parada total. O que fazer com o que já
foi produzido pelo comportamento antigo. Como voltar atrás, e o que é caro ou
impossível desfazer.

Pergunta de calibragem: existe um instante em que metade do sistema está no
formato novo e metade no antigo? O que acontece nesse instante?

## 6. Operação e observabilidade

Quem opera, com qual comando, e como percebe que deu certo ou errado. Que
evidência fica gravada depois da execução. Qual sinal um incidente produziria.

Pergunta de calibragem: com o sistema em produção e o autor ausente, o operador
consegue diagnosticar sozinho pelo que ficou registrado?

## 7. Validação

Como se prova que a mudança funciona: teste determinístico, execução com dado
real, comparação com baseline, verificação manual. Qual evidência é obrigatória
antes de considerar a mudança pronta.

Pergunta de calibragem: existe um teste que falha hoje e passa depois? Se não,
o que exatamente está sendo provado?

## 8. Ownership e documentação

Quem passa a ser dono do código, do artefato e da decisão. Que documento
canônico precisa mudar, e qual decisão merece registro permanente. O que fica
obsoleto e deve ser removido em vez de conviver.

Pergunta de calibragem: seis meses depois, quem lê o quê para entender por que
está assim?
