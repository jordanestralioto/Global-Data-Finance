# Portable API Triage

> A ferramenta localiza pistas. Comprove comportamento com leitura contextual e
> testes nativos do consumidor.

## Execução

Use Python disponível para ferramentas do projeto; não é necessário que a
aplicação seja Python. A CLI depende apenas da biblioteca padrão e não importa
o harness nem código da aplicação.

```bash
python .agents/skills/api-patterns/scripts/validate_api.py . --output json
python .agents/skills/api-patterns/scripts/validate_api.py app/api
python .agents/skills/api-patterns/scripts/validate_api.py internal/http \
  --include '**/*.go' --exclude '**/generated/**'
python .agents/skills/api-patterns/scripts/validate_api.py contract.openapi.json \
  --fail-on-critical
```

O antigo `scripts/api_validator.py` foi substituído por `scripts/validate_api.py`.
Atualize comandos locais e regenere a projeção via `harness-sync`; não copie
arquivos da central ou edite módulos projetados manualmente.

## Descoberta e escopo

- Diretórios convencionais `api`, `routes`, `routers`, `controllers`, `endpoints`,
  `handlers` e `actions` são reconhecidos, incluindo subdiretórios.
- Extensões comuns de Python, JavaScript/TypeScript, Go, Rust, Ruby, PHP, Java,
  Kotlin, C#, Elixir e outras são candidatas; isso não significa parsing dessas
  linguagens. Um arquivo informado explicitamente dispensa convenção de nome.
- Use `--include` repetido para selecionar globs relativos ao diretório alvo.
  Com include explícito, esses globs substituem a seleção automática de candidatos
  e podem selecionar extensões adicionais. Use `--exclude` para caminhos do projeto.
- A caminhada poda dependências, ambientes virtuais, build, projeções e a própria
  ferramenta. Não segue symlinks. Não interpreta `.gitignore`; declare exclusões
  adicionais conforme o projeto.
- A ordem é estável. O padrão é até 25 arquivos; aumente `--max-files` quando
  necessário. O relatório mostra encontrados, inspecionados e omitidos.

## O que cada análise comprova

| `analysis`         | Evidência e limite                                                                                                                        |
| ------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- |
| `lexical-markers`  | Arquivo UTF-8 lido; pistas textuais e checks manuais. Não resolve AST, middleware ou fluxo entre funções                                  |
| `structured-json`  | Contratos declarados em JSON; referências JSON locais resolvidas quando possível. Não prova conformidade completa de OpenAPI nem execução |
| `yaml-text-only`   | Somente marcadores de texto; não valida sintaxe YAML ou contratos por operação                                                            |
| `inspection-error` | Falha de leitura/parsing: falta evidência para concluir a triagem                                                                         |

`passed` contém somente observações verificadas no arquivo/contrato, não uma
aprovação da API. `issues` são pistas para revisão; `[X]` indica um problema
estrutural do documento, não severidade de segurança comprovada. `unverified`
lista controles que exigem contexto e testes.

A palavra `stream`, um `try`, uma classe `Provider` ou `202` em outra função não
comprova duração, ausência de tratamento central ou proteção de uma rota.
Também não conclua segurança pela presença de `auth`, `ETag` ou `signature`.

## Exit codes e automação

| Exit | Significado                                                                                     |
| ---- | ----------------------------------------------------------------------------------------------- |
| `0`  | Triagem dos candidatos selecionados concluída; pode conter avisos e checks não verificados      |
| `1`  | `--fail-on-critical` e problema estrutural `[X]` encontrado                                     |
| `2`  | Input/argumento inválido, nenhum candidato, leitura/parsing falho ou limite que omitiu arquivos |

`status: complete` descreve a execução da triagem. Não substitui gates do projeto,
testes de authz, revisão independente ou evals do agente. YAML continua limitado
mesmo com exit 0; use o validador OpenAPI adotado pelo consumidor ou exporte JSON
para a triagem estruturada. Referências externas não são buscadas na rede/disco.

## Checks mínimos depois da triagem

- Recurso de outro caller/tenant é rejeitado pelo controle real.
- Retry concorrente e redelivery não duplicam efeitos críticos.
- Precondition é validada atomicamente antes da escrita.
- Custo é reservado antes do trabalho caro e reconciliado após falha/cancelamento.
- Stream e webhook têm lifecycle e trust boundary comprovados pelos testes.
