# Server Functions And Framework Actions

> Identifique a entrada remota real, mesmo quando o código parece uma função local.

## Fronteira de confiança

Server Actions/Functions e actions de formulário podem gerar endpoints sem uma
rota escrita manualmente. Verifique o transporte e a versão do framework antes
de concluir que uma função é interna. No Next.js, uma action exposta pode receber
POST direto; funções internas usadas apenas no servidor têm outro alcance.

Esse critério também se aplica a handlers gerados em outros frameworks e
linguagens: nome da função, tipagem e esconder o botão na UI não autorizam o caller.

## Ordem da revisão

1. Identifique como invocar a action fora da UI, qual método/transporte ela usa
   e quais controles o framework já fornece.
2. Valide sessão/token no ponto de entrada ou no serviço de dados chamado por ele.
   O redirect de uma página não comprova autorização da chamada direta.
3. Valide IDs, campos permitidos, tamanho e limites com a biblioteca do projeto.
   Tipos estáticos e dados capturados em closure não validam input remoto.
4. Derive identidade e tenant do contexto validado. Vincule cada recurso à policy
   correspondente; autenticação sozinha não resolve BOLA/IDOR.
5. Aplique quota e reserva atômica de custo antes de I/O caro. Para mutações
   críticas, defina retry/idempotência e concorrência conforme o domínio.
6. Confira origem/CSRF e comportamento de cookies e proxies conforme o framework.
   Não desative proteções de origem para contornar um erro de deploy.
7. Retorne apenas campos necessários; sanitize erros e mantenha segredos fora do
   payload serializado, argumentos e closures enviados ao cliente.

## Aplicação sem receita por linguagem

```text
entrada remota
  -> validar sessão e schema
  -> autorizar operação e recurso usando identidade confiável
  -> reservar quota/custo e tratar chave de repetição
  -> executar mutação com transação/precondition quando necessário
  -> persistir resultado e devolver resposta mínima sanitizada
```

Use as abstrações já adotadas no consumidor. Não imponha Zod, decorators,
middleware específico, ORM ou uma implementação em Python no backend.

## Testes negativos

- Chamada direta sem carregar a página: rejeitada sem efeitos colaterais.
- Caller autenticado envia ID de outro tenant: nenhum dado ou mutação permitida.
- Campos administrativos extras ou payload excessivo: rejeitados/ignorados
  conforme schema explícito, sem mass assignment.
- Retry concorrente da mesma mutação crítica: um efeito persistido.
- Quota esgotada ou origem inválida: rejeitada antes do trabalho caro.
- Falha de banco/provider: retorno sanitizado, com identificador de rastreio.

## Fontes primárias

- [Next.js: segurança de Server Actions](https://nextjs.org/docs/app/guides/data-security#built-in-server-actions-security-features).
- [React: Server Functions](https://react.dev/reference/rsc/server-functions).

Consulte a documentação da versão usada pelo projeto antes de aplicar detalhes
de transporte ou de proteção de um framework a outro.
